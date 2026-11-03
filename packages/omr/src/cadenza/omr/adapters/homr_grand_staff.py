"""Qué pentagramas de un sistema de tres forman el piano en HOMR y cómo se leen (#239, #325,
ADR-0060).

HOMR 0.7 junta dos pentagramas vecinos en un gran pentagrama (el piano) si un elemento alto a la
izquierda del sistema (la llave) los abarca: puntúa cada par con lo que el elemento se solapa con
el par menos su distancia a los pentagramas, y se queda con el par de más puntos
(`MultiStaff._select_grandstaffs`). En una página de voz y piano, la barra que une los tres
pentagramas al principio de cada sistema también cuenta como llave, a veces fundida con la llave
de verdad: abarca los dos pares, y gana el de arriba (voz y mano derecha) cuando el hueco de la
letra es mayor que el que hay entre las manos. La voz y la mano derecha salen entonces en una
parte y la mano izquierda en otra, sistema a sistema.

Aquí, en un sistema de tres pentagramas, un elemento que abarca los tres no decide el par: solo
cuentan los que abarcan menos. Si solo hay de los que abarcan los tres, el piano son los dos de
abajo, como en toda partitura de una voz o un instrumento por encima del piano (el alcance de
#239). Los sistemas de dos o de más de tres pentagramas siguen como los deja HOMR.

El piano encontrado se lee de una de dos maneras (`PianoReading`, #325): emparejado, como un gran
pentagrama (lo de #239), o con cada pentagrama solo, sin emparejar ninguno del sistema. Fuera de
`reading`, se empareja. `reading` dice además en qué sistemas había piano, para que el adaptador
lea la página de las dos maneras y las combine (`homr_piano`). HOMR se llama de uno en uno en
todo el proceso (`homr._HOMR_LOCK`), así que la lectura en curso es una sola.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

SYSTEM_STAFFS = 3
"""Pentagramas del sistema en el que se aplica: una voz o un instrumento y el piano."""

_PATCHED_ATTRIBUTE = "_cadenza_voice_above_piano"


class PianoReading(StrEnum):
    """Cómo lee HOMR el piano de un sistema de tres pentagramas."""

    PAIRED = "paired"
    """Las dos manos como un gran pentagrama, en una misma imagen (#239)."""
    ALONE = "alone"
    """Cada pentagrama del sistema solo (#325)."""


@dataclass
class ReadingRecord:
    """Una lectura de HOMR: cómo se lee el piano y los pares de piano que se encontraron."""

    mode: PianoReading
    piano_pairs: list[list[int]] = field(default_factory=list)


_current: ReadingRecord | None = None


@contextmanager
def reading(mode: PianoReading) -> Iterator[ReadingRecord]:
    """Lee el piano de los sistemas de tres pentagramas como dice `mode` mientras dura."""

    global _current
    record = ReadingRecord(mode)
    previous, _current = _current, record
    try:
        yield record
    finally:
        _current = previous


def _vertical_extent(symbol: Any) -> tuple[float, float]:
    """Lo alto que ocupa el elemento, medido como lo mide HOMR (centro y alto de la caja)."""
    center_y = float(symbol.center[1])
    half_height = float(symbol.size[1]) / 2
    return center_y - half_height, center_y + half_height


def covers_every_staff(symbol: Any, staffs: Sequence[Any]) -> bool:
    """Si el elemento abarca al menos la mitad del alto de cada pentagrama del sistema."""
    top, bottom = _vertical_extent(symbol)
    for staff in staffs:
        overlap = min(bottom, float(staff.max_y)) - max(top, float(staff.min_y))
        if overlap < (float(staff.max_y) - float(staff.min_y)) / 2:
            return False
    return True


def piano_pairs(
    original: Callable[[Any, list[Any]], list[Any]],
    multi_staff: Any,
    brace_dot: list[Any],
) -> list[Any]:
    """El par de pentagramas del piano en un sistema de tres, con la regla del módulo.

    `original` es `MultiStaff._select_grandstaffs` de HOMR: devuelve los pares elegidos
    (`MultiStaff.GrandStaffPair`, con `get_index()` y `get_score()`).
    """
    staffs = list(multi_staff.staffs)
    own = [symbol for symbol in brace_dot if not covers_every_staff(symbol, staffs)]
    # HOMR toma el máximo de los elementos: con una lista vacía fallaría.
    pairs = original(multi_staff, own) if own else []
    if pairs:
        return pairs
    spanning = [symbol for symbol in brace_dot if covers_every_staff(symbol, staffs)]
    by_spanning = original(multi_staff, spanning) if spanning else []
    if not by_spanning:
        return []
    pair_type = type(by_spanning[0])
    return [pair_type([1, 2], max(pair.get_score() for pair in by_spanning))]


def select_grandstaffs_voice_above_piano(
    original: Callable[[Any, list[Any]], list[Any]],
    multi_staff: Any,
    brace_dot: list[Any],
    record: ReadingRecord | None = None,
) -> list[Any]:
    """Los pares que HOMR lee como un gran pentagrama en un sistema.

    En un sistema de tres pentagramas, el piano de `piano_pairs`, que se anota en `record`; con
    `PianoReading.ALONE`, ninguno. Los demás sistemas, como los deja HOMR.
    """
    if len(multi_staff.staffs) != SYSTEM_STAFFS:
        return original(multi_staff, brace_dot)
    pairs = piano_pairs(original, multi_staff, brace_dot)
    if record is None:
        return pairs
    record.piano_pairs.extend(list(pair.get_index()) for pair in pairs)
    return [] if record.mode is PianoReading.ALONE else pairs


def install(multi_staff_class: Any) -> None:
    """Sustituye la elección de HOMR en la clase `MultiStaff`; llamarla otra vez no hace nada.

    Falla si la versión de HOMR no tiene `_select_grandstaffs`: sin la sustitución, la voz y la
    mano derecha volverían a juntarse en silencio.
    """
    current = getattr(multi_staff_class, "_select_grandstaffs", None)
    if current is None:
        raise RuntimeError(
            "homr.model.MultiStaff no tiene '_select_grandstaffs'. Verifica la versión instalada "
            "de HOMR: sin esta sustitución, la voz y la mano derecha del piano se juntan en una "
            "parte (#239, ADR-0060)."
        )
    if getattr(current, _PATCHED_ATTRIBUTE, False):
        return
    original = current

    # `wraps` deja en `__wrapped__` la elección de HOMR sin sustituir, para compararla.
    @functools.wraps(original)
    def select(self: Any, brace_dot: list[Any]) -> list[Any]:
        return select_grandstaffs_voice_above_piano(original, self, brace_dot, _current)

    setattr(select, _PATCHED_ATTRIBUTE, True)
    multi_staff_class._select_grandstaffs = select
