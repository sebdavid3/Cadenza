"""Métricas de evaluación del catálogo de validación sobre errores reales (ADR-0008, Issue #18, D8).

Cuantifica la utilidad real del catálogo de validación sintáctico/semántico
(`ValidationEngine`) frente a las discrepancias reales de OMR derivadas del diff
con el ground truth (`derive_edit_events`). Calcula precisión, recall y F1 a nivel
de compás tanto globalmente como por regla, y analiza la cobertura por tipo de error.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from cadenza.domain import (
    EditEvent,
    EditOp,
    Finding,
    Provenance,
    ScoreDocument,
    ScoreIR,
    build_anchor_index,
)
from cadenza.learning.alignment import derive_edit_events
from cadenza.validation import ValidationEngine


@dataclass(frozen=True, slots=True)
class BinaryMetrics:
    """Métricas de clasificación binaria a nivel de compás."""

    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return round(self.tp / denom, 4) if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return round(self.tp / denom, 4) if denom > 0 else 0.0

    @property
    def f1(self) -> float:
        p = self.precision
        r = self.recall
        return round(2 * p * r / (p + r), 4) if (p + r) > 0 else 0.0

    @property
    def accuracy(self) -> float:
        denom = self.total
        return round((self.tp + self.tn) / denom, 4) if denom > 0 else 0.0

    @property
    def specificity(self) -> float:
        denom = self.tn + self.fp
        return round(self.tn / denom, 4) if denom > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "total": self.total,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "accuracy": self.accuracy,
            "specificity": self.specificity,
        }


def compute_binary_metrics(tp: int, fp: int, fn: int, tn: int) -> BinaryMetrics:
    """Calcula métricas binarias estándar a partir de la matriz de confusión."""
    return BinaryMetrics(tp=tp, fp=fp, fn=fn, tn=tn)


@dataclass(frozen=True, slots=True)
class MeasureEvaluationRecord:
    """Evaluación de un compás individual respecto a errores reales y hallazgos."""

    score_id: str
    part_index: int
    staff_index: int
    measure_number: int
    has_real_error: bool
    error_operations: tuple[str, ...]
    error_categories: tuple[str, ...]
    flagged_global: bool
    flagged_rules: tuple[str, ...]

    def to_row(self) -> dict[str, Any]:
        return {
            "score_id": self.score_id,
            "part_index": self.part_index,
            "staff_index": self.staff_index,
            "measure_number": self.measure_number,
            "has_real_error": self.has_real_error,
            "error_operations": ",".join(self.error_operations),
            "error_categories": ",".join(self.error_categories),
            "flagged_global": self.flagged_global,
            "flagged_rules": ",".join(self.flagged_rules),
        }


@dataclass(frozen=True, slots=True)
class ErrorCategoryCoverage:
    """Cobertura de detección del validador para una categoría de error."""

    category: str
    total_measures_with_error: int
    detected_measures: int
    coverage_rate: float
    detected_by_rules: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "total_measures_with_error": self.total_measures_with_error,
            "detected_measures": self.detected_measures,
            "coverage_rate": self.coverage_rate,
            "detected_by_rules": self.detected_by_rules,
        }


@dataclass(frozen=True, slots=True)
class ValidationEvaluationReport:
    """Informe consolidado de evaluación del catálogo de validación."""

    total_scores: int
    total_measures: int
    measures_with_real_errors: int
    measures_flagged: int
    global_metrics: BinaryMetrics
    metrics_by_rule: dict[str, BinaryMetrics]
    coverage_by_category: dict[str, ErrorCategoryCoverage]
    coverage_analysis: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_scores": self.total_scores,
            "total_measures": self.total_measures,
            "measures_with_real_errors": self.measures_with_real_errors,
            "measures_flagged": self.measures_flagged,
            "global_metrics": self.global_metrics.to_dict(),
            "metrics_by_rule": {rule: m.to_dict() for rule, m in self.metrics_by_rule.items()},
            "coverage_by_category": {
                cat: cov.to_dict() for cat, cov in self.coverage_by_category.items()
            },
            "coverage_analysis": self.coverage_analysis,
        }


def categorize_edit_op(op: EditOp | str) -> str:
    """Mapea una operación de edición a una categoría semántica de error musical."""
    val = op.value if hasattr(op, "value") else str(op)
    if val == EditOp.SET_DURATION.value:
        return "duration"
    if val == EditOp.SET_ACCIDENTAL.value:
        return "accidental"
    if val == EditOp.SET_PITCH.value:
        return "pitch"
    if val in (EditOp.INSERT_EVENT.value, EditOp.DELETE_EVENT.value):
        return "structure"
    if val in (EditOp.SET_KEY.value, EditOp.SET_CLEF.value):
        return "key_clef"
    return "other"


def evaluate_score_measures(
    score_id: str,
    score_pred: ScoreIR,
    findings: Sequence[Finding],
    edits: Sequence[EditEvent],
) -> list[MeasureEvaluationRecord]:
    """Evalúa compás a compás la partitura predicha contra hallazgos y ediciones reales."""
    records: list[MeasureEvaluationRecord] = []

    for part_idx, part in enumerate(score_pred.parts):
        for staff_idx, staff in enumerate(part.staves):
            for meas in staff.measures:
                m_num = meas.number

                # Ediciones reales dirigidas a este compás
                meas_edits = [
                    e
                    for e in edits
                    if e.anchor.part == part_idx
                    and e.anchor.staff == staff_idx
                    and e.anchor.measure == m_num
                ]
                has_error = len(meas_edits) > 0
                ops = tuple(e.op.value if hasattr(e.op, "value") else str(e.op) for e in meas_edits)
                cats = tuple(sorted({categorize_edit_op(e.op) for e in meas_edits}))

                # Hallazgos del validador dirigidos a este compás
                meas_findings = [
                    f
                    for f in findings
                    if f.anchor.part == part_idx
                    and f.anchor.staff == staff_idx
                    and f.anchor.measure == m_num
                ]
                flagged_global = len(meas_findings) > 0
                flagged_rules = tuple(sorted({f.rule_id for f in meas_findings}))

                records.append(
                    MeasureEvaluationRecord(
                        score_id=score_id,
                        part_index=part_idx,
                        staff_index=staff_idx,
                        measure_number=m_num,
                        has_real_error=has_error,
                        error_operations=ops,
                        error_categories=cats,
                        flagged_global=flagged_global,
                        flagged_rules=flagged_rules,
                    )
                )

    return records


def aggregate_validation_metrics(
    records: Sequence[MeasureEvaluationRecord],
    known_rules: Sequence[str] | None = None,
) -> ValidationEvaluationReport:
    """Calcula el informe agregado de métricas globales, por regla y por categoría."""
    distinct_scores = len({r.score_id for r in records})
    total_measures = len(records)
    measures_with_real_errors = sum(1 for r in records if r.has_real_error)
    measures_flagged = sum(1 for r in records if r.flagged_global)

    # 1. Matriz de confusión global
    g_tp = sum(1 for r in records if r.has_real_error and r.flagged_global)
    g_fp = sum(1 for r in records if not r.has_real_error and r.flagged_global)
    g_fn = sum(1 for r in records if r.has_real_error and not r.flagged_global)
    g_tn = sum(1 for r in records if not r.has_real_error and not r.flagged_global)
    global_metrics = compute_binary_metrics(g_tp, g_fp, g_fn, g_tn)

    # 2. Métricas por regla
    rules_set: set[str] = set(known_rules or ())
    for r in records:
        rules_set.update(r.flagged_rules)
    sorted_rules = sorted(rules_set)

    metrics_by_rule: dict[str, BinaryMetrics] = {}
    for rule in sorted_rules:
        r_tp = sum(1 for r in records if r.has_real_error and rule in r.flagged_rules)
        r_fp = sum(1 for r in records if not r.has_real_error and rule in r.flagged_rules)
        r_fn = sum(1 for r in records if r.has_real_error and rule not in r.flagged_rules)
        r_tn = sum(1 for r in records if not r.has_real_error and rule not in r.flagged_rules)
        metrics_by_rule[rule] = compute_binary_metrics(r_tp, r_fp, r_fn, r_tn)

    # 3. Cobertura por categoría de error
    all_categories = {"duration", "accidental", "pitch", "structure", "key_clef"}
    for r in records:
        all_categories.update(r.error_categories)
    sorted_cats = sorted(all_categories)

    coverage_by_category: dict[str, ErrorCategoryCoverage] = {}
    for cat in sorted_cats:
        meas_in_cat = [r for r in records if cat in r.error_categories]
        total_in_cat = len(meas_in_cat)
        detected = [r for r in meas_in_cat if r.flagged_global]
        det_count = len(detected)
        rate = round(det_count / total_in_cat, 4) if total_in_cat > 0 else 0.0

        rule_counts: dict[str, int] = {}
        for r in detected:
            for rule in r.flagged_rules:
                rule_counts[rule] = rule_counts.get(rule, 0) + 1

        coverage_by_category[cat] = ErrorCategoryCoverage(
            category=cat,
            total_measures_with_error=total_in_cat,
            detected_measures=det_count,
            coverage_rate=rate,
            detected_by_rules=rule_counts,
        )

    # 4. Análisis cualitativo de la cobertura
    analysis = {
        "what_catalog_covers": (
            "El catálogo simbólico detecta primordialmente errores que violan la gramática "
            "musical formal: compases incompletos o excedidos en duración (regla measure.balance), "
            "inconsistencias entre alteraciones accidentales y armadura tonal (key.consistency), "
            "alturas que desbordan la tesitura de la clave (pitch.range), solapamientos "
            "polifónicos temporales (voice.collision) y ligaduras huérfanas (tie.resolution)."
        ),
        "what_catalog_cannot_cover": (
            "El catálogo simbólico no puede detectar errores de sustitución sintácticamente "
            "válidos: notas reconocidas con altura o alteración incorrecta que permanecen dentro "
            "de la tonalidad y tesitura (p. ej. reconocer E4 en vez de C4), o sustituciones de "
            "duración que se compensan dentro del mismo compás. Estos errores son musicalmente "
            "gramaticales y requieren señal visual del modelo OMR o feedback del corrector humano."
        ),
        "false_positive_nature": (
            "Los falsos positivos en el corpus musical histórico provienen mayoritariamente de "
            "convenciones notacionales de incipits: anacrusas iniciales o compases finales "
            "incompletos no declarados explícitamente como tales en la métrica, que el validador "
            "señala con razón como desbalance respecto a la armadura formal de 4/4."
        ),
    }

    return ValidationEvaluationReport(
        total_scores=distinct_scores,
        total_measures=total_measures,
        measures_with_real_errors=measures_with_real_errors,
        measures_flagged=measures_flagged,
        global_metrics=global_metrics,
        metrics_by_rule=metrics_by_rule,
        coverage_by_category=coverage_by_category,
        coverage_analysis=analysis,
    )


def evaluate_pair(
    score_id: str,
    score_pred: ScoreIR,
    score_gt: ScoreIR,
    validator: ValidationEngine,
) -> list[MeasureEvaluationRecord]:
    """Evalúa un par predicho vs ground truth ejecutando el validador y el diff."""
    doc = ScoreDocument(
        id=score_id,
        score=score_pred,
        anchors=build_anchor_index(score_pred),
        provenance=Provenance(omr_engine="homr"),
    )
    findings = validator.validate(doc)
    edits = derive_edit_events(score_pred, score_gt, document_id=score_id)
    return evaluate_score_measures(score_id, score_pred, findings, edits)
