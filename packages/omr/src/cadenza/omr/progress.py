"""Avance de una transcripción del motor OMR, para decir en qué está (#375, ADR-0063).

El motor avisa de lo que de verdad ha hecho: que empieza una lectura de la página (detectando los
pentagramas) y qué pentagrama de cuántos empieza a leer. Quien quiera seguirlo abre
`listening(listener)` en el hilo que transcribe; sin nadie escuchando, avisar no hace nada.
Seguir el avance no cambia lo que lee el motor, y un fallo de quien escucha no lo interrumpe.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import StrEnum

_LOGGER = logging.getLogger(__name__)


class Reading(StrEnum):
    """Qué lectura de la página hace el motor."""

    FIRST = "first"
    """La lectura de la página: la única, salvo en las de voz y piano."""
    PIANO = "piano"
    """La segunda lectura de una página de voz y piano, con cada mano del piano sola (#325)."""


@dataclass(frozen=True)
class OMRProgress:
    """Un aviso del motor: en qué lectura está y, si ya los detectó, qué pentagrama lee."""

    reading: Reading
    staffs: int | None = None
    """Pentagramas que tiene esta lectura; None mientras se detectan."""
    staff: int | None = None
    """El pentagrama que empieza a leerse, de 1 a `staffs`; None mientras se detectan."""


ProgressListener = Callable[[OMRProgress], None]

_LISTENER: ContextVar[ProgressListener | None] = ContextVar("cadenza_omr_progress", default=None)


@contextmanager
def listening(listener: ProgressListener) -> Iterator[None]:
    """Hace llegar a `listener` los avisos del motor que transcribe en este hilo."""

    token = _LISTENER.set(listener)
    try:
        yield
    finally:
        _LISTENER.reset(token)


def report(progress: OMRProgress) -> None:
    """Avisa a quien escucha en este hilo; si nadie escucha, no hace nada."""

    listener = _LISTENER.get()
    if listener is None:
        return
    try:
        listener(progress)
    except Exception:
        # Seguir el avance nunca tumba una transcripción.
        _LOGGER.exception("omr_progress_listener_failed")
