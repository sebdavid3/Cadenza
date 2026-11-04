"""Cómo se agrupan las notas de un acorde en una voz (ADR-0049, ADR-0055).

Un acorde es una nota y las que la siguen en su voz marcadas `is_chord`, como los agrupa el
exportador: una nota con `is_chord` que no sigue a otra nota (al empezar la voz o tras un
silencio) no se une a nada y empieza su propio grupo.
"""

from __future__ import annotations

from collections.abc import Sequence

from .anchor import EventKind
from .score import Event


def joins_previous(events: Sequence[Event], index: int) -> bool:
    """Si el evento `index` de una voz es una nota del acorde que empieza antes que él."""

    event = events[index]
    return (
        index > 0
        and event.kind is EventKind.NOTE
        and event.is_chord
        and events[index - 1].kind is EventKind.NOTE
    )


def chord_bounds(events: Sequence[Event], index: int) -> tuple[int, int]:
    """Posiciones `[inicio, fin)` del grupo del evento `index` de una voz: su acorde entero, o
    solo él si no es de un acorde."""

    start = index
    while joins_previous(events, start):
        start -= 1
    end = start + 1
    while end < len(events) and joins_previous(events, end):
        end += 1
    return start, end


def is_chord_head(events: Sequence[Event], index: int) -> bool:
    """Si el evento `index` de una voz es la primera nota de un acorde de dos o más notas."""

    start, end = chord_bounds(events, index)
    return start == index and end - start >= 2 and events[index].kind is EventKind.NOTE
