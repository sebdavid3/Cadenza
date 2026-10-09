"""Puerto abstracto del repositorio de métricas de esfuerzo (ADR-0004, #13)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class EffortMetricsData:
    """Datos desacoplados de métricas de esfuerzo de corrección humana."""

    id: str
    session_id: str
    duration_ms: int
    time_to_first_edit_ms: int | None
    interventions: dict[str, int]
    created_at: datetime


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
