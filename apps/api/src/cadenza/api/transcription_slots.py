"""Tope de transcripciones que la API calcula a la vez (#165, ADR-0024)."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException, status

# Cuánto espera una transcripción a que quede un hueco antes de responder 503. Corta frente a los
# 30 s del cliente (ADR-0016): mejor un «ocupado» claro que un timeout.
SLOT_WAIT_SECONDS = 10.0
RETRY_AFTER_SECONDS = 10
_POLL_SECONDS = 0.1


class TranscriptionSlots:
    """Huecos de transcripción con su propio grupo de hilos, uno por hueco.

    Con un hilo por hueco, quien tiene hueco nunca espera a un hilo libre, y las transcripciones no
    compiten con el resto de `asyncio.to_thread` por el ejecutor por defecto.
    """

    def __init__(self, size: int) -> None:
        self.size = size
        self.semaphore = threading.BoundedSemaphore(size)
        self.executor = ThreadPoolExecutor(max_workers=size, thread_name_prefix="transcripcion")

    def try_acquire(self, *, require_idle: bool = False) -> bool:
        """Toma un hueco sin esperar. Con `require_idle`, solo si están libres todos.

        HOMR calcula de una en una: con un hueco ocupado, el otro es el de espera de quien entra,
        y una transcripción sin cuenta no debe quitárselo (#278, ADR-0054 §5). Se toman todos y
        se devuelven todos menos uno; si alguno falta, se devuelven los tomados.
        """
        if not require_idle:
            return self.semaphore.acquire(blocking=False)
        taken = 0
        while taken < self.size and self.semaphore.acquire(blocking=False):
            taken += 1
        keep = 1 if taken == self.size else 0
        for _ in range(taken - keep):
            self.semaphore.release()
        return keep == 1


async def run_in_transcription_slot[T](
    slots: TranscriptionSlots,
    func: Callable[[], T],
    *,
    wait_seconds: float | None = None,
    require_idle: bool = False,
) -> T:
    """Ejecuta `func` en un hilo cuando hay hueco; si no lo hay a tiempo, responde 503.

    El hueco se libera cuando el trabajo termina, o si se cancela antes de empezar; nunca al
    cancelarse la petición con el trabajo en marcha, que sigue ocupándolo hasta acabar. Con
    `require_idle`, solo empieza si están libres todos los huecos (`try_acquire`).
    """

    deadline = time.monotonic() + (SLOT_WAIT_SECONDS if wait_seconds is None else wait_seconds)
    while not slots.try_acquire(require_idle=require_idle):
        if time.monotonic() >= deadline:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "El servidor está ocupado con otras transcripciones. "
                    "Inténtalo de nuevo en unos segundos."
                ),
                headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
            )
        await asyncio.sleep(_POLL_SECONDS)

    try:
        future = slots.executor.submit(func)
    except BaseException:
        slots.semaphore.release()
        raise
    # El callback corre una sola vez: al acabar el trabajo (bien o con error) o al cancelarse el
    # futuro antes de que un hilo lo tome. Cancelar la petición con el trabajo en marcha no lo
    # cancela: el futuro sigue hasta terminar y entonces libera el hueco.
    future.add_done_callback(lambda _future: slots.semaphore.release())
    return await asyncio.wrap_future(future)
