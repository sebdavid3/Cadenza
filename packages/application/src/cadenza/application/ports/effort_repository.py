"""Puerto abstracto del repositorio de métricas de esfuerzo (ADR-0004, #13, ADR-0050)."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Literal

FindingAction = Literal["dismissed", "restored"]
"""Una orden sobre un posible error que cambió su estado (ADR-0050 §4)."""


@dataclass(frozen=True)
class EffortSegment:
    """Un tramo de la medición: el tiempo con la página visible y con actividad que midió una
    pestaña de la sesión (ADR-0050 §2). `first_edit_ms` es el tiempo del tramo en el momento en
    que se guardó la primera edición del log, si fue en este tramo; `idle_threshold_ms`, el
    umbral de las pausas con que lo midió la vista, para comprobar que todo el estudio usó el
    mismo."""

    id: str
    active_ms: int
    first_edit_ms: int | None = None
    idle_threshold_ms: int | None = None

    def to_primitive(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "active_ms": self.active_ms,
            "first_edit_ms": self.first_edit_ms,
            "idle_threshold_ms": self.idle_threshold_ms,
        }

    @classmethod
    def from_primitive(cls, data: dict[str, Any]) -> EffortSegment:
        first = data.get("first_edit_ms")
        threshold = data.get("idle_threshold_ms")
        return cls(
            id=str(data["id"]),
            active_ms=int(data["active_ms"]),
            first_edit_ms=None if first is None else int(first),
            idle_threshold_ms=None if threshold is None else int(threshold),
        )


@dataclass(frozen=True)
class EffortMetricsData:
    """Datos desacoplados de métricas de esfuerzo de corrección humana.

    Un registro `accumulated` es el único que acumula la web para la sesión (#188, ADR-0050):
    `duration_ms` y `time_to_first_edit_ms` salen de sus `segments`; `interventions` (por
    compás) e `interventions_by_class` (por clase de operación y compás), del log; los
    contadores, de las órdenes sobre los posibles errores y de las respuestas a las sugerencias.
    Los demás son registros sueltos de `POST /effort` (#13), con los valores que se enviaron.
    """

    id: str
    session_id: str
    duration_ms: int
    time_to_first_edit_ms: int | None
    interventions: dict[str, int]
    created_at: datetime
    accumulated: bool = False
    segments: tuple[EffortSegment, ...] = ()
    interventions_by_class: dict[str, dict[str, int]] = field(default_factory=dict)
    findings_dismissed: int = 0
    findings_restored: int = 0
    suggestions_applied: int = 0
    suggestions_rejected: int = 0
    updated_at: datetime | None = None


def empty_accumulated(session_id: str, now: datetime) -> EffortMetricsData:
    """El registro acumulado de una sesión antes de medir nada."""
    return EffortMetricsData(
        id=str(uuid.uuid4()),
        session_id=session_id,
        duration_ms=0,
        time_to_first_edit_ms=None,
        interventions={},
        created_at=now,
        accumulated=True,
        updated_at=now,
    )


class EffortRepository(ABC):
    """Contrato del repositorio de métricas de esfuerzo."""

    @abstractmethod
    def add(self, metrics: EffortMetricsData) -> EffortMetricsData:
        """Persiste una medición de esfuerzo de corrección."""

    @abstractmethod
    def list_by_session(self, session_id: str) -> tuple[EffortMetricsData, ...]:
        """Devuelve todas las mediciones de esfuerzo de una sesión ordenadas por fecha."""

    @abstractmethod
    def get_latest(self, session_id: str) -> EffortMetricsData | None:
        """Devuelve la medición de esfuerzo más reciente de la sesión, o None."""

    @abstractmethod
    def get_accumulated(
        self, session_id: str, *, for_update: bool = False
    ) -> EffortMetricsData | None:
        """El registro que acumula la web para la sesión (ADR-0050), o None si aún no hay.

        Con `for_update`, la fila queda bloqueada hasta el final de la transacción: quien lo lee
        para reescribirlo no pisa otra escritura que llegue a la vez (`SELECT … FOR UPDATE`).
        """

    @abstractmethod
    def save_accumulated(self, metrics: EffortMetricsData) -> EffortMetricsData:
        """Crea o actualiza el registro acumulado de la sesión: los tramos, lo que sale de ellos,
        del log y de las sugerencias, y `updated_at`. No toca los contadores de los posibles
        errores, que solo suma `add_finding_action`."""

    @abstractmethod
    def add_finding_action(
        self, session_id: str, action: FindingAction, *, now: datetime
    ) -> EffortMetricsData:
        """Suma uno al contador de la acción en el registro acumulado, creándolo si no hay."""


class InMemoryEffortRepository(EffortRepository):
    """Implementación en memoria de EffortRepository para pruebas unitarias."""

    def __init__(self) -> None:
        self.records: dict[str, list[EffortMetricsData]] = {}

    def add(self, metrics: EffortMetricsData) -> EffortMetricsData:
        self.records.setdefault(metrics.session_id, []).append(metrics)
        return metrics

    def list_by_session(self, session_id: str) -> tuple[EffortMetricsData, ...]:
        return tuple(self.records.get(session_id, []))

    def get_latest(self, session_id: str) -> EffortMetricsData | None:
        entries = self.records.get(session_id, [])
        return entries[-1] if entries else None

    def get_accumulated(
        self, session_id: str, *, for_update: bool = False
    ) -> EffortMetricsData | None:
        return next((m for m in self.records.get(session_id, []) if m.accumulated), None)

    def _put(self, metrics: EffortMetricsData) -> EffortMetricsData:
        entries = self.records.setdefault(metrics.session_id, [])
        for index, stored in enumerate(entries):
            if stored.accumulated:
                entries[index] = metrics
                return metrics
        entries.append(metrics)
        return metrics

    def save_accumulated(self, metrics: EffortMetricsData) -> EffortMetricsData:
        stored = self.get_accumulated(metrics.session_id)
        if stored is not None:
            metrics = replace(
                metrics,
                id=stored.id,
                created_at=stored.created_at,
                findings_dismissed=stored.findings_dismissed,
                findings_restored=stored.findings_restored,
            )
        return self._put(replace(metrics, accumulated=True))

    def add_finding_action(
        self, session_id: str, action: FindingAction, *, now: datetime
    ) -> EffortMetricsData:
        stored = self.get_accumulated(session_id) or empty_accumulated(session_id, now)
        if action == "dismissed":
            stored = replace(stored, findings_dismissed=stored.findings_dismissed + 1)
        else:
            stored = replace(stored, findings_restored=stored.findings_restored + 1)
        return self._put(replace(stored, updated_at=now))
