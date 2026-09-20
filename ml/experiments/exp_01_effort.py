"""Experimento 1: reducción de esfuerzo de inspección (HITL asistido vs. manual).

Compara dos flujos de revisión sobre un `ScoreDocument`:

- **Línea base (manual):** el usuario inspecciona los N compases uno por uno sin
  ayuda, por lo que el esfuerzo es O(N).
- **Línea asistida:** el `ValidationEngine` emite `Finding` anclados a compases,
  y el usuario inspecciona únicamente los compases señalados, esforzando O(X).

El documento se deriva del `FakeOMREngine` determinista y se escala a N compases.
El script es determinista y escribe `results/effort_comparison.json`.
"""

from __future__ import annotations

import json
import random
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

from cadenza.domain import (
    Finding,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Staff,
    TimeSignature,
    build_anchor_index,
)
from cadenza.omr import FakeOMREngine, OMREngine
from cadenza.validation import MeasureBalanceRule, ValidationEngine

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"
DEFAULT_MEASURES = 40
DEFAULT_BROKEN_RATIO = 0.25
SEED = 20260920
TIME_SIGNATURE = TimeSignature(4, 4)


def _base_measures(engine: OMREngine) -> tuple[Measure, ...]:
    """Compases canónicos que aporta el adaptador OMR (motivo reutilizable)."""

    document = engine.transcribe(Path("synthetic.png"))
    return document.score.parts[0].staves[0].measures


def _corrupt(measure: Measure, number: int) -> Measure:
    """Desbalancea un compás alterando la duración de su último evento."""

    events = list(measure.events)
    last = events[-1]
    duration = last.duration_beats or Fraction(1)
    wrong = duration - 1 if duration > 1 else duration + 1
    events[-1] = replace(last, duration_beats=wrong)
    return replace(measure, number=number, events=tuple(events))


def _balanced(measure: Measure, number: int) -> Measure:
    """Reetiqueta un compás sano con su número definitivo."""

    return replace(measure, number=number)


def build_document(
    measures: int = DEFAULT_MEASURES,
    broken_ratio: float = DEFAULT_BROKEN_RATIO,
    seed: int = SEED,
    engine: OMREngine | None = None,
) -> ScoreDocument:
    """Genera un documento de `measures` compases con una fracción corrupta."""

    omr = engine if engine is not None else FakeOMREngine()
    motif = _base_measures(omr)
    rng = random.Random(seed)

    generated: list[Measure] = []
    for number in range(1, measures + 1):
        template = motif[(number - 1) % len(motif)]
        if rng.random() < broken_ratio:
            generated.append(_corrupt(template, number))
        else:
            generated.append(_balanced(template, number))

    staff = Staff(id="part-0-staff-0", measures=tuple(generated))
    score = ScoreIR(parts=(Part(id="part-0", staves=(staff,)),))
    return ScoreDocument(
        id="exp-01-doc",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(
            omr_engine=omr.engine_id,
            rules_version="measure.balance",
        ),
    )


def _measures_with_findings(findings: list[Finding]) -> set[tuple[int, int, int]]:
    return {
        (finding.anchor.part, finding.anchor.staff, finding.anchor.measure)
        for finding in findings
    }


def run(
    measures: int = DEFAULT_MEASURES,
    broken_ratio: float = DEFAULT_BROKEN_RATIO,
) -> dict[str, object]:
    """Ejecuta la comparación y devuelve el resumen serializable."""

    document = build_document(measures=measures, broken_ratio=broken_ratio, seed=SEED)
    findings = ValidationEngine([MeasureBalanceRule()]).validate(document)

    total_measures = sum(
        len(staff.measures) for part in document.score.parts for staff in part.staves
    )
    flagged = _measures_with_findings(findings)
    total_findings = len(findings)

    baseline_inspections = total_measures
    assisted_inspections = len(flagged)
    reduction = (
        0.0 if baseline_inspections == 0 else 1.0 - assisted_inspections / baseline_inspections
    )

    return {
        "experiment": "exp_01_effort",
        "seed": SEED,
        "omr_engine": document.provenance.omr_engine,
        "total_measures": total_measures,
        "total_findings": total_findings,
        "baseline_inspections": baseline_inspections,
        "assisted_inspections": assisted_inspections,
        "effort_reduction_ratio": round(reduction, 4),
        "effort_reduction_percent": round(reduction * 100, 2),
        "flagged_measures": sorted(
            f"{part}:{staff}:{measure}" for part, staff, measure in flagged
        ),
    }


def main() -> None:
    result = run()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = RESULTS_DIR / "effort_comparison.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"[exp_01] inspecciones manual={result['baseline_inspections']} "
        f"asistidas={result['assisted_inspections']} "
        f"reduccion={result['effort_reduction_percent']}%"
    )
    print(f"[exp_01] escrito: {output}")


if __name__ == "__main__":
    main()
