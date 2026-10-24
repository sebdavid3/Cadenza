"""Varias voces ante el validador y la secuencia de símbolos de la SER (#218).

Aquí no se ejecuta ningún experimento: solo las funciones de las que dependen.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from cadenza.domain import (
    EditEvent,
    EditOp,
    Event,
    Finding,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Severity,
    build_anchor_index,
    materialize,
)
from cadenza.interchange import read_score
from cadenza.learning import (
    DatasetBuilder,
    derive_edit_events,
    is_structurally_equal,
    score_to_symbol_sequence,
)
from cadenza.validation import ValidationEngine

FIXTURES = Path(__file__).resolve().parents[2] / "interchange" / "tests" / "fixtures"
# Compás de 4/4: voz 1, un Mi5 redonda; voz 2, `<forward>` de dos negras y después Do5 y Si4.
FORWARD = FIXTURES / "forward_second_voice.musicxml"


def _findings(path: Path) -> list[str]:
    score = read_score(path)
    document = ScoreDocument(
        id="d",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="homr"),
    )
    return [f.message for f in ValidationEngine().validate(document)]


def test_a_voice_that_enters_mid_measure_is_not_a_balance_error() -> None:
    assert _findings(FORWARD) == []


def test_voices_that_enter_rest_and_leave_mid_measure_are_not_errors() -> None:
    """Piano con voces que entran, callan y salen a mitad del compás, un acorde y una ligadura
    en la segunda voz: sin ningún hallazgo."""

    assert _findings(FIXTURES / "voices_piano.musicxml") == []


def _map_events(score: ScoreIR, change: Callable[[Event], Event | None]) -> ScoreIR:
    return replace(
        score,
        parts=tuple(
            replace(
                part,
                staves=tuple(
                    replace(
                        staff,
                        measures=tuple(
                            replace(
                                measure,
                                events=tuple(
                                    changed
                                    for event in measure.events
                                    if (changed := change(event)) is not None
                                ),
                            )
                            for measure in staff.measures
                        ),
                    )
                    for staff in part.staves
                ),
            )
            for part in score.parts
        ),
    )


def test_the_derived_edits_rebuild_the_hidden_rest_of_the_truth() -> None:
    """Materializar las ediciones derivadas del diff da la verdad, también su silencio invisible:
    falte en la predicción o esté en ella como un silencio que se ve."""

    truth = read_score(FORWARD)
    without_gap = _map_events(truth, lambda event: None if event.hidden else event)
    shown_gap = _map_events(truth, lambda event: replace(event, hidden=False))
    for predicted in (without_gap, shown_gap):
        edits = derive_edit_events(predicted, truth)
        assert edits
        assert materialize(predicted, edits) == truth
        assert not is_structurally_equal(predicted, truth)


def test_the_error_density_of_a_sample_does_not_count_hidden_rests() -> None:
    """La densidad de errores de una muestra son los hallazgos entre los eventos del compás: un
    silencio invisible no se ve ni se corrige, y no cuenta (3 eventos, no 4)."""

    score = read_score(FORWARD)
    anchors = build_anchor_index(score)
    document = ScoreDocument(
        id="d", score=score, anchors=anchors, provenance=Provenance(omr_engine="homr")
    )
    target = next(a for a in anchors.anchors() if a.voice == 1 and a.event_index == 1)
    finding = Finding(
        anchor=target, rule_id="measure.balance", severity=Severity.ERROR, message="prueba"
    )
    edit = EditEvent(
        id="e1",
        document_id="d",
        seq=1,
        anchor=target,
        op=EditOp.SET_PITCH,
        author="ana",
        created_at=datetime(2026, 10, 24, tzinfo=UTC),
        before={"pitch": "C5"},
        after={"pitch": "D5"},
    )
    [sample] = DatasetBuilder().build(document, [edit], [finding])
    assert sample.error_density == 1 / 3


def test_a_hidden_rest_is_not_a_symbol_of_the_ser() -> None:
    """El hueco de una voz no se dibuja ni se reconoce: no entra en la secuencia de símbolos,
    como antes de #218, cuando el `<forward>` se perdía al importar."""

    assert score_to_symbol_sequence(read_score(FORWARD)) == [
        "clef:G2",
        "key:0",
        "time:4/4",
        "note:E5:whole",
        "note:C5:quarter",
        "note:B4:quarter",
        "barline",
    ]
