"""Altura que suena de la verdad de referencia de PrIMuS (#255).

El MEI de PrIMuS no codifica la alteración que impone la armadura: con tres bemoles, la
nota de la línea de Si es `pname="b"` sin `accid.ges`, y su lectura da `B4` donde suena
`Bb4`. Como el `ScoreIR` escribe la altura con `nameWithOctave`, un becuadro explícito y
una nota sin alteración dan el mismo texto, así que la armadura no se puede aplicar
después de leer. El `.semantic` del mismo incipit sí trae la altura que suena de cada nota
(`note-Bb4_eighth`, y `note-B4_eighth` con el becuadro), en el orden de la partitura.

`with_sounding_pitches` pone esas alturas en el `ScoreIR` leído del MEI, comprobando que
coinciden el número de notas, la letra y la octava; si no coinciden, no adivina nada.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace
from typing import Final

from cadenza.domain import EventKind, Measure, ScoreIR

from .alignment import split_pitch

# Fichas del `.semantic` que son notas, en el orden en que el `ScoreIR` las lee del MEI:
# las de adorno también, porque el lector las conserva como notas.
_NOTE_TOKEN: Final[re.Pattern[str]] = re.compile(r"^(?:grace)?note-([^_]+)_")


class SemanticMismatch(ValueError):
    """La verdad leída del MEI y el `.semantic` del incipit no describen las mismas notas."""


def _normalized(pitch: str) -> str | None:
    letter, accidental, octave = split_pitch(pitch)
    if not letter:
        return None
    return f"{letter}{accidental}{octave}"


def semantic_note_pitches(semantic: str) -> list[str]:
    """Altura que suena de cada nota y nota de adorno de un `.semantic`, en orden.

    Las alteraciones se escriben como en el `ScoreIR`: `#`, `##`, `b` y `bb`.
    """
    pitches: list[str] = []
    for token in semantic.split():
        match = _NOTE_TOKEN.match(token)
        if match is None:
            continue
        pitch = _normalized(match.group(1))
        if pitch is None:
            raise SemanticMismatch(f"altura ilegible en la ficha {token!r} del .semantic")
        pitches.append(pitch)
    return pitches


def with_sounding_pitches(score: ScoreIR, pitches: Sequence[str]) -> ScoreIR:
    """Devuelve `score` con la altura que suena de cada nota, tomada de `pitches`.

    Recorre las notas en orden de partes, pentagramas, compases y eventos. Cada altura
    debe tener la letra y la octava de la nota leída: solo cambia la alteración.
    """
    note_count = sum(
        1
        for part in score.parts
        for staff in part.staves
        for measure in staff.measures
        for event in measure.events
        if event.kind is EventKind.NOTE
    )
    if note_count != len(pitches):
        raise SemanticMismatch(f"{len(pitches)} alturas para {note_count} notas")

    remaining = iter(enumerate(pitches, start=1))
    parts = []
    for part in score.parts:
        staves = []
        for staff in part.staves:
            measures: list[Measure] = []
            for measure in staff.measures:
                events = []
                for event in measure.events:
                    if event.kind is EventKind.NOTE:
                        position, sounding = next(remaining)
                        read_letter, _, read_octave = split_pitch(event.pitch)
                        letter, _, octave = split_pitch(sounding)
                        if (read_letter, read_octave) != (letter, octave):
                            raise SemanticMismatch(
                                f"nota {position}: el MEI dice {event.pitch} y el "
                                f".semantic, {sounding}"
                            )
                        event = replace(event, pitch=sounding)
                    events.append(event)
                measures.append(replace(measure, events=tuple(events)))
            staves.append(replace(staff, measures=tuple(measures)))
        parts.append(replace(part, staves=tuple(staves)))
    return replace(score, parts=tuple(parts))
