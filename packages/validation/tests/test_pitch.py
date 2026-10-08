"""Pruebas de utilidades de altura musical."""

from __future__ import annotations

import pytest
from cadenza.validation.pitch import (
    midi_to_pitch,
    parse_pitch,
    pitch_alter,
    pitch_octave,
    pitch_step,
    pitch_to_midi,
)


@pytest.mark.parametrize(
    "pitch, expected_step, expected_alter, expected_octave",
    [
        ("C4", "C", 0, 4),
        ("C#4", "C", 1, 4),
        ("Db4", "D", -1, 4),
        ("F##5", "F", 2, 5),
        ("Ebb3", "E", -2, 3),
        ("A0", "A", 0, 0),
        ("C-1", "C", 0, -1),
    ],
)
def test_parse_pitch_valid(
    pitch: str, expected_step: str, expected_alter: int, expected_octave: int
) -> None:
    result = parse_pitch(pitch)
    assert result is not None
    assert result == (expected_step, expected_alter, expected_octave)


@pytest.mark.parametrize("invalid", ["", "H4", "C", "4", "C4x", "X#2", None])
def test_parse_pitch_invalid(invalid: str | None) -> None:
    assert parse_pitch(invalid) is None


@pytest.mark.parametrize(
    "pitch, expected_midi",
    [
        ("C-1", 0),
        ("C4", 60),
        ("C#4", 61),
        ("Db4", 61),
        ("A4", 69),
        ("B4", 71),
        ("C5", 72),
        ("G9", 127),
    ],
)
def test_pitch_to_midi(pitch: str, expected_midi: int) -> None:
    assert pitch_to_midi(pitch) == expected_midi


def test_pitch_to_midi_invalid() -> None:
    assert pitch_to_midi("") is None
    assert pitch_to_midi("invalid") is None
    assert pitch_to_midi(None) is None


def test_midi_to_pitch() -> None:
    assert midi_to_pitch(60) == "C4"
    assert midi_to_pitch(61) == "C#4"
    assert midi_to_pitch(61, prefer_flats=True) == "Db4"
    assert midi_to_pitch(69) == "A4"


def test_pitch_helpers() -> None:
    assert pitch_step("G#3") == "G"
    assert pitch_alter("G#3") == 1
    assert pitch_octave("G#3") == 3
    assert pitch_step(None) is None
    assert pitch_alter(None) is None
    assert pitch_octave(None) is None
