"""Partituras sintéticas para las pruebas de las reglas, escritas como se leen."""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction

from cadenza.domain import (
    Clef,
    Event,
    EventKind,
    KeySignature,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Staff,
    Tie,
    TimeSignature,
    build_anchor_index,
)

# Figuras, en negras.
REDONDA = Fraction(4)
BLANCA = Fraction(2)
BLANCA_PUNTILLO = Fraction(3)
NEGRA = Fraction(1)
CORCHEA = Fraction(1, 2)
CORCHEA_TRESILLO = Fraction(1, 3)


def n(
    pitch: str,
    duration: Fraction | None,
    *,
    voice: int = 0,
    tie: Tie | None = None,
    chord: bool = False,
) -> Event:
    return Event(
        kind=EventKind.NOTE,
        pitch=pitch,
        duration_beats=duration,
        voice=voice,
        tie=tie,
        is_chord=chord,
    )


def r(
    duration: Fraction | None,
    *,
    voice: int = 0,
    tie: Tie | None = None,
    hidden: bool = False,
) -> Event:
    return Event(kind=EventKind.REST, duration_beats=duration, voice=voice, tie=tie, hidden=hidden)


def m(
    number: int,
    *events: Event,
    time: tuple[int, int] | None = (4, 4),
    fifths: int | None = None,
    clef: Clef | None = None,
) -> Measure:
    return Measure(
        number=number,
        events=events,
        time_signature=None if time is None else TimeSignature(*time),
        key_signature=None if fifths is None else KeySignature(fifths=fifths),
        clef=clef,
    )


def full(number: int, time: tuple[int, int] = (4, 4), *, voice: int = 0) -> Measure:
    """Un compás lleno con una sola figura (o con negras si no hay figura que lo llene)."""
    capacity = TimeSignature(*time).quarter_length
    if capacity in (REDONDA, BLANCA, BLANCA_PUNTILLO, NEGRA, Fraction(3, 2)):
        return m(number, n("C5", capacity, voice=voice), time=time)
    quarters = [n("C5", NEGRA, voice=voice) for _ in range(int(capacity))]
    return m(number, *quarters, time=time)


def document(*staves: Sequence[Measure]) -> ScoreDocument:
    """Una parte con un pentagrama por secuencia de compases."""
    part = Part(
        id="P1",
        staves=tuple(
            Staff(id=f"P1-S{index + 1}", measures=tuple(measures))
            for index, measures in enumerate(staves)
        ),
    )
    score = ScoreIR(parts=(part,))
    return ScoreDocument(
        id="doc", score=score, anchors=build_anchor_index(score), provenance=Provenance("fake")
    )


def surrounded(target: Measure, time: tuple[int, int] = (4, 4)) -> ScoreDocument:
    """El compás entre compases llenos: ni el primero ni el último de su pentagrama."""
    before = [full(number, time) for number in range(1, target.number)]
    if not before:
        raise ValueError("el compás de prueba no puede ser el primero")
    return document([*before, target, full(target.number + 1, time)])
