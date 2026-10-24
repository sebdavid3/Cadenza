"""Varias voces ante el validador y la secuencia de símbolos de la SER (#218).

Aquí no se ejecuta ningún experimento: solo las funciones de las que dependen.
"""

from __future__ import annotations

from pathlib import Path

from cadenza.domain import Provenance, ScoreDocument, build_anchor_index
from cadenza.interchange import read_score
from cadenza.learning import score_to_symbol_sequence
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
