"""Puerto de la caché del estado materializado de una sesión (#275, ADR-0037).

El estado de una sesión en `seq` es el `ScoreIR` crudo con sus `seq` primeras ediciones
aplicadas (ADR-0007). El log es solo de añadir, así que ese estado no cambia nunca: se puede
guardar, con su MusicXML y su mapa de tiempos, y servirlo otra vez sin rehacerlo.

La clave lleva el identificador de la última edición aplicada. Una edición que se valida y se
guarda en la caché, pero cuya transacción no llega a confirmarse, deja una entrada con un
identificador que el log nunca tendrá: otra edición con el mismo `seq` no la encuentra.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass

from cadenza.domain import ScoreIR, TimingMap


@dataclass(frozen=True, slots=True)
class ScoreStateKey:
    """Un estado de una sesión: su `seq` y la edición que lo produjo (None en el estado 0)."""

    session_id: str
    seq: int
    last_edit_id: str | None


@dataclass(frozen=True, slots=True)
class CachedScoreState:
    """El `ScoreIR` materializado de un estado y, una vez calculados, su MusicXML y sus tiempos.

    `ScoreIR` y `TimingMap` son inmutables: se comparten entre peticiones sin copiarlos.
    """

    score: ScoreIR
    musicxml: str | None = None
    timing: TimingMap | None = None


class ScoreStateCache(ABC):
    """Caché de estados materializados por `(sesión, seq, última edición)`."""

    @abstractmethod
    def get(self, key: ScoreStateKey) -> CachedScoreState | None:
        """El estado guardado con esa clave, o None."""

    @abstractmethod
    def put(self, key: ScoreStateKey, state: CachedScoreState) -> None:
        """Guarda (o sustituye) el estado de esa clave."""

    @abstractmethod
    def invalidate(self, session_id: str) -> None:
        """Olvida todos los estados de la sesión.

        Lo necesita lo que cambie la partitura sin pasar por el log, como el título y los
        instrumentos de #235.
        """


class InMemoryScoreStateCache(ScoreStateCache):
    """Caché en el proceso, con los `max_entries` estados usados más recientemente.

    Es la de producción: una instancia de la API, un proceso (ADR-0015). Segura entre hilos:
    las rutas síncronas de FastAPI corren en un grupo de hilos. Con `max_entries=0` no guarda
    nada.
    """

    def __init__(self, max_entries: int = 32) -> None:
        if max_entries < 0:
            raise ValueError("max_entries no puede ser negativo")
        self._max_entries = max_entries
        self._entries: OrderedDict[ScoreStateKey, CachedScoreState] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: ScoreStateKey) -> CachedScoreState | None:
        with self._lock:
            state = self._entries.get(key)
            if state is not None:
                self._entries.move_to_end(key)
            return state

    def put(self, key: ScoreStateKey, state: CachedScoreState) -> None:
        if self._max_entries == 0:
            return
        with self._lock:
            self._entries[key] = state
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def invalidate(self, session_id: str) -> None:
        with self._lock:
            for key in [k for k in self._entries if k.session_id == session_id]:
                del self._entries[key]

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
