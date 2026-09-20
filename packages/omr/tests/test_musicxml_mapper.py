"""Pruebas del puente MusicXML -> ScoreIR (sin HOMR ni music21)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from cadenza.domain import EventKind, ScoreIR, build_anchor_index
from cadenza.omr.adapters.musicxml import musicxml_to_score_ir

FIXTURE = Path(__file__).parent / "fixtures" / "simple.musicxml"


def _score() -> ScoreIR:
    return musicxml_to_score_ir(FIXTURE.read_text(encoding="utf-8"))


def test_parts_and_staves() -> None:
    score = _score()
    assert len(score.parts) == 1
    assert score.parts[0].id == "part-0"
    assert score.parts[0].staves[0].id == "part-0-staff-0"


def test_measures_durations_and_pitches() -> None:
    measures = _score().parts[0].staves[0].measures
    assert [measure.number for measure in measures] == [1, 2]

    first_events = measures[0].events
    assert [event.kind for event in first_events] == [
        EventKind.NOTE,
        EventKind.NOTE,
        EventKind.REST,
    ]
    assert first_events[0].pitch == "C4"
    assert first_events[0].duration_beats == Fraction(1)
    assert first_events[1].pitch == "D4"
    assert first_events[2].pitch is None
    assert first_events[2].duration_beats == Fraction(2)


def test_anchor_index_is_deterministic_and_complete() -> None:
    score = _score()
    index = build_anchor_index(score)
    assert len(index) == 4
    assert index == build_anchor_index(score)
