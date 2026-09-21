"""Experimento 2: comparación de estrategias de aprendizaje activo.

Simula un *pool* histórico de correcciones (muestras derivadas de un
`ScoreDocument` y su log de `EditEvent`), les asigna valores sintéticos de
`error_density` y `correction_magnitude`, y ejecuta el muestreo de un lote con las
tres estrategias del proyecto:

- `UncertaintyAcquisition` (baseline por densidad de error),
- `DiversityAcquisition` (cobertura del espacio de features),
- `HybridAcquisition` (la apuesta principal: críticos + diversidad).

Exporta `results/al_strategies_comparison.csv` con la selección de cada estrategia.
"""

from __future__ import annotations

import csv
import random
from dataclasses import replace
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path

from cadenza.domain import (
    Anchor,
    EditEvent,
    EditOp,
    Event,
    EventKind,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Staff,
    TimeSignature,
    build_anchor_index,
)
from cadenza.learning import (
    DiversityAcquisition,
    HybridAcquisition,
    TrainingSample,
    UncertaintyAcquisition,
)
from cadenza.learning.dataset import DatasetBuilder

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"
POOL_SIZE = 80
BUDGET = 5
SEED = 20260920
TIME_SIGNATURE = TimeSignature(4, 4)
PITCHES = ("C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5")


def _document(measures: int = POOL_SIZE) -> ScoreDocument:
    """Documento sintético con `POOL_SIZE` compases y dos eventos por compás."""

    generated = []
    for number in range(1, measures + 1):
        generated.append(
            Measure(
                number=number,
                events=(
                    Event(
                        kind=EventKind.NOTE,
                        voice=0,
                        pitch=PITCHES[number % len(PITCHES)],
                        duration_beats=Fraction(1),
                    ),
                    Event(
                        kind=EventKind.NOTE,
                        voice=0,
                        pitch=PITCHES[(number + 3) % len(PITCHES)],
                        duration_beats=Fraction(1),
                    ),
                ),
                time_signature=TIME_SIGNATURE,
            )
        )
    staff = Staff(id="part-0-staff-0", measures=tuple(generated))
    score = ScoreIR(parts=(Part(id="part-0", staves=(staff,)),))
    return ScoreDocument(
        id="exp-02-doc",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="synthetic"),
    )


def _anchor(measure: int, event_index: int) -> Anchor:
    return Anchor(
        part=0,
        staff=0,
        measure=measure,
        voice=0,
        event_index=event_index,
        staff_id="part-0-staff-0",
    )


def _edit(seq: int, measure: int, before: str, after: str) -> EditEvent:
    return EditEvent(
        id=f"edit-{seq}",
        document_id="exp-02-doc",
        seq=seq,
        anchor=_anchor(measure, 0),
        op=EditOp.SET_PITCH,
        author="simulated",
        created_at=datetime(2026, 9, 20, tzinfo=UTC),
        before={"pitch": before},
        after={"pitch": after},
    )


def _build_pool() -> tuple[TrainingSample, ...]:
    """Deriva un pool de muestras vía `DatasetBuilder` y enriquece sus señales."""

    document = _document()
    rng = random.Random(SEED)
    edits = [
        _edit(seq=index, measure=index, before=PITCHES[index % len(PITCHES)],
              after=PITCHES[(index + 2) % len(PITCHES)])
        for index in range(1, POOL_SIZE + 1)
    ]
    base = DatasetBuilder().build(document, edits)

    enriched = []
    for sample in base:
        # Señales simuladas: densidad de error y magnitud de corrección correlacionadas
        # con la posición para que existan casos "críticos" identificables.
        error_density = round(rng.betavariate(2.0, 5.0) + sample.correction_magnitude / 24.0, 4)
        magnitude = round(sample.correction_magnitude + rng.uniform(0.0, 4.0), 4)
        enriched.append(replace(sample, error_density=error_density,
                                correction_magnitude=magnitude))
    return tuple(enriched)


def _spread(samples: list[TrainingSample]) -> float:
    """Diversidad media por par del lote (distancia euclídea en features)."""

    if len(samples) < 2:
        return 0.0
    distances = []
    for index, left in enumerate(samples):
        for right in samples[index + 1 :]:
            distances.append(
                sum((a - b) ** 2 for a, b in zip(left.features, right.features, strict=True)) ** 0.5
            )
    return float(sum(distances) / len(distances))


def run() -> tuple[list[dict[str, object]], dict[str, dict[str, float]]]:
    pool = _build_pool()
    strategies = (
        UncertaintyAcquisition(),
        DiversityAcquisition(),
        HybridAcquisition(),
    )

    rows: list[dict[str, object]] = []
    summary: dict[str, dict[str, float]] = {}
    for strategy in strategies:
        selected = strategy.select(pool, BUDGET)
        summary[strategy.strategy_id] = {
            "mean_error_density": round(
                sum(s.error_density for s in selected) / len(selected), 4
            ),
            "mean_magnitude": round(
                sum(s.correction_magnitude for s in selected) / len(selected), 4
            ),
            "mean_pairwise_spread": round(_spread(list(selected)), 4),
        }
        for rank, sample in enumerate(selected, start=1):
            rows.append(
                {
                    "strategy": strategy.strategy_id,
                    "rank": rank,
                    "measure": sample.anchor.measure,
                    "error_density": sample.error_density,
                    "correction_magnitude": sample.correction_magnitude,
                }
            )
    return rows, summary


def main() -> None:
    rows, summary = run()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = RESULTS_DIR / "al_strategies_comparison.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "strategy",
                "rank",
                "measure",
                "error_density",
                "correction_magnitude",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    for strategy_id, metrics in summary.items():
        print(
            f"[exp_02] {strategy_id:12s} "
            f"error={metrics['mean_error_density']:.3f} "
            f"magnitud={metrics['mean_magnitude']:.3f} "
            f"diversidad={metrics['mean_pairwise_spread']:.3f}"
        )
    print(f"[exp_02] escrito: {output}")


if __name__ == "__main__":
    main()
