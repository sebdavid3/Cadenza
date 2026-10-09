"""Módulo de utilidades de altura musical para el motor de validación (M2).

Proporciona funciones puras para parseo de alturas científicas (p. ej. 'C4', 'F#5', 'Bb3'),
conversión a número de nota MIDI y extracción de paso, alteración y octava.
"""

from __future__ import annotations

_PITCH_CLASS = {
    "C": 0,
    "D": 2,
    "E": 4,
    "F": 5,
    "G": 7,
    "A": 9,
    "B": 11,
}

_SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def parse_pitch(pitch: str | None) -> tuple[str, int, int] | None:
    """Parsea una altura científica como ``(step, alter, octave)``.

    Ejemplos:
        'C4' -> ('C', 0, 4)
        'F#5' -> ('F', 1, 5)
        'Bb3' -> ('B', -1, 3)
        'C##4' -> ('C', 2, 4)
        'Ebb2' -> ('E', -2, 2)
    """
    if not pitch:
        return None
    step = pitch[0].upper()
    if step not in _PITCH_CLASS:
        return None

    idx = 1
    alter = 0
    while idx < len(pitch) and pitch[idx] in "#b":
        alter += 1 if pitch[idx] == "#" else -1
        idx += 1

    octave_text = pitch[idx:]
    if not octave_text:
        return None
    # Permitir octavas negativas (p. ej. -1)
    if octave_text.startswith("-"):
        digits = octave_text[1:]
        if not digits or not digits.isdigit():
            return None
        octave = -int(digits)
    elif octave_text.isdigit():
        octave = int(octave_text)
    else:
        return None

    return (step, alter, octave)


def pitch_to_midi(pitch: str | None) -> int | None:
    """Convierte una altura musical a número MIDI (p. ej. 'C4' -> 60)."""
    parsed = parse_pitch(pitch)
    if parsed is None:
        return None
    step, alter, octave = parsed
    # C-1 es MIDI 0 (octava -1 + 1 = 0 * 12 + 0)
    return (octave + 1) * 12 + _PITCH_CLASS[step] + alter


def midi_to_pitch(midi: int, *, prefer_flats: bool = False) -> str:
    """Convierte un número MIDI a altura estándar (p. ej. 60 -> 'C4')."""
    octave = (midi // 12) - 1
    semitone = midi % 12
    names = _FLAT_NAMES if prefer_flats else _SHARP_NAMES
    name = names[semitone]
    return f"{name}{octave}"


def pitch_step(pitch: str | None) -> str | None:
    """Paso o letra base de la nota ('C'..'B')."""
    parsed = parse_pitch(pitch)
    return parsed[0] if parsed is not None else None


def pitch_alter(pitch: str | None) -> int | None:
    """Alteración numérica de la nota (-1 para bemol, 0 para natural, 1 para sostenido)."""
    parsed = parse_pitch(pitch)
    return parsed[1] if parsed is not None else None


def pitch_octave(pitch: str | None) -> int | None:
    """Octava científica de la nota."""
    parsed = parse_pitch(pitch)
    return parsed[2] if parsed is not None else None
