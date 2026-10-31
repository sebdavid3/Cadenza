"""Entrenamiento, evaluación y promoción de la capa de sugerencias, fuera de línea (ADR-0036).

Cuenta las frecuencias de las correcciones del corpus de #255 por contexto, elige el umbral
de cada familia por validación cruzada de 5 pliegues agrupados por obra dentro de la
partición de entrenamiento, mide sobre la partición de prueba fija y escribe el artefacto
JSON que la API carga. Importa los rasgos de `cadenza.validation.learned`, nunca al revés.

Todas las métricas son medidas (CLAUDE.md §8): si no hay datos con que medir, el resultado
es None y la promoción se rechaza; nunca una cifra de reserva.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Final

from cadenza.application.suggestions import suggest as suggest_with_layer
from cadenza.domain import (
    Anchor,
    Clef,
    EditOp,
    Event,
    EventKind,
    KeySignature,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Staff,
    Tie,
    TimeSignature,
    build_anchor_index,
    materialize,
)
from cadenza.validation import RULES_CATALOG_VERSION, ValidationEngine
from cadenza.validation.learned import (
    ARTIFACT_FORMAT,
    ARTIFACT_FORMAT_VERSION,
    FAMILIES,
    FEATURE_VERSION,
    INSERTION,
    LEARNED_PREFIX,
    MODEL_TYPE,
    NONE_LABEL,
    FrequencyBackoffModel,
    ScoreFeatures,
    context_key,
    discretize,
    insertion_label,
    label_of_edit,
    labels_from_correction,
)

from .alignment import derive_edit_events, is_structurally_equal
from .config import compute_config_hash
from .correction_corpus import assign_split, build_correction_records
from .primus import primus_work_id

THRESHOLD_GRID: Final[tuple[float, ...]] = tuple(round(0.05 * step, 2) for step in range(1, 20))
_ACCIDENTAL_KEYS: Final[tuple[str, ...]] = (
    "accidental",
    "key_accidental",
    "accidental_vs_key",
    "previous_accidental_same_step",
)


class SuggestionTrainingError(ValueError):
    """El corpus o la configuración no permiten entrenar o medir."""


@dataclass(frozen=True, slots=True)
class SuggestionsConfig:
    """Configuración versionada del entrenamiento (`configs/learning/suggestions.json`)."""

    seed: int
    alpha: float
    min_support: int
    folds: int
    target_precision: float
    high_precision: float
    min_alarms: int
    learned_families: tuple[str, ...]
    levels: Mapping[str, tuple[tuple[str, ...], ...]]
    raw: Mapping[str, Any]

    @property
    def config_hash(self) -> str:
        return compute_config_hash(dict(self.raw))

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> SuggestionsConfig:
        levels_raw = raw.get("levels") or {}
        levels: dict[str, tuple[tuple[str, ...], ...]] = {}
        for family in (*FAMILIES, INSERTION):
            family_levels = levels_raw.get(family)
            if not family_levels:
                raise SuggestionTrainingError(f"faltan los niveles de retroceso de {family}")
            parsed = tuple(tuple(str(name) for name in level) for level in family_levels)
            if parsed[-1]:
                raise SuggestionTrainingError(f"el último nivel de {family} debe ser el vacío")
            levels[family] = parsed
        learned = tuple(str(f) for f in raw.get("learned_families") or ())
        unknown = sorted(set(learned) - set(FAMILIES))
        if unknown:
            raise SuggestionTrainingError(f"familias desconocidas: {', '.join(unknown)}")
        config = cls(
            seed=int(raw["seed"]),
            alpha=float(raw["alpha"]),
            min_support=int(raw["min_support"]),
            folds=int(raw.get("folds", 5)),
            target_precision=float(raw["target_precision"]),
            high_precision=float(raw["high_precision"]),
            min_alarms=int(raw.get("min_alarms", 1)),
            learned_families=learned,
            levels=levels,
            raw=dict(raw),
        )
        if config.folds < 2:
            raise SuggestionTrainingError("la validación cruzada necesita al menos 2 pliegues")
        return config


def load_suggestions_config(path: Path) -> SuggestionsConfig:
    return SuggestionsConfig.from_mapping(json.loads(path.read_text(encoding="utf-8")))


# --- El corpus -------------------------------------------------------------------------------


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_corpus(path: Path) -> list[dict[str, Any]]:
    """Los registros de un corpus JSONL; falla con un mensaje claro si falta o está vacío."""
    if not path.is_file():
        raise SuggestionTrainingError(f"no existe el corpus: {path}")
    records = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if not records:
        raise SuggestionTrainingError(f"el corpus está vacío: {path}")
    return records


def work_of(record: Mapping[str, Any]) -> str:
    """La obra de un registro, para agrupar pliegues y particiones: la página de origen de una
    sesión de Cadenza o el registro RISM de un incipit de PrIMuS."""
    work = record.get("work_id")
    if work:
        return str(work)
    return primus_work_id(str(record["incipit_id"]))


def fold_of(work: str, *, seed: int, folds: int) -> int:
    digest = hashlib.sha256(f"{seed}:fold:{work}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % folds


def _usable(record: Mapping[str, Any], kind: str, split: str) -> bool:
    return (
        record.get("record") == kind
        and bool(record.get("verified"))
        and bool(record.get("aligned"))
        and record.get("split") == split
    )


def _incipit_groups(records: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        groups.setdefault(str(record["incipit_id"]), []).append(record)
    return groups


def _position(anchor: Mapping[str, Any]) -> tuple[int, int, int, int, int]:
    return (
        int(anchor["part"]),
        int(anchor["staff"]),
        int(anchor["measure"]),
        int(anchor["voice"]),
        int(anchor["event_index"]),
    )


def _neighbour(read: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if read is None:
        return None
    return {
        "kind": read.get("kind"),
        "pitch": read.get("pitch"),
        "duration_beats": read.get("duration_beats"),
    }


def _advance(read: Mapping[str, Any]) -> Fraction:
    duration = read.get("duration_beats")
    if read.get("is_chord") or duration is None:
        return Fraction(0)
    return Fraction(str(duration))


@dataclass(frozen=True, slots=True)
class Example:
    """Un ejemplo de una familia: los rasgos de un evento (o hueco) y su etiqueta."""

    family: str
    features: Mapping[str, str]
    label: str
    work: str


def gap_examples(records: Sequence[Mapping[str, Any]]) -> list[Example]:
    """Ejemplos de la familia de inserciones de un incipit: cada hueco de cada voz, con la
    inserción que falta ahí o `none`.

    El contexto de un hueco es el mismo que calcula la inferencia: el de su evento siguiente
    sin alteración y con él como vecino siguiente, o, al final de la voz, el del último
    evento con el índice y el inicio desplazados.
    """
    examples: list[Example] = []
    events = sorted(
        (r for r in records if r.get("record") == "event" and r.get("context") is not None),
        key=lambda r: _position(r["anchor"]),
    )
    positives: dict[tuple[int, int, int, int, int], list[str]] = {}
    for record in records:
        if record.get("record") != "insertion":
            continue
        event = (record.get("correction") or {}).get("event") or {}
        label = insertion_label(event.get("kind"), event.get("duration_beats"))
        if label is not None:
            positives.setdefault(_position(record["anchor"]), []).append(label)
    for index, record in enumerate(events):
        context = dict(record["context"])
        position = _position(record["anchor"])
        work = work_of(record)
        gap = {
            **context,
            **dict.fromkeys(_ACCIDENTAL_KEYS),
            "next": _neighbour(record["read"]),
        }
        examples.extend(_gap_labels(gap, positives.get(position), work))
        following = events[index + 1] if index + 1 < len(events) else None
        last_in_voice = following is None or _position(following["anchor"])[:4] != position[:4]
        if last_in_voice:
            end = (*position[:4], position[4] + 1)
            onset = Fraction(str(context["onset_beats"])) + _advance(record["read"])
            end_gap = {
                **context,
                **dict.fromkeys(_ACCIDENTAL_KEYS),
                "event_index": end[4],
                "onset_beats": str(onset),
                "prev": _neighbour(record["read"]),
            }
            examples.extend(_gap_labels(end_gap, positives.get(end), work))
    return examples


def _gap_labels(context: Mapping[str, Any], labels: list[str] | None, work: str) -> list[Example]:
    features = discretize(None, context)
    if not labels:
        return [Example(INSERTION, features, NONE_LABEL, work)]
    return [Example(INSERTION, features, label, work) for label in labels]


def event_examples(record: Mapping[str, Any]) -> list[Example]:
    features = discretize(record["read"], record["context"])
    labels = labels_from_correction(record["read"], record["context"], record.get("correction"))
    work = work_of(record)
    return [Example(family, features, label, work) for family, label in labels.items()]


def training_examples(records: Sequence[Mapping[str, Any]], *, split: str) -> list[Example]:
    """Los ejemplos de entrenamiento: registros verificados y alineados de la partición."""
    examples: list[Example] = []
    for incipit_records in _incipit_groups(records).values():
        usable = [r for r in incipit_records if _usable(r, "event", split)]
        for record in usable:
            examples.extend(event_examples(record))
        insertions = [r for r in incipit_records if _usable(r, "insertion", split)]
        if usable:
            examples.extend(gap_examples([*usable, *insertions]))
    return examples


# --- Las tablas y el artefacto ---------------------------------------------------------------


def count_tables(
    examples: Iterable[Example], config: SuggestionsConfig
) -> dict[str, dict[str, Any]]:
    """Las tablas de frecuencias de cada familia, nivel a nivel."""
    tables: dict[str, list[dict[str, Counter[str]]]] = {
        family: [{} for _ in config.levels[family]] for family in (*FAMILIES, INSERTION)
    }
    for example in examples:
        for level, table in zip(config.levels[example.family], tables[example.family], strict=True):
            table.setdefault(context_key(example.features, level), Counter())[example.label] += 1
    return {
        family: {
            "levels": [list(level) for level in config.levels[family]],
            "tables": [
                {key: dict(sorted(counts.items())) for key, counts in sorted(table.items())}
                for table in tables[family]
            ],
            "threshold": None,
            "high_threshold": None,
            "active": False,
        }
        for family in (*FAMILIES, INSERTION)
    }


def _artifact(families: Mapping[str, Any], config: SuggestionsConfig) -> dict[str, Any]:
    return {
        "format": ARTIFACT_FORMAT,
        "format_version": ARTIFACT_FORMAT_VERSION,
        "model_type": MODEL_TYPE,
        "feature_version": FEATURE_VERSION,
        "params": {"alpha": config.alpha, "min_support": config.min_support},
        "families": dict(families),
    }


def _precision_at(
    scored: Sequence[tuple[int, float, bool]], threshold: float, folds: int
) -> tuple[float | None, int]:
    """Precisión media entre pliegues (los que tienen alarmas) y alarmas totales."""
    per_fold: list[float] = []
    alarms_total = 0
    for fold in range(folds):
        alarms = [correct for f, p, correct in scored if f == fold and p >= threshold]
        if alarms:
            per_fold.append(sum(alarms) / len(alarms))
            alarms_total += len(alarms)
    if not per_fold:
        return None, 0
    return sum(per_fold) / len(per_fold), alarms_total


def choose_thresholds(
    examples: Sequence[Example], config: SuggestionsConfig
) -> dict[str, dict[str, Any]]:
    """El umbral de cada familia por validación cruzada agrupada por obra (ADR-0036 §6).

    El menor umbral cuya precisión media entre pliegues es al menos `target_precision` (y
    `high_precision` para `confidence_level` alto), con al menos `min_alarms` alarmas. Una
    familia sin umbral que lo alcance queda apagada.
    """
    scored: dict[str, list[tuple[int, float, bool]]] = {family: [] for family in FAMILIES}
    for fold in range(config.folds):
        train = [
            e for e in examples if fold_of(e.work, seed=config.seed, folds=config.folds) != fold
        ]
        held = [
            e for e in examples if fold_of(e.work, seed=config.seed, folds=config.folds) == fold
        ]
        if not train or not held:
            continue
        model = FrequencyBackoffModel(_artifact(count_tables(train, config), config), version="cv")
        for example in held:
            if example.family not in scored:
                continue
            best = model.best(example.family, example.features)
            if best is None:
                continue
            label, score = best
            scored[example.family].append((fold, score.probability, label == example.label))
    report: dict[str, dict[str, Any]] = {}
    for family in FAMILIES:
        found: dict[str, float | None] = {"threshold": None, "high_threshold": None}
        curve: list[dict[str, Any]] = []
        for threshold in THRESHOLD_GRID:
            precision, alarms = _precision_at(scored[family], threshold, config.folds)
            curve.append({"threshold": threshold, "precision": precision, "alarms": alarms})
            if precision is None or alarms < config.min_alarms:
                continue
            if found["threshold"] is None and precision >= config.target_precision:
                found["threshold"] = threshold
            if found["high_threshold"] is None and precision >= config.high_precision:
                found["high_threshold"] = threshold
        report[family] = {**found, "scored": len(scored[family]), "curve": curve}
    return report


def train(
    records: Sequence[Mapping[str, Any]],
    config: SuggestionsConfig,
    *,
    dataset_hash: str,
) -> dict[str, Any]:
    """El artefacto de la capa: tablas de toda la partición de entrenamiento y umbrales por
    validación cruzada. Determinista: el mismo corpus y la misma configuración dan los mismos
    bytes."""
    examples = training_examples(records, split="train")
    if not any(e.family in FAMILIES for e in examples):
        raise SuggestionTrainingError(
            "el corpus no tiene registros `event` verificados y alineados de entrenamiento"
        )
    families = count_tables(examples, config)
    thresholds = choose_thresholds(examples, config)
    for family in FAMILIES:
        chosen = thresholds[family]
        families[family]["threshold"] = chosen["threshold"]
        families[family]["high_threshold"] = chosen["high_threshold"]
        families[family]["active"] = (
            family in config.learned_families and chosen["threshold"] is not None
        )
    artifact = _artifact(families, config)
    artifact["training"] = {
        "dataset_hash": dataset_hash,
        "config_hash": config.config_hash,
        "seed": config.seed,
        "examples": dict(sorted(Counter(e.family for e in examples).items())),
        "works": len({e.work for e in examples}),
        # Los incipits con que se entrenó: `evaluate` comprueba que ninguno esté en la prueba.
        "train_incipits": sorted(
            {str(r["incipit_id"]) for r in records if _usable(r, "event", "train")}
        ),
        "cross_validation": {
            "folds": config.folds,
            "grouped_by": "obra (work_of)",
            "target_precision": config.target_precision,
            "high_precision": config.high_precision,
            "min_alarms": config.min_alarms,
            "families": thresholds,
        },
    }
    return artifact


def artifact_bytes(artifact: Mapping[str, Any]) -> bytes:
    return (json.dumps(artifact, sort_keys=True, ensure_ascii=False, indent=1) + "\n").encode(
        "utf-8"
    )


# --- Evaluación ------------------------------------------------------------------------------


def _clef(name: str | None) -> Clef | None:
    if not name:
        return None
    sign, rest = name[0], name[1:]
    line, octave = rest, 0
    for marker in ("+", "-"):
        if marker in rest[1:]:
            cut = rest.index(marker, 1)
            line, octave = rest[:cut], int(rest[cut:])
    return Clef(sign=sign, line=int(line), octave_change=octave)


def _time(value: str | None) -> TimeSignature | None:
    if not value:
        return None
    beats, beat_type = value.split("/")
    return TimeSignature(int(beats), int(beat_type))


def reconstruct_score(records: Sequence[Mapping[str, Any]]) -> ScoreIR:
    """El `ScoreIR` leído de un incipit, a partir de sus registros `event` (lo leído y su
    contexto). La métrica va en cada compás, y la clave y la armadura donde cambian, como las
    deja el lector de MusicXML."""
    events = sorted(
        (r for r in records if r.get("record") == "event"), key=lambda r: _position(r["anchor"])
    )
    staves: dict[tuple[int, int], dict[int, list[Mapping[str, Any]]]] = {}
    for record in events:
        part, staff, measure, _, _ = _position(record["anchor"])
        staves.setdefault((part, staff), {}).setdefault(measure, []).append(record)
    parts: dict[int, list[Staff]] = {}
    for (part, staff), measures in sorted(staves.items()):
        built: list[Measure] = []
        previous_clef: Clef | None = None
        previous_key: int | None = None
        for number, measure_records in sorted(measures.items()):
            context = measure_records[0]["context"]
            clef = _clef(context.get("clef"))
            fifths = int(context.get("key_fifths") or 0)
            built.append(
                Measure(
                    number=number,
                    events=tuple(_event(r) for r in measure_records),
                    time_signature=_time(context.get("time_signature")),
                    clef=clef if clef != previous_clef else None,
                    key_signature=KeySignature(fifths=fifths) if fifths != previous_key else None,
                )
            )
            previous_clef, previous_key = clef, fifths
        parts.setdefault(part, []).append(Staff(id=f"P{part}-S{staff}", measures=tuple(built)))
    return ScoreIR(
        parts=tuple(
            Part(id=f"P{part}", staves=tuple(staves_)) for part, staves_ in sorted(parts.items())
        )
    )


def _event(record: Mapping[str, Any]) -> Event:
    read = record["read"]
    duration = read.get("duration_beats")
    tie = read.get("tie")
    return Event(
        kind=EventKind(read["kind"]),
        voice=int(record["anchor"]["voice"]),
        pitch=read.get("pitch"),
        duration_beats=None if duration is None else Fraction(str(duration)),
        tie=None if tie is None else Tie(str(tie)),
        is_chord=bool(read.get("is_chord")),
        hidden=bool(read.get("hidden")),
    )


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None:
        return None
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def evaluate(
    model: FrequencyBackoffModel,
    records: Sequence[Mapping[str, Any]],
    *,
    split: str = "test",
) -> dict[str, Any]:
    """Métricas medidas sobre la partición `split`, frente a la línea base de no tener capa.

    - Por familia: precisión, *recall* y F1 de los posibles errores propios con su umbral
      (sobre todos los eventos, sin la exclusión por las reglas).
    - De punta a punta, sobre el documento leído reconstruido: las reglas actuales, la capa
      con sus exclusiones, cuántos errores que las reglas no ven señala, y la exactitud de la
      primera sugerencia en los hallazgos de regla cuyo arreglo verdadero está entre los
      candidatos (la línea base es el primer candidato de la regla).
    """
    by_incipit = _incipit_groups(records)
    validator = ValidationEngine()
    family_counts = {f: Counter[str]() for f in FAMILIES}
    pooled = Counter[str]()
    active = set(model.active_families())
    blind = Counter[str]()
    ranking = Counter[str]()
    end_to_end = Counter[str]()
    incipits = 0
    skipped: dict[str, str] = {}
    for incipit, incipit_records in sorted(by_incipit.items()):
        usable = [r for r in incipit_records if _usable(r, "event", split)]
        if not usable:
            continue
        incipits += 1
        truths: dict[tuple[int, int, int, int, int], dict[str, str]] = {}
        for record in usable:
            labels = labels_from_correction(
                record["read"], record["context"], record.get("correction")
            )
            position = _position(record["anchor"])
            truths[position] = labels
            features = discretize(record["read"], record["context"])
            for family in FAMILIES:
                truth = labels.get(family)
                if truth is None:
                    continue
                counts = family_counts[family]
                if truth != NONE_LABEL:
                    counts["errors"] += 1
                    pooled["errors"] += 1
                family_model = model.family(family)
                threshold = None if family_model is None else family_model.threshold
                best = model.best(family, features)
                if threshold is None or best is None or best[1].probability < threshold:
                    continue
                counts["alarms"] += 1
                correct = best[0] == truth
                counts["true_positives"] += int(correct)
                if family in active:
                    pooled["alarms"] += 1
                    pooled["true_positives"] += int(correct)
        gaps: dict[tuple[int, int, int, int, int], set[str]] = {}
        for record in incipit_records:
            if _usable(record, "insertion", split):
                event = (record.get("correction") or {}).get("event") or {}
                label = insertion_label(event.get("kind"), event.get("duration_beats"))
                if label is not None:
                    gaps.setdefault(_position(record["anchor"]), set()).add(label)
        try:
            score = reconstruct_score([r for r in incipit_records if r.get("record") == "event"])
            document = ScoreDocument(
                id=incipit,
                score=score,
                anchors=build_anchor_index(score),
                provenance=Provenance(omr_engine="corpus"),
            )
            findings = validator.validate(document)
            # El mismo camino que producción: la capa y el filtro de admisibilidad de los
            # casos de uso (validate_after, sin duplicados, tres por hallazgo).
            suggested = suggest_with_layer(document, findings, model)
        except (ValueError, KeyError, IndexError) as exc:
            skipped[incipit] = f"{type(exc).__name__}: {exc}"
            continue
        _score_end_to_end(suggested, findings, truths, gaps, score, blind, ranking, end_to_end)

    families: dict[str, Any] = {}
    for family in FAMILIES:
        counts = family_counts[family]
        family_model = model.family(family)
        precision = _ratio(counts["true_positives"], counts["alarms"])
        recall = _ratio(counts["true_positives"], counts["errors"])
        families[family] = {
            "threshold": None if family_model is None else family_model.threshold,
            "active": family in active,
            "alarms": counts["alarms"],
            "true_positives": counts["true_positives"],
            "errors": counts["errors"],
            "precision": precision,
            "recall": recall,
            "f1": _f1(precision, recall),
        }
    precision = _ratio(pooled["true_positives"], pooled["alarms"])
    recall = _ratio(pooled["true_positives"], pooled["errors"])
    learned_f1 = _f1(precision, recall)
    if learned_f1 is None and pooled["errors"]:
        learned_f1 = 0.0  # sin alarmas no hay aciertos: F1 nulo, medido
    top1 = _ratio(ranking["top1_correct"], ranking["with_true_candidate"])
    baseline_top1 = _ratio(ranking["baseline_top1_correct"], ranking["with_true_candidate"])
    return {
        "split": split,
        "simulated": False,
        # Lo que mide de punta a punta depende de las reglas (ADR-0040 §14).
        "rules_version": validator.rules_version,
        "rules_catalog_version": RULES_CATALOG_VERSION,
        "incipits": incipits,
        "skipped_incipits": skipped,
        "families": families,
        "learned": {
            "active_families": sorted(active),
            "alarms": pooled["alarms"],
            "true_positives": pooled["true_positives"],
            "errors": pooled["errors"],
            "precision": precision,
            "recall": recall,
            "f1": learned_f1,
        },
        "rule_blind": {
            "errors": blind["errors"],
            "flagged": blind["flagged"],
            "flagged_with_correct_fix": blind["flagged_with_correct_fix"],
        },
        "rule_findings": {
            "with_candidates": ranking["with_candidates"],
            "with_true_candidate": ranking["with_true_candidate"],
            "top1_correct": ranking["top1_correct"],
            "top1_accuracy": top1,
            "baseline_top1_correct": ranking["baseline_top1_correct"],
            "baseline_top1_accuracy": baseline_top1,
        },
        "end_to_end": {
            "learned_findings": end_to_end["learned_findings"],
            "correct": end_to_end["correct"],
            "precision": _ratio(end_to_end["correct"], end_to_end["learned_findings"]),
        },
        "baseline": {
            "description": (
                "sin capa: ningún posible error propio y el primer candidato de la regla"
            ),
            "learned_f1": 0.0 if pooled["errors"] else None,
            "top1_accuracy": baseline_top1,
        },
    }


def _is_true(
    op: EditOp,
    after: Mapping[str, Any] | None,
    anchor: Anchor,
    features: ScoreFeatures,
    truths: Mapping[tuple[int, int, int, int, int], Mapping[str, str]],
    gaps: Mapping[tuple[int, int, int, int, int], set[str]],
) -> bool:
    position = (anchor.part, anchor.staff, anchor.measure, anchor.voice, anchor.event_index)
    if op is EditOp.INSERT_EVENT:
        data = after or {}
        label = insertion_label(data.get("kind"), data.get("duration_beats"))
        return label is not None and label in gaps.get(position, set())
    labelled = label_of_edit(op, after, features.events.get(position))
    if labelled is None:
        return False
    family, label = labelled
    return truths.get(position, {}).get(family) == label


def _score_end_to_end(
    suggested: Sequence[tuple[Any, Sequence[Any]]],
    findings: Sequence[Any],
    truths: Mapping[tuple[int, int, int, int, int], Mapping[str, str]],
    gaps: Mapping[tuple[int, int, int, int, int], set[str]],
    score: ScoreIR,
    blind: Counter[str],
    ranking: Counter[str],
    end_to_end: Counter[str],
) -> None:
    features = ScoreFeatures.of(score)
    # Lo que ven las reglas, como la exclusión de la capa (ADR-0036 §3.3 y enmienda 4): el
    # ancla de un hallazgo, todas las familias; un candidato, solo la suya.
    anchored: set[tuple[int, int, int, int, int]] = set()
    seen_by_rules: set[tuple[tuple[int, int, int, int, int], str]] = set()
    for finding in findings:
        a = finding.anchor
        anchored.add((a.part, a.staff, a.measure, a.voice, a.event_index))
        for candidate in finding.candidates:
            c = candidate.anchor
            position = (c.part, c.staff, c.measure, c.voice, c.event_index)
            labelled = label_of_edit(candidate.op, candidate.after, features.events.get(position))
            if labelled is not None:
                seen_by_rules.add((position, labelled[0]))
    learned_at: dict[tuple[int, int, int, int, int], tuple[str, bool]] = {}
    for finding, suggestions in suggested:
        if finding.rule_id.startswith(LEARNED_PREFIX):
            end_to_end["learned_findings"] += 1
            suggestion = suggestions[0]
            correct = _is_true(
                suggestion.op, suggestion.after, suggestion.anchor, features, truths, gaps
            )
            end_to_end["correct"] += int(correct)
            a = finding.anchor
            learned_at[(a.part, a.staff, a.measure, a.voice, a.event_index)] = (
                finding.rule_id.removeprefix(LEARNED_PREFIX),
                correct,
            )
            continue
        if not finding.candidates:
            continue
        ranking["with_candidates"] += 1
        true_candidates = [
            c
            for c in finding.candidates
            if _is_true(c.op, c.after, c.anchor, features, truths, gaps)
        ]
        if not true_candidates:
            continue
        ranking["with_true_candidate"] += 1
        first = finding.candidates[0]
        ranking["baseline_top1_correct"] += int(
            _is_true(first.op, first.after, first.anchor, features, truths, gaps)
        )
        if suggestions:
            top = suggestions[0]
            ranking["top1_correct"] += int(
                _is_true(top.op, top.after, top.anchor, features, truths, gaps)
            )
    for position, labels in truths.items():
        if position in anchored:
            continue
        for family, label in labels.items():
            if label == NONE_LABEL or (position, family) in seen_by_rules:
                continue
            blind["errors"] += 1
            learned = learned_at.get(position)
            if learned is not None and learned[0] == family:
                blind["flagged"] += 1
                blind["flagged_with_correct_fix"] += int(learned[1])


# --- Promoción -------------------------------------------------------------------------------


def _rules_of(metrics: Mapping[str, Any]) -> tuple[object, object]:
    """Con qué reglas se midió un informe; sin versión del catálogo, el 1 (anterior a #246)."""
    return metrics.get("rules_version"), metrics.get("rules_catalog_version", 1)


def promotion_decision(
    report: Mapping[str, Any], active_metrics: Mapping[str, Any] | None
) -> tuple[bool, str]:
    """Si una versión se puede promover (ADR-0036 §9).

    Mejora a la activa en la partición de prueba fija (F1 de las familias activas, sin bajar
    la exactitud de la primera sugerencia), medida con las mismas reglas (ADR-0040 §14); la
    primera, a no tener capa. Sin métricas medidas, no se promueve.
    """
    if report.get("simulated", True):
        return False, "el informe no es una medición"
    if report.get("split") != "test":
        return False, "el informe no se midió sobre la partición de prueba fija"
    learned_f1 = (report.get("learned") or {}).get("f1")
    top1 = (report.get("rule_findings") or {}).get("top1_accuracy")
    if learned_f1 is None:
        return False, "el informe no mide el F1 de los posibles errores propios"
    if active_metrics is None:
        baseline = report.get("baseline") or {}
        base_f1 = baseline.get("learned_f1")
        base_top1 = baseline.get("top1_accuracy")
        if base_f1 is None:
            return False, "el informe no mide la línea base"
        if learned_f1 <= base_f1:
            return False, f"F1 {learned_f1:.4f} no mejora a no tener capa ({base_f1:.4f})"
        if top1 is not None and base_top1 is not None and top1 < base_top1:
            return False, (
                f"la primera sugerencia acierta menos ({top1:.4f}) que el primer candidato "
                f"de la regla ({base_top1:.4f})"
            )
        return True, "mejora a no tener capa"
    if active_metrics.get("evaluation_dataset_hash") != report.get("evaluation_dataset_hash"):
        return False, "la versión activa se midió con otra partición de prueba: no se comparan"
    if _rules_of(active_metrics) != _rules_of(report):
        return False, (
            "la versión activa se midió con otra versión de las reglas: no se comparan "
            "(ADR-0040 §14)"
        )
    active_f1 = (active_metrics.get("learned") or {}).get("f1")
    active_top1 = (active_metrics.get("rule_findings") or {}).get("top1_accuracy")
    if active_f1 is None:
        return False, "la versión activa no tiene F1 medido"
    if learned_f1 <= active_f1:
        return False, f"F1 {learned_f1:.4f} no mejora al de la activa ({active_f1:.4f})"
    if top1 is not None and active_top1 is not None and top1 < active_top1:
        return False, (
            f"la exactitud de la primera sugerencia baja de {active_top1:.4f} a {top1:.4f}"
        )
    return True, "mejora a la versión activa"


# --- El bucle de aprendizaje: las sesiones finalizadas de Cadenza -------------------------------


def _page_of(session: Any) -> str | None:
    """La página de origen de una sesión: la partitura de prueba o el sha256 de su imagen."""
    if session.test_score_id:
        return f"test_score:{session.test_score_id}"
    image = session.image_artifact or (session.document.get("provenance") or {}).get(
        "source_image_hash"
    )
    return None if not image else f"image:{image}"


def session_records(
    *,
    session_repository: Any,
    edit_repository: Any,
    user_repository: Any,
    split_seed: int,
    test_fraction: float,
    include_self_registered: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Los registros del corpus de las sesiones finalizadas, y las que se dejan fuera y por qué.

    Para cada sesión, `build_correction_records(estado 0, estado final)`, verificados con la
    misma comprobación que PrIMuS, con `source: cadenza` y la partición sobre su página de
    origen (todas las sesiones de una página caen del mismo lado, ADR-0036 §10). Las
    respuestas a sus sugerencias van en registros `suggestion` (aceptada, rechazada o
    ignorada), para evaluar y analizar: no se entrena con ellas.
    """
    records: list[dict[str, Any]] = []
    left_out: dict[str, str] = {}
    for session in session_repository.list(status="finalized"):
        if not include_self_registered:
            owner = user_repository.get(session.owner_id)
            if owner is not None and owner.self_registered:
                left_out[session.id] = "cuenta del registro público"
                continue
        page = _page_of(session)
        if page is None:
            left_out[session.id] = "sin página de origen (test_score_id ni imagen)"
            continue
        split = assign_split(page, seed=split_seed, test_fraction=test_fraction)
        raw = ScoreIR.from_primitive(session.document["score"])
        edits = edit_repository.list_events(session.id)
        final = materialize(raw, edits) if edits else raw
        try:
            derived = derive_edit_events(raw, final, document_id=session.document_id)
            verified = is_structurally_equal(materialize(raw, derived), final)
        except (ValueError, IndexError):
            verified = False
        incipit_id = f"cadenza:{session.id}"
        for record in build_correction_records(
            raw, final, incipit_id=incipit_id, split=split, verified=verified
        ):
            records.append(
                {**record, "source": "cadenza", "session_id": session.id, "work_id": page}
            )
        for suggestion in session_repository.list_suggestions(session.id):
            records.append(
                {
                    "record": "suggestion",
                    "source": "cadenza",
                    "incipit_id": incipit_id,
                    "session_id": session.id,
                    "work_id": page,
                    "split": split,
                    "condition": session.condition,
                    "response": suggestion.response or "ignored",
                    # Un rechazo heredado repite el de `inherited_from`: no es otra respuesta.
                    "inherited_from": suggestion.inherited_from,
                    "responded_by": suggestion.responded_by,
                    "responded_at": (
                        None
                        if suggestion.responded_at is None
                        else suggestion.responded_at.isoformat()
                    ),
                    "suggestion": {
                        "at_seq": suggestion.at_seq,
                        "rank": suggestion.rank,
                        "op": suggestion.op,
                        "anchor": suggestion.anchor,
                        "after": suggestion.after,
                        "confidence": suggestion.confidence,
                        "source": suggestion.source,
                        "model_version": suggestion.model_version,
                        "linked_to_finding": suggestion.finding_id is not None,
                        "applied_seq": suggestion.applied_seq,
                    },
                }
            )
    return records, left_out


def check_partition(artifact: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> None:
    """Falla si algún incipit de prueba del corpus estuvo en el entrenamiento del artefacto:
    la medición no sería sobre datos que el modelo no vio (ADR-0036 §9)."""
    trained = (artifact.get("training") or {}).get("train_incipits")
    if trained is None:
        raise SuggestionTrainingError(
            "el artefacto no dice con qué incipits se entrenó: no se puede comprobar la partición"
        )
    tested = {str(r["incipit_id"]) for r in records if r.get("split") == "test"}
    overlap = sorted(tested & set(trained))
    if overlap:
        shown = ", ".join(overlap[:5]) + (" …" if len(overlap) > 5 else "")
        raise SuggestionTrainingError(
            f"{len(overlap)} incipits de prueba se usaron para entrenar ({shown}): "
            "la partición del corpus no es la del entrenamiento"
        )
