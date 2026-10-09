"""Pruebas de conversión de alturas a MIDI y distancia en semitonos."""

from __future__ import annotations

import pytest
from cadenza.learning import pitch_to_midi, semitone_distance


@pytest.mark.parametrize(
    "pitch, expected",
    [("C4", 60), ("D#4", 63), ("Eb4", 63), ("C-1", 0), ("B3", 59), ("a4", 69)],
)
def test_pitch_to_midi(pitch: str, expected: int) -> None:
    assert pitch_to_midi(pitch) == expected


@pytest.mark.parametrize("pitch", ["", "H4", "C", "Cx4", "4"])
def test_pitch_to_midi_invalid(pitch: str) -> None:
    assert pitch_to_midi(pitch) is None


def test_semitone_distance() -> None:
    assert semitone_distance("C4", "D4") == 2.0
    assert semitone_distance("C4", "C4") == 0.0
    assert semitone_distance(None, "D4") == 0.0
