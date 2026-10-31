"""Tiempo por etapa de una petición, para la cabecera `Server-Timing` (#275, ADR-0037).

La API abre una recogida por petición (`collect_stage_timings`) y los casos de uso marcan sus
etapas (`timed_stage`): la base de datos, materializar el estado, exportarlo y serializar la
respuesta. Fuera de una recogida, marcar una etapa no hace nada. Solo usa la biblioteca
estándar: la capa de aplicación no conoce el servidor HTTP (ADR-0009).
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_TIMINGS: ContextVar[dict[str, float] | None] = ContextVar("cadenza_stage_timings", default=None)


@contextmanager
def collect_stage_timings() -> Iterator[dict[str, float]]:
    """Recoge, en milisegundos y por nombre, las etapas que se marquen dentro del bloque.

    El diccionario es el mismo objeto en las tareas e hilos que copian el contexto (el grupo de
    hilos de las rutas síncronas), así que ve las etapas que marquen.
    """
    timings: dict[str, float] = {}
    token = _TIMINGS.set(timings)
    try:
        yield timings
    finally:
        _TIMINGS.reset(token)


@contextmanager
def timed_stage(name: str) -> Iterator[None]:
    """Suma a la etapa `name` lo que tarda el bloque, si hay una recogida abierta."""
    timings = _TIMINGS.get()
    if timings is None:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        timings[name] = timings.get(name, 0.0) + elapsed_ms
