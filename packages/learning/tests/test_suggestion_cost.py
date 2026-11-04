"""Coste de la capa de sugerencias en una validación de página completa (ADR-0036 §12).

La capa (rasgos, puntuación, posibles errores propios y el filtro de admisibilidad que
aplican los casos de uso) añade como mucho 300 ms. Aquí se mide sobre una página sintética
densa (dos pentagramas, 40 compases, 624 eventos, con compases incompletos y alteraciones
contra la armadura que disparan candidatos y posibles errores propios) y con la caché del
modelo vacía en cada pasada, el caso más caro. La medición con una página real la hace
`scripts/measure_suggestion_cost.py`, que falla si no recibe la página. No se mide la escritura
de las filas de `suggestions` en la base de datos, ni con un artefacto entrenado con el corpus
completo (con más etiquetas por familia).
"""

from __future__ import annotations

import statistics
import time
from fractions import Fraction
from pathlib import Path

from cadenza.application.suggestions import suggest, with_inherited_rejections
from cadenza.domain import (
    Clef,
    Event,
    EventKind,
    KeySignature,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Staff,
    TimeSignature,
    build_anchor_index,
)
from cadenza.learning.suggestions import load_suggestions_config, train
from cadenza.validation import ValidationEngine
from cadenza.validation.learned import FrequencyBackoffModel

from .suggestions_support import corpus_records, small_config

BUDGET_SECONDS = 0.300
RUNS = 5
_UPPER = ("C5", "D5", "E5", "F5", "G5", "A5", "B4", "A4")
_LOWER = ("F3", "C4", "A3", "C4", "B2", "D3", "C3", "E3")


def _staff(staff_id: str, pitches: tuple[str, ...], measures: int, *, clef: Clef) -> Staff:
    built = []
    for number in range(1, measures + 1):
        events = [
            Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=Fraction(1, 2))
            for pitch in pitches
        ]
        if number % 5 == 0:
            events = events[:-1]  # compás incompleto: measure.balance con candidatos
        built.append(
            Measure(
                number=number,
                events=tuple(events),
                time_signature=TimeSignature(4, 4),
                clef=clef if number == 1 else None,
                key_signature=KeySignature(fifths=-1) if number == 1 else None,
            )
        )
    return Staff(id=staff_id, measures=tuple(built))


def full_page(measures: int = 40) -> ScoreDocument:
    score = ScoreIR(
        parts=(
            Part(
                id="P1",
                staves=(
                    _staff("P1-S1", _UPPER, measures, clef=Clef.treble()),
                    _staff("P1-S2", _LOWER, measures, clef=Clef.bass()),
                ),
            ),
        )
    )
    return ScoreDocument(
        id="page",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="fake"),
    )


def test_the_layer_adds_at_most_300_ms_to_a_full_page(tmp_path: Path) -> None:
    config = load_suggestions_config(small_config(tmp_path / "config.json"))
    artifact = train(corpus_records(), config, dataset_hash="d")
    document = full_page()
    events = sum(len(m.events) for s in document.score.parts[0].staves for m in s.measures)
    assert events == 624
    validator = ValidationEngine()
    findings = validator.validate(document)

    layer: list[float] = []
    produced = []
    for _ in range(RUNS):
        model = FrequencyBackoffModel(artifact, version="cost")  # caché vacía en cada pasada
        start = time.perf_counter()
        produced = suggest(document, findings, model)
        with_inherited_rejections(produced, (), current_seq=0, edits=())
        layer.append(time.perf_counter() - start)

    # La capa trabajó de verdad: ordenó candidatos y propuso posibles errores propios.
    assert any(edits for finding, edits in produced if finding.rule_id == "measure.balance")
    assert any(finding.rule_id.startswith("learned.") for finding, _ in produced)
    assert statistics.median(layer) <= BUDGET_SECONDS, layer
