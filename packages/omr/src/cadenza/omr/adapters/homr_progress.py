"""Avisos de avance desde dentro de HOMR (#375, ADR-0063).

HOMR 0.7 lee una página en dos pasos dentro de `homr.main.process_image`: detecta los pentagramas
(la segmentación y la búsqueda de los sistemas) y después lee cada uno con el transformer en
`homr.staff_parsing.parse_staffs`. Esa función cuenta las voces del sistema con
`_get_number_of_voices` y llama a `parse_staff_image` una vez por voz y sistema. Aquí se envuelven
esas dos funciones del módulo: la primera dice cuántos pentagramas tiene la lectura y la segunda,
cuál empieza. Las envolturas llaman a las originales con los mismos argumentos y devuelven lo
mismo, así que lo leído no cambia.

El adaptador abre una lectura con `reading(...)`, que avisa de que empieza (se detectan los
pentagramas). Fuera de una lectura, las envolturas solo llaman a las originales. HOMR se llama de
uno en uno en todo el proceso (`homr._HOMR_LOCK`), pero la lectura en curso se guarda por hilo,
como quien escucha (`cadenza.omr.progress`).
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from ..progress import OMRProgress, Reading, report

_LOGGER = logging.getLogger(__name__)
_PATCHED_ATTRIBUTE = "_cadenza_progress"
_COUNT_FUNCTION = "_get_number_of_voices"
_READ_FUNCTION = "parse_staff_image"


@dataclass
class _ReadingState:
    reading: Reading
    staffs: int | None = None
    started: int = 0


_CURRENT: ContextVar[_ReadingState | None] = ContextVar("cadenza_homr_reading", default=None)


@contextmanager
def reading(kind: Reading) -> Iterator[None]:
    """Una lectura de la página: avisa de que empieza y numera sus pentagramas mientras dura."""

    token = _CURRENT.set(_ReadingState(kind))
    try:
        report(OMRProgress(kind))
        yield
    finally:
        _CURRENT.reset(token)


def _count_staffs(original: Callable[[list[Any]], int], staffs: list[Any]) -> int:
    """`_get_number_of_voices`: las voces de cada sistema; la lectura tiene voces por sistemas."""

    voices = original(staffs)
    state = _CURRENT.get()
    if state is not None:
        state.staffs = voices * len(staffs)
    return voices


def _read_staff(original: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """`parse_staff_image`: avisa del pentagrama que empieza y lo lee como HOMR."""

    state = _CURRENT.get()
    if state is not None and state.staffs is not None:
        state.started = min(state.started + 1, state.staffs)
        report(OMRProgress(state.reading, staffs=state.staffs, staff=state.started))
    return original(*args, **kwargs)


def install(staff_parsing: Any) -> bool:
    """Envuelve las dos funciones de `homr.staff_parsing`; llamarla otra vez no hace nada.

    Si la versión de HOMR no las tiene, no envuelve nada y devuelve False: sin avisos, la
    transcripción sigue igual (solo se pierde el detalle del avance).
    """

    count = getattr(staff_parsing, _COUNT_FUNCTION, None)
    read = getattr(staff_parsing, _READ_FUNCTION, None)
    if count is None or read is None:
        missing = [
            name for name in (_COUNT_FUNCTION, _READ_FUNCTION) if not hasattr(staff_parsing, name)
        ]
        _LOGGER.warning("homr_progress_unavailable missing=%s", ",".join(missing))
        return False

    if not getattr(count, _PATCHED_ATTRIBUTE, False):
        original_count = count

        @functools.wraps(original_count)
        def counted(staffs: list[Any]) -> int:
            return _count_staffs(original_count, staffs)

        setattr(counted, _PATCHED_ATTRIBUTE, True)
        setattr(staff_parsing, _COUNT_FUNCTION, counted)

    if not getattr(read, _PATCHED_ATTRIBUTE, False):
        original_read = read

        @functools.wraps(original_read)
        def reported(*args: Any, **kwargs: Any) -> Any:
            return _read_staff(original_read, *args, **kwargs)

        setattr(reported, _PATCHED_ATTRIBUTE, True)
        setattr(staff_parsing, _READ_FUNCTION, reported)
    return True
