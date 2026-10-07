"""Puerto abstracto de repositorio de sesiones (ADR-0009)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from cadenza.domain import Finding


@dataclass(frozen=True)
class SessionData:
    """Representación desacoplada de los datos de una sesión."""

    id: str
    document_id: str
    omr_engine: str
    document: dict[str, Any]
    created_at: datetime | None = None
    image_artifact: str | None = None
    model_version: str | None = None
    status: str = "transcribed"
    owner_id: str = "default-user"


@dataclass(frozen=True)
class PersistedFinding:
    """Representación desacoplada de un hallazgo persistido con su identificador."""

    id: int
    rule_id: str
    severity: str
    message: str
    suggested_fix: str | None
    anchor: dict[str, Any]
    at_seq: int = 0


class SessionRepository(ABC):
    """Puerto de persistencia para sesiones y sus hallazgos."""

    @abstractmethod
    def add(self, session: SessionData, findings: Sequence[Finding]) -> SessionData:
        """Persiste una nueva sesión y sus hallazgos asociados."""

    @abstractmethod
    def get(self, session_id: str) -> SessionData | None:
        """Recupera los datos de la sesión o None si no existe."""

    @abstractmethod
    def list_findings(self, session_id: str) -> tuple[PersistedFinding, ...]:
        """Devuelve los hallazgos vigentes asociados a la sesión."""

    @abstractmethod
    def list(self, owner_id: str | None = None) -> tuple[SessionData, ...]:
        """Devuelve el listado de sesiones, opcionalmente filtrado por propietario."""
