"""Pruebas del puente canónico MusicXML → ScoreIR (music21)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from cadenza.domain import EventKind, ScoreIR, TimeSignature, build_anchor_index
from cadenza.interchange import musicxml_to_score_ir, read_score, score_ir_to_musicxml

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


def test_time_signature_is_mapped_and_inherited() -> None:
    measures = _score().parts[0].staves[0].measures
    assert measures[0].time_signature == TimeSignature(4, 4)
    assert measures[1].time_signature == TimeSignature(4, 4)


def test_anchor_index_is_deterministic_and_complete() -> None:
    score = _score()
    index = build_anchor_index(score)
    assert len(index) == 4
    assert index == build_anchor_index(score)


def test_read_score_matches_text_parsing() -> None:
    assert read_score(FIXTURE) == _score()


def test_musicxml_roundtrip_preserves_supported_subset() -> None:
    original = _score()
    reparsed = musicxml_to_score_ir(score_ir_to_musicxml(original))

    original_measures = original.parts[0].staves[0].measures
    reparsed_measures = reparsed.parts[0].staves[0].measures
    assert [m.number for m in reparsed_measures] == [m.number for m in original_measures]
    for expected, actual in zip(original_measures, reparsed_measures, strict=True):
        assert [e.pitch for e in actual.events] == [e.pitch for e in expected.events]
        assert [e.duration_beats for e in actual.events] == [
            e.duration_beats for e in expected.events
        ]
