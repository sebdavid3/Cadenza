"""Pruebas unitarias de serialización simbólica y cálculo de SER (#30)."""

from __future__ import annotations

from fractions import Fraction

import pytest
from cadenza.domain import (
    Clef,
    Event,
    EventKind,
    KeySignature,
    Measure,
    Part,
    ScoreIR,
    Staff,
    TimeSignature,
)
from cadenza.learning import (
    SerResult,
    format_clef_symbol,
    format_duration_symbol,
    format_key_signature_symbol,
    format_time_signature_symbol,
    resolve_pitch_with_key_signature,
    score_ser_pair,
    score_to_symbol_sequence,
    score_to_symbols,
    symbol_error_rate,
)


def test_format_clef_symbol() -> None:
    assert format_clef_symbol(None) is None
    assert format_clef_symbol(Clef.treble()) == "clef:G2"
    assert format_clef_symbol(Clef.bass()) == "clef:F4"
    assert format_clef_symbol(Clef.alto()) == "clef:C3"
    assert format_clef_symbol(Clef.tenor()) == "clef:C4"
    assert format_clef_symbol(Clef(sign="G", line=2, octave_change=-1)) == "clef:G2-1"
    assert format_clef_symbol(Clef(sign="G", line=2, octave_change=1)) == "clef:G2+1"


def test_format_key_signature_symbol() -> None:
    assert format_key_signature_symbol(None) is None
    assert format_key_signature_symbol(KeySignature(fifths=0)) == "key:0"
    assert format_key_signature_symbol(KeySignature(fifths=1)) == "key:1#"
    assert format_key_signature_symbol(KeySignature(fifths=3)) == "key:3#"
    assert format_key_signature_symbol(KeySignature(fifths=-1)) == "key:1b"
    assert format_key_signature_symbol(KeySignature(fifths=-3)) == "key:3b"


def test_format_time_signature_symbol() -> None:
    assert format_time_signature_symbol(None) is None
    assert format_time_signature_symbol(TimeSignature(3, 4)) == "time:3/4"
    assert format_time_signature_symbol(TimeSignature(4, 4)) == "time:4/4"
    assert format_time_signature_symbol(TimeSignature(6, 8)) == "time:6/8"


def test_format_duration_symbol() -> None:
    assert format_duration_symbol(None) == "unspecified"
    assert format_duration_symbol(Fraction(4, 1)) == "whole"
    assert format_duration_symbol(Fraction(2, 1)) == "half"
    assert format_duration_symbol(Fraction(1, 1)) == "quarter"
    assert format_duration_symbol(Fraction(1, 2)) == "eighth"
    assert format_duration_symbol(Fraction(1, 4)) == "sixteenth"
    assert format_duration_symbol(Fraction(3, 2)) == "dotted_quarter"
    assert format_duration_symbol(Fraction(3, 4)) == "dotted_eighth"
    # Duración no estándar / tresillo
    assert format_duration_symbol(Fraction(2, 3)) == "2/3"


def test_resolve_pitch_with_key_signature() -> None:
    assert resolve_pitch_with_key_signature(None, 0) is None
    assert resolve_pitch_with_key_signature("", 0) == ""
    # En Do mayor (0)
    assert resolve_pitch_with_key_signature("C4", 0) == "C4"
    assert resolve_pitch_with_key_signature("B5", 0) == "B5"

    # En Mib mayor (-3: Bb, Eb, Ab)
    assert resolve_pitch_with_key_signature("B5", -3) == "Bb5"
    assert resolve_pitch_with_key_signature("E5", -3) == "Eb5"
    assert resolve_pitch_with_key_signature("A5", -3) == "Ab5"
    assert resolve_pitch_with_key_signature("C5", -3) == "C5"
    assert resolve_pitch_with_key_signature("D5", -3) == "D5"
    # Si ya tiene alteración explícita, se respeta
    assert resolve_pitch_with_key_signature("Bb5", -3) == "Bb5"
    assert resolve_pitch_with_key_signature("B#5", -3) == "B#5"

    # En Sol mayor (1#: F#)
    assert resolve_pitch_with_key_signature("F4", 1) == "F#4"
    assert resolve_pitch_with_key_signature("G4", 1) == "G4"
    assert resolve_pitch_with_key_signature("F#4", 1) == "F#4"


def _make_score(measures: list[Measure]) -> ScoreIR:
    staff = Staff(id="staff-1", measures=tuple(measures))
    part = Part(id="part-1", staves=(staff,))
    return ScoreIR(parts=(part,))


def test_score_to_symbol_sequence_roundtrip() -> None:
    meas = Measure(
        number=1,
        clef=Clef.treble(),
        key_signature=KeySignature(fifths=-3),
        time_signature=TimeSignature(3, 4),
        events=(
            Event(kind=EventKind.NOTE, pitch="B5", duration_beats=Fraction(1, 1)),
            Event(kind=EventKind.NOTE, pitch="E5", duration_beats=Fraction(1, 2)),
            Event(kind=EventKind.REST, duration_beats=Fraction(1, 4)),
        ),
    )
    score = _make_score([meas])

    # Con resolución de armadura
    syms = score_to_symbol_sequence(score, apply_key_signature=True)
    expected = [
        "clef:G2",
        "key:3b",
        "time:3/4",
        "note:Bb5:quarter",
        "note:Eb5:eighth",
        "rest:sixteenth",
        "barline",
    ]
    assert syms == expected

    # Sin resolución de armadura
    syms_raw = score_to_symbols(score, apply_key_signature=False)
    expected_raw = [
        "clef:G2",
        "key:3b",
        "time:3/4",
        "note:B5:quarter",
        "note:E5:eighth",
        "rest:sixteenth",
        "barline",
    ]
    assert syms_raw == expected_raw


def test_score_to_symbol_sequence_empty() -> None:
    score = ScoreIR(parts=())
    assert score_to_symbol_sequence(score) == []


def test_ser_pair_identical_scores() -> None:
    meas = Measure(
        number=1,
        clef=Clef.treble(),
        events=(
            Event(kind=EventKind.NOTE, pitch="C4", duration_beats=Fraction(1, 1)),
            Event(kind=EventKind.NOTE, pitch="D4", duration_beats=Fraction(1, 1)),
        ),
    )
    score = _make_score([meas])
    res = score_ser_pair(score, score)

    assert isinstance(res, SerResult)
    assert symbol_error_rate(["a", "b"], ["a", "c"]) == 0.5
    assert res.reference_symbols == 4  # clef, note, note, barline
    assert res.hypothesis_symbols == 4
    assert res.edit_distance == 0
    assert res.ser == 0.0
    assert res.to_primitive() == {
        "reference_symbols": 4,
        "hypothesis_symbols": 4,
        "edit_distance": 0,
        "ser": 0.0,
    }


def test_ser_pair_transcription_failure() -> None:
    # Hipótesis vacía (fallo de segmentación HOMR)
    meas = Measure(
        number=1,
        clef=Clef.treble(),
        events=(Event(kind=EventKind.NOTE, pitch="C4", duration_beats=Fraction(1, 1)),),
    )
    ref_score = _make_score([meas])
    empty_score = ScoreIR(parts=())

    res = score_ser_pair(ref_score, empty_score)
    assert res.reference_symbols == 3  # clef:G2, note:C4:quarter, barline
    assert res.hypothesis_symbols == 0
    assert res.edit_distance == 3
    assert res.ser == 1.0


def test_ser_pair_both_empty() -> None:
    empty = ScoreIR(parts=())
    res = score_ser_pair(empty, empty)
    assert res.reference_symbols == 0
    assert res.hypothesis_symbols == 0
    assert res.edit_distance == 0
    assert res.ser == 0.0


def test_ser_pair_reference_empty_hypothesis_non_empty() -> None:
    empty = ScoreIR(parts=())
    meas = Measure(
        number=1,
        clef=Clef.treble(),
        events=(Event(kind=EventKind.NOTE, pitch="C4", duration_beats=Fraction(1, 1)),),
    )
    hyp = _make_score([meas])
    res = score_ser_pair(empty, hyp)
    assert res.ser == 1.0


def test_ser_pair_substitutions_and_deletions() -> None:
    m1 = Measure(
        number=1,
        events=(
            Event(kind=EventKind.NOTE, pitch="C4", duration_beats=Fraction(1, 1)),
            Event(kind=EventKind.NOTE, pitch="D4", duration_beats=Fraction(1, 1)),
            Event(kind=EventKind.NOTE, pitch="E4", duration_beats=Fraction(1, 1)),
            Event(kind=EventKind.NOTE, pitch="F4", duration_beats=Fraction(1, 1)),
        ),
    )
    # Hipótesis con una nota cambiada y una nota omitida
    m2 = Measure(
        number=1,
        events=(
            Event(kind=EventKind.NOTE, pitch="C4", duration_beats=Fraction(1, 1)),
            Event(kind=EventKind.NOTE, pitch="D#4", duration_beats=Fraction(1, 1)),  # substitución
            Event(kind=EventKind.NOTE, pitch="E4", duration_beats=Fraction(1, 1)),
            # F4 omitida (eliminación)
        ),
    )
    s1 = _make_score([m1])
    s2 = _make_score([m2])

    res = score_ser_pair(s1, s2)
    # ref: [note:C4:quarter, note:D4:quarter, note:E4:quarter, note:F4:quarter, barline]
    # hyp: [note:C4:quarter, note:D#4:quarter, note:E4:quarter, barline] (4 símbolos)
    # edit distance: 1 sub (D4->D#4) + 1 del (F4) = 2
    assert res.reference_symbols == 5
    assert res.hypothesis_symbols == 4
    assert res.edit_distance == 2
    assert pytest.approx(res.ser, 1e-4) == 2 / 5
