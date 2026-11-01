"""Duraciones que admite una edición (ADR-0017): las de `SetDuration`, `InsertEvent` y
`SetTuplet` (ADR-0044).

Hasta una longa (16 pulsos de negra) y denominadores 2^a·t con t en {1, 3, 5, 7} hasta 128
(fusas de tresillo, quintillo y septillo). Con ese vocabulario el exportador escribe MusicXML y
MIDI; fuera de él, music21 rechaza duraciones como 1/17 o 3/1000 y tarda sin límite con
duraciones enormes.
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import Final

from .edit_errors import InvalidEditPayload

MAX_DURATION_BEATS: Final[Fraction] = Fraction(16)
MAX_DURATION_DENOMINATOR: Final[int] = 128
TUPLET_FACTORS: Final[frozenset[int]] = frozenset({1, 3, 5, 7})


def check_duration(value: object) -> Fraction:
    """La duración de `value` en negras si es una de las admitidas; `InvalidEditPayload` si no."""

    if isinstance(value, bool) or not isinstance(value, int | float | str | Fraction):
        raise InvalidEditPayload(f"duración no válida: {value!r}")
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidEditPayload(f"duración no válida: {value!r}")
    try:
        duration = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as exc:
        raise InvalidEditPayload(f"duración no válida: {value!r}") from exc
    if not 0 < duration <= MAX_DURATION_BEATS:
        raise InvalidEditPayload(
            f"la duración debe estar entre 0 (excluido) y {MAX_DURATION_BEATS} pulsos: "
            f"{value!r}"
        )
    tuplet = duration.denominator
    while tuplet % 2 == 0:
        tuplet //= 2
    if duration.denominator > MAX_DURATION_DENOMINATOR or tuplet not in TUPLET_FACTORS:
        raise InvalidEditPayload(
            f"duración no representable: {value!r} (el denominador debe ser 2^a·t con t "
            f"1, 3, 5 o 7 y como mucho {MAX_DURATION_DENOMINATOR}, p. ej. '1/2', '1/3', "
            "'3/4')"
        )
    return duration
