"""Medición de la capa de sugerencias sobre lo que leyó HOMR (#257, ADR-0036).

`exp_14` mide la capa por el camino de producción: las reglas (`ValidationEngine`) y después
la capa con el filtro de admisibilidad de los casos de uso (`cadenza.application.suggest`:
`validate_after`, sin duplicados, tres por hallazgo), sobre el `ScoreIR` que HOMR leyó. La
verdad es la del corpus de #255: la corrección del corrector ideal de cada evento leído, de
cada hueco y de cada compás, con su ancla relativa al estado leído (`seq` 0, ADR-0011).

Todo se cuenta; las proporciones se derivan de los recuentos y son None si no hay con qué
medirlas (CLAUDE.md §8): nunca una cifra de reserva.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final, Literal

from cadenza.application.suggestions import LEARNED_PREFIX, suggest
from cadenza.domain import (
    Anchor,
    EditEvent,
    EditOp,
    Finding,
    InvalidEditPayload,
    Provenance,
    ScoreDocument,
    ScoreIR,
    SuggestedEdit,
    SuggestedFinding,
    SuggestionResult,
    apply_edit,
    build_anchor_index,
    snapshot_before,
    translate_anchor,
    validate_after,
)
from cadenza.validation import ValidationEngine
from cadenza.validation.learned import (
    FAMILIES,
    NONE_LABEL,
    ScoreFeatures,
    insertion_label,
    label_of_edit,
    labels_from_correction,
)

from .validation_metrics import (
    MeasureError,
    MeasureEvaluationRecord,
    aggregate_validation_metrics,
    evaluate_measures,
)

Position = tuple[int, int, int, int, int]
Policy = Literal["high", "first"]
POLICIES: Final[tuple[Policy, ...]] = ("high", "first")
CATEGORIES: Final[tuple[str, ...]] = ("accidental", "duration", "pitch", "structure", "key_clef")
_APPLIED_AT: Final[datetime] = datetime(2026, 1, 1, tzinfo=UTC)
SuggestedList = Sequence[tuple[Finding, Sequence[SuggestedEdit]]]


def _position(anchor: Anchor | Mapping[str, Any]) -> Position:
    if isinstance(anchor, Anchor):
        return (anchor.part, anchor.staff, anchor.measure, anchor.voice, anchor.event_index)
    return (
        int(anchor["part"]),
        int(anchor["staff"]),
        int(anchor["measure"]),
        int(anchor["voice"]),
        int(anchor["event_index"]),
    )


# --- La verdad ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IncipitCase:
    """Un incipit a medir: lo que leyó HOMR y sus registros del corpus."""

    incipit_id: str
    work: str
    score: ScoreIR
    records: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True, slots=True)
class IncipitTruth:
    """La verdad de un incipit según el corpus, relativa al estado leído."""

    labels: Mapping[Position, Mapping[str, str]]
    correct_events: frozenset[Position]
    gaps: Mapping[Position, frozenset[str]]
    errors: tuple[MeasureError, ...]


def measure_errors(records: Iterable[Mapping[str, Any]]) -> list[MeasureError]:
    """Las correcciones reales de cada compás: cada operación de cada registro.

    Cada edición que deriva `derive_edit_events` está en un registro del corpus y solo en
    uno, así que son las mismas que usa `exp_06` (`evaluate_score_measures`).
    """
    errors: list[MeasureError] = []
    for record in records:
        anchor = record["anchor"]
        for op in (record.get("correction") or {}).get("ops", ()):
            errors.append(
                MeasureError(
                    part=int(anchor["part"]),
                    staff=int(anchor["staff"]),
                    measure=int(anchor["measure"]),
                    op=str(op),
                )
            )
    return errors


def truth_of(records: Iterable[Mapping[str, Any]]) -> IncipitTruth:
    rows = list(records)
    labels: dict[Position, Mapping[str, str]] = {}
    correct: set[Position] = set()
    gaps: dict[Position, set[str]] = {}
    for record in rows:
        kind = record.get("record")
        if kind == "event" and record.get("aligned"):
            position = _position(record["anchor"])
            correction = record.get("correction")
            labels[position] = labels_from_correction(record["read"], record["context"], correction)
            if correction is None:
                correct.add(position)
        elif kind == "insertion":
            event = (record.get("correction") or {}).get("event") or {}
            label = insertion_label(event.get("kind"), event.get("duration_beats"))
            if label is not None:
                gaps.setdefault(_position(record["anchor"]), set()).add(label)
    return IncipitTruth(
        labels=labels,
        correct_events=frozenset(correct),
        gaps={position: frozenset(found) for position, found in gaps.items()},
        errors=tuple(measure_errors(rows)),
    )


def is_true_fix(edit: SuggestedEdit, features: ScoreFeatures, truth: IncipitTruth) -> bool:
    """Si la edición propuesta es la corrección del corrector ideal (de su familia)."""
    position = _position(edit.anchor)
    if edit.op is EditOp.INSERT_EVENT:
        after = edit.after or {}
        label = insertion_label(after.get("kind"), after.get("duration_beats"))
        return label is not None and label in truth.gaps.get(position, frozenset())
    labelled = label_of_edit(edit.op, edit.after, features.events.get(position))
    if labelled is None:
        return False
    family, label = labelled
    return truth.labels.get(position, {}).get(family) == label


# --- La línea base: los candidatos de la regla en su orden ---------------------------------


class RuleOrderModel:
    """Sin capa que ordene: los candidatos de cada regla en el orden en que los da la regla,
    por el mismo filtro de admisibilidad de producción. Es la línea base del orden."""

    version: Final[str] = "rule-order"

    def suggest(self, document: ScoreDocument, findings: Sequence[Finding]) -> SuggestionResult:
        return SuggestionResult(
            findings=tuple(
                SuggestedFinding(finding=finding, suggestions=finding.candidates)
                for finding in findings
            )
        )


# --- Aplicar sugerencias -----------------------------------------------------------------


def _target(edit: SuggestedEdit) -> tuple[str, Position]:
    return ("gap" if edit.op is EditOp.INSERT_EVENT else "event", _position(edit.anchor))


def select_suggestions(suggested: SuggestedList, policy: Policy) -> list[SuggestedEdit]:
    """La primera sugerencia de cada hallazgo (`first`), o solo si es de confianza alta
    (`high`). Una sola por evento o hueco: la del primer hallazgo que lo toca."""
    chosen: list[SuggestedEdit] = []
    seen: set[tuple[str, Position]] = set()
    for _, suggestions in suggested:
        if not suggestions:
            continue
        first = suggestions[0]
        if policy == "high" and first.confidence_level != "high":
            continue
        target = _target(first)
        if target in seen:
            continue
        seen.add(target)
        chosen.append(first)
    return chosen


def apply_suggestions(
    score: ScoreIR, suggestions: Sequence[SuggestedEdit], *, document_id: str
) -> tuple[ScoreIR, int, int]:
    """Aplica las sugerencias, con anclas relativas al estado leído, como lo haría una persona
    una tras otra: cada ancla se traduce al estado anterior (ADR-0011) y la edición pasa
    `validate_after` sobre él. Devuelve el estado final, las aplicadas y las descartadas."""
    applied: list[EditEvent] = []
    current = score
    skipped = 0
    for suggestion in suggestions:
        seq = len(applied) + 1
        anchor = translate_anchor(suggestion.anchor, 0, seq - 1, applied)
        if anchor is None:
            skipped += 1
            continue
        try:
            validate_after(current, anchor, suggestion.op, suggestion.after)
            edit = EditEvent(
                id=f"{document_id}:{seq}",
                document_id=document_id,
                seq=seq,
                anchor=anchor,
                op=suggestion.op,
                author="exp_14",
                created_at=_APPLIED_AT,
                before=snapshot_before(current, anchor, suggestion.op),
                after=suggestion.after,
            )
            current = apply_edit(current, edit)
        except (InvalidEditPayload, IndexError, ValueError, TypeError, ZeroDivisionError):
            skipped += 1
            continue
        applied.append(edit)
    return current, len(applied), skipped


def classify_suggestions(
    suggestions: Sequence[SuggestedEdit], features: ScoreFeatures, truth: IncipitTruth
) -> Counter[str]:
    """Qué haría aplicar cada sugerencia: arreglar, estropear una nota correcta, arreglar mal
    un evento con error o insertar un evento que no falta."""
    counts: Counter[str] = Counter()
    for suggestion in suggestions:
        counts["selected"] += 1
        position = _position(suggestion.anchor)
        if is_true_fix(suggestion, features, truth):
            counts["correct"] += 1
        elif suggestion.op is EditOp.INSERT_EVENT:
            counts["spurious_insertion"] += 1
        elif position in truth.correct_events:
            counts["damaged_correct_events"] += 1
        elif position in truth.labels:
            counts["wrong_fix_on_erroneous_event"] += 1
        else:
            counts["unlabelled"] += 1
    return counts


# --- Medir un incipit --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IncipitMeasurement:
    incipit_id: str
    counts: Counter[str]
    measures_rules: list[MeasureEvaluationRecord]
    measures_with_layer: list[MeasureEvaluationRecord]
    suggested: list[tuple[Finding, tuple[SuggestedEdit, ...]]]
    policies: dict[str, Counter[str]] = field(default_factory=dict)


def _is_learned(finding: Finding) -> bool:
    return finding.rule_id.startswith(LEARNED_PREFIX)


def measure_incipit(
    case: IncipitCase, model: Any, validator: ValidationEngine
) -> IncipitMeasurement:
    """Reglas y capa sobre lo leído de un incipit, frente a su verdad del corpus."""
    truth = truth_of(case.records)
    document = ScoreDocument(
        id=case.incipit_id,
        score=case.score,
        anchors=build_anchor_index(case.score),
        provenance=Provenance(omr_engine="homr"),
    )
    findings = validator.validate(document)
    suggested = suggest(document, findings, model)
    baseline = suggest(document, findings, RuleOrderModel())
    features = ScoreFeatures.of(case.score)
    counts: Counter[str] = Counter()
    counts["correct_events"] = len(truth.correct_events)
    counts["labelled_events"] = len(truth.labels)

    def true(edit: SuggestedEdit) -> bool:
        return is_true_fix(edit, features, truth)

    # Sugerencias a los posibles errores de las reglas: la capa ordena, la regla acota.
    base_by_finding = {id(finding): suggestions for finding, suggestions in baseline}
    for finding, suggestions in suggested:
        if _is_learned(finding):
            continue
        counts["rule_findings"] += 1
        if finding.candidates:
            counts["rule_findings_with_candidates"] += 1
        has_true = any(true(candidate) for candidate in finding.candidates)
        counts["rule_findings_with_true_candidate"] += int(has_true)
        for prefix, ranked in (
            ("rule", suggestions),
            ("baseline", base_by_finding.get(id(finding), ())),
        ):
            if not ranked:
                continue
            counts[f"{prefix}_findings_with_suggestions"] += 1
            top1 = true(ranked[0])
            top3 = any(true(s) for s in ranked[:3])
            counts[f"{prefix}_top1_correct"] += int(top1)
            counts[f"{prefix}_top3_correct"] += int(top3)
            if has_true:
                counts[f"{prefix}_top1_correct_true_candidate"] += int(top1)
                counts[f"{prefix}_top3_correct_true_candidate"] += int(top3)

    # Posibles errores propios de la capa.
    learned_at: dict[Position, tuple[str, bool]] = {}
    learned_findings: list[Finding] = []
    for finding, suggestions in suggested:
        if not _is_learned(finding):
            continue
        family = finding.rule_id.removeprefix(LEARNED_PREFIX)
        correct = true(suggestions[0])
        learned_findings.append(finding)
        counts["learned_findings"] += 1
        counts["learned_correct"] += int(correct)
        counts[f"learned_findings:{family}"] += 1
        counts[f"learned_correct:{family}"] += int(correct)
        if suggestions[0].confidence_level == "high":
            counts["learned_high"] += 1
        learned_at[_position(finding.anchor)] = (family, correct)

    # Errores por evento que las reglas no ven: ni anclados ni entre sus candidatos.
    anchored = {_position(finding.anchor) for finding in findings}
    seen_by_rules: set[tuple[Position, str]] = set()
    for finding in findings:
        for candidate in finding.candidates:
            position = _position(candidate.anchor)
            labelled = label_of_edit(candidate.op, candidate.after, features.events.get(position))
            if labelled is not None:
                seen_by_rules.add((position, labelled[0]))
    for position, labels in truth.labels.items():
        if position in anchored:
            continue
        for family, label in labels.items():
            if label == NONE_LABEL or (position, family) in seen_by_rules:
                continue
            counts["blind_errors"] += 1
            counts[f"blind_errors:{family}"] += 1
            learned = learned_at.get(position)
            if learned is not None and learned[0] == family:
                counts["blind_flagged"] += 1
                counts[f"blind_flagged:{family}"] += 1
                counts["blind_flagged_with_correct_fix"] += int(learned[1])
                counts[f"blind_flagged_with_correct_fix:{family}"] += int(learned[1])

    policies: dict[str, Counter[str]] = {
        policy: classify_suggestions(select_suggestions(suggested, policy), features, truth)
        for policy in POLICIES
    }
    return IncipitMeasurement(
        incipit_id=case.incipit_id,
        counts=counts,
        measures_rules=evaluate_measures(case.incipit_id, case.score, findings, truth.errors),
        measures_with_layer=evaluate_measures(
            case.incipit_id, case.score, [*findings, *learned_findings], truth.errors
        ),
        suggested=[(finding, tuple(suggestions)) for finding, suggestions in suggested],
        policies=policies,
    )


# --- Agregar -----------------------------------------------------------------------------


def _ratio(cases: int, n: int) -> dict[str, Any]:
    return {"correct": cases, "n": n, "accuracy": None if n == 0 else round(cases / n, 4)}


def _share(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 4)


def summarize(measurements: Sequence[IncipitMeasurement]) -> dict[str, Any]:
    """Las métricas de un conjunto de incipits, a partir de los recuentos."""
    counts: Counter[str] = Counter()
    policies: dict[str, Counter[str]] = {policy: Counter() for policy in POLICIES}
    rules: list[MeasureEvaluationRecord] = []
    layered: list[MeasureEvaluationRecord] = []
    for measured in measurements:
        counts.update(measured.counts)
        for policy in POLICIES:
            policies[policy].update(measured.policies.get(policy, Counter()))
        rules.extend(measured.measures_rules)
        layered.extend(measured.measures_with_layer)

    with_suggestions = counts["rule_findings_with_suggestions"]
    with_true = counts["rule_findings_with_true_candidate"]
    base_with = counts["baseline_findings_with_suggestions"]
    rule_suggestions = {
        "rule_findings": counts["rule_findings"],
        "with_candidates": counts["rule_findings_with_candidates"],
        "with_true_candidate": with_true,
        "with_suggestions": with_suggestions,
        "top1": {
            "over_findings_with_suggestions": _ratio(counts["rule_top1_correct"], with_suggestions),
            "over_true_candidate": _ratio(counts["rule_top1_correct_true_candidate"], with_true),
        },
        "top3": {
            "over_findings_with_suggestions": _ratio(counts["rule_top3_correct"], with_suggestions),
            "over_true_candidate": _ratio(counts["rule_top3_correct_true_candidate"], with_true),
        },
        "baseline_rule_order": {
            "with_suggestions": base_with,
            "top1": {
                "over_findings_with_suggestions": _ratio(
                    counts["baseline_top1_correct"], base_with
                ),
                "over_true_candidate": _ratio(
                    counts["baseline_top1_correct_true_candidate"], with_true
                ),
            },
            "top3": {
                "over_findings_with_suggestions": _ratio(
                    counts["baseline_top3_correct"], base_with
                ),
                "over_true_candidate": _ratio(
                    counts["baseline_top3_correct_true_candidate"], with_true
                ),
            },
        },
    }

    learned = {
        "count": counts["learned_findings"],
        "correct": counts["learned_correct"],
        "high_confidence": counts["learned_high"],
        "precision": _share(counts["learned_correct"], counts["learned_findings"]),
        "by_family": {
            family: {
                "count": counts[f"learned_findings:{family}"],
                "correct": counts[f"learned_correct:{family}"],
                "precision": _share(
                    counts[f"learned_correct:{family}"], counts[f"learned_findings:{family}"]
                ),
            }
            for family in FAMILIES
        },
    }

    def blind(suffix: str) -> dict[str, Any]:
        errors = counts[f"blind_errors{suffix}"]
        flagged = counts[f"blind_flagged{suffix}"]
        fixed = counts[f"blind_flagged_with_correct_fix{suffix}"]
        return {
            "errors": errors,
            "flagged": flagged,
            "flagged_with_correct_fix": fixed,
            "recall": _share(flagged, errors),
            "recall_with_correct_fix": _share(fixed, errors),
        }

    rules_report = aggregate_validation_metrics(rules)
    layer_report = aggregate_validation_metrics(layered)
    unseen = [
        (r, layer)
        for r, layer in zip(rules, layered, strict=True)
        if r.has_real_error and not r.flagged_global
    ]
    added_alarms = sum(
        1
        for r, layer in zip(rules, layered, strict=True)
        if not r.has_real_error and not r.flagged_global and layer.flagged_global
    )
    measures = {
        "definition": (
            "exp_06 (cadenza.learning.evaluate_measures): un compás tiene error si alguna "
            "corrección real va a él y está marcado si algún hallazgo está anclado en él"
        ),
        "rules": _measure_report(rules_report),
        "rules_and_layer": _measure_report(layer_report),
        "coverage_by_category": {
            category: {
                "rules": rules_report.coverage_by_category[category].to_dict(),
                "rules_and_layer": layer_report.coverage_by_category[category].to_dict(),
            }
            for category in CATEGORIES
            if category in rules_report.coverage_by_category
        },
        "measures_with_error_unseen_by_rules": len(unseen),
        "of_which_flagged_by_layer": sum(1 for _, layer in unseen if layer.flagged_global),
        "measures_without_error_flagged_only_by_layer": added_alarms,
    }

    damage: dict[str, Any] = {}
    for policy in POLICIES:
        found = policies[policy]
        damage[policy] = {
            "selected": found["selected"],
            "correct": found["correct"],
            "damaged_correct_events": found["damaged_correct_events"],
            "wrong_fix_on_erroneous_event": found["wrong_fix_on_erroneous_event"],
            "spurious_insertion": found["spurious_insertion"],
            "unlabelled": found["unlabelled"],
            "precision": _share(found["correct"], found["selected"]),
            "damaged_share_of_selected": _share(found["damaged_correct_events"], found["selected"]),
            "damaged_share_of_correct_events": _share(
                found["damaged_correct_events"], counts["correct_events"]
            ),
        }

    return {
        "incipits": len(measurements),
        "events": {
            "labelled": counts["labelled_events"],
            "correct": counts["correct_events"],
        },
        "rule_suggestions": rule_suggestions,
        "learned_findings": learned,
        "rule_blind_events": {
            **blind(""),
            "by_family": {family: blind(f":{family}") for family in FAMILIES},
        },
        "rule_blind_measures": measures,
        "damage": damage,
    }


def _measure_report(report: Any) -> dict[str, Any]:
    return {
        "total_measures": report.total_measures,
        "measures_with_real_errors": report.measures_with_real_errors,
        "measures_flagged": report.measures_flagged,
        "global_metrics": report.global_metrics.to_dict(),
    }


def measure_cases(
    cases: Sequence[IncipitCase],
    model: Any,
    validator: ValidationEngine | None = None,
) -> dict[str, Any]:
    engine = validator or ValidationEngine()
    return summarize([measure_incipit(case, model, engine) for case in cases])


def principal_metrics(summary: Mapping[str, Any]) -> dict[str, float | int | None]:
    """Las métricas principales de un resumen, para la validación cruzada y la curva."""
    ranking = summary["rule_suggestions"]
    baseline = ranking["baseline_rule_order"]
    learned = summary["learned_findings"]
    blind = summary["rule_blind_events"]
    measures = summary["rule_blind_measures"]
    damage = summary["damage"]
    return {
        "rule_top1_accuracy": ranking["top1"]["over_true_candidate"]["accuracy"],
        "rule_top3_accuracy": ranking["top3"]["over_true_candidate"]["accuracy"],
        "baseline_top1_accuracy": baseline["top1"]["over_true_candidate"]["accuracy"],
        "rule_top1_accuracy_over_suggested": ranking["top1"]["over_findings_with_suggestions"][
            "accuracy"
        ],
        "learned_findings": learned["count"],
        "learned_precision": learned["precision"],
        "blind_event_recall_with_correct_fix": blind["recall_with_correct_fix"],
        "measure_recall_rules": measures["rules"]["global_metrics"]["recall"],
        "measure_precision_rules": measures["rules"]["global_metrics"]["precision"],
        "measure_recall_rules_and_layer": measures["rules_and_layer"]["global_metrics"]["recall"],
        "measure_precision_rules_and_layer": measures["rules_and_layer"]["global_metrics"][
            "precision"
        ],
        "high_selected": damage["high"]["selected"],
        "high_precision": damage["high"]["precision"],
        "high_damaged_correct_events": damage["high"]["damaged_correct_events"],
        "first_damaged_correct_events": damage["first"]["damaged_correct_events"],
    }


def subsample_works(works: Iterable[str], fraction: float, *, seed: int) -> list[str]:
    """Una fracción de las obras, al azar con semilla y anidada: con la misma semilla, las
    del 10 % están en las del 25 %, y estas en las del 50 %."""
    if not 0.0 < fraction <= 1.0:
        raise ValueError(f"la fracción debe estar en (0, 1], no {fraction}")
    ordered = sorted(set(works))
    random.Random(seed).shuffle(ordered)
    size = max(1, math.ceil(round(fraction * len(ordered), 9)))
    return sorted(ordered[:size])
