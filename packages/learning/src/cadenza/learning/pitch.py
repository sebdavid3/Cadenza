"""Utilidades de altura para features de aprendizaje activo."""

from __future__ import annotations

_PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def pitch_to_midi(pitch: str | None) -> int | None:
    """Convierte ``C4``/``D#4``/``Eb3`` a número MIDI; `None` si no es válida."""

    if not pitch:
        return None
    letter = pitch[0].upper()
    if letter not in _PITCH_CLASS:
        return None
    index = 1
    accidental = 0
    while index < len(pitch) and pitch[index] in "#b":
        accidental += 1 if pitch[index] == "#" else -1
        index += 1
    octave_text = pitch[index:]
    if not octave_text.lstrip("-").isdigit():
        return None
    octave = int(octave_text)
    return (octave + 1) * 12 + _PITCH_CLASS[letter] + accidental


def semitone_distance(before: str | None, after: str | None) -> float:
    """Distancia absoluta en semitonos entre dos alturas (0.0 si alguna falta)."""

    before_midi = pitch_to_midi(before)
    after_midi = pitch_to_midi(after)
    if before_midi is None or after_midi is None:
        return 0.0
    return float(abs(before_midi - after_midi))
