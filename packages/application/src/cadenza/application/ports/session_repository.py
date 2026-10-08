"""Puerto abstracto de repositorio de sesiones (ADR-0009)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from cadenza.domain import Finding

from ..exceptions import FindingNotFound, SessionNotFound


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
    validated_at_seq: int = 0


@dataclass(frozen=True)
class SessionSummary:
    """Resumen ligero de una sesión para listados sin cargar el documento JSONB (#27)."""

    session_id: str
    document_id: str
    omr_engine: str
    model_version: str | None
    status: str
    created_at: datetime
    owner_id: str
    findings_count: int
    edits_count: int


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
    status: str = "active"
    dismissed_at: datetime | None = None
    dismissed_by: str | None = None
    dismissal_reason: str | None = None


class SessionRepository(ABC):
    """Puerto de persistencia para sesiones y sus hallazgos."""

    @abstractmethod
    def add(self, session: SessionData, findings: Sequence[Finding]) -> SessionData:
        """Persiste una nueva sesión y sus hallazgos asociados."""

    @abstractmethod
    def get(self, session_id: str) -> SessionData | None:
        """Recupera los datos de la sesión o None si no existe."""

    @abstractmethod
    def replace_findings(
        self,
        session_id: str,
        findings: Sequence[Finding],
        *,
        at_seq: int,
        dismissed_statuses: Sequence[PersistedFinding | None] | None = None,
    ) -> tuple[PersistedFinding, ...]:
        """Persiste los hallazgos evaluados en at_seq y actualiza los hallazgos vigentes.

        Es idempotente por `(session_id, at_seq)`: re-evaluar el mismo estado
        sustituye los hallazgos de ese `at_seq`. Los hallazgos de otras
        secuencias se conservan para el análisis de esfuerzo (#11, ADR-0013).
        Si se provee `dismissed_statuses`, preserva el estado descartado de
        los hallazgos correspondientes (#36).
        Lanza `SessionNotFound` si la sesión no existe.
        """

    @abstractmethod
    def dismiss_finding(
        self,
        session_id: str,
        finding_id: int,
        *,
        user: str,
        reason: str | None = None,
    ) -> PersistedFinding:
        """Marca un hallazgo como descartado (falso positivo, #36)."""

    @abstractmethod
    def restore_finding(
        self,
        session_id: str,
        finding_id: int,
    ) -> PersistedFinding:
        """Restaura un hallazgo previamente descartado a estado activo (#36)."""

    @abstractmethod
    def list_findings(
        self,
        session_id: str,
        *,
        at_seq: int | None = None,
        latest_only: bool = True,
        include_dismissed: bool = False,
    ) -> tuple[PersistedFinding, ...]:
        """Devuelve los hallazgos asociados a la sesión.

        Por defecto (`latest_only=True`, `include_dismissed=False`), devuelve los hallazgos
        vigentes del estado más reciente evaluado (`validated_at_seq`) que no han sido
        descartados. Si `include_dismissed=True`, incluye también los hallazgos descartados.
        """

    @abstractmethod
    def list_dismissed_findings(
        self,
        session_id: str,
    ) -> tuple[PersistedFinding, ...]:
        """Devuelve los falsos positivos descartados de la sesión (#36, #18)."""

    @abstractmethod
    def update_status(self, session_id: str, status: str) -> SessionData:
        """Actualiza el estado del ciclo de vida de la sesión (#34, ADR-0014)."""

    @abstractmethod
    def list(
        self,
        owner_id: str | None = None,
        status: str | None = None,
    ) -> tuple[SessionData, ...]:
        """Devuelve el listado de sesiones, opcionalmente filtrado por propietario y/o estado."""

    @abstractmethod
    def list_summaries(
        self,
        *,
        owner_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[SessionSummary, ...]:
        """Devuelve resúmenes de sesiones ordenados por created_at descendente (#27)."""


class InMemorySessionRepository(SessionRepository):
    """Implementación en memoria de SessionRepository para pruebas unitarias."""

    def __init__(self, edit_repository: Any | None = None) -> None:
        self.sessions: dict[str, SessionData] = {}
        self.findings: dict[str, list[PersistedFinding]] = {}
        self._next_finding_id = 1
        self.edit_repository = edit_repository

    def add(self, session: SessionData, findings: Sequence[Finding]) -> SessionData:
        self.sessions[session.id] = session
        persisted: list[PersistedFinding] = []
        for finding in findings:
            persisted.append(
                PersistedFinding(
                    id=self._next_finding_id,
                    rule_id=finding.rule_id,
                    severity=finding.severity.value,
                    message=finding.message,
                    suggested_fix=finding.suggested_fix,
                    anchor=finding.anchor.to_primitive(),
                    at_seq=finding.at_seq,
                )
            )
            self._next_finding_id += 1
        self.findings[session.id] = persisted
        return session

    def get(self, session_id: str) -> SessionData | None:
        return self.sessions.get(session_id)

    def replace_findings(
        self,
        session_id: str,
        findings: Sequence[Finding],
        *,
        at_seq: int,
        dismissed_statuses: Sequence[PersistedFinding | None] | None = None,
    ) -> tuple[PersistedFinding, ...]:
        record = self.sessions.get(session_id)
        if record is None:
            raise SessionNotFound(session_id)

        self.sessions[session_id] = replace(record, validated_at_seq=at_seq)
        # Re-evaluar el mismo estado sustituye sus hallazgos (ADR-0013).
        self.findings[session_id] = [
            f for f in self.findings.get(session_id, []) if f.at_seq != at_seq
        ]

        persisted: list[PersistedFinding] = []
        for i, finding in enumerate(findings):
            d_state = (
                dismissed_statuses[i]
                if dismissed_statuses is not None and i < len(dismissed_statuses)
                else None
            )
            persisted.append(
                PersistedFinding(
                    id=self._next_finding_id,
                    rule_id=finding.rule_id,
                    severity=finding.severity.value,
                    message=finding.message,
                    suggested_fix=finding.suggested_fix,
                    anchor=finding.anchor.to_primitive(),
                    at_seq=at_seq,
                    status=d_state.status if d_state is not None else "active",
                    dismissed_at=d_state.dismissed_at if d_state is not None else None,
                    dismissed_by=d_state.dismissed_by if d_state is not None else None,
                    dismissal_reason=d_state.dismissal_reason if d_state is not None else None,
                )
            )
            self._next_finding_id += 1
        self.findings.setdefault(session_id, []).extend(persisted)
        return tuple(persisted)

    def dismiss_finding(
        self,
        session_id: str,
        finding_id: int,
        *,
        user: str,
        reason: str | None = None,
    ) -> PersistedFinding:
        record = self.sessions.get(session_id)
        if record is None:
            raise SessionNotFound(session_id)

        session_findings = self.findings.get(session_id, [])
        for i, f in enumerate(session_findings):
            if f.id == finding_id:
                updated = replace(
                    f,
                    status="dismissed",
                    dismissed_at=datetime.now(UTC),
                    dismissed_by=user,
                    dismissal_reason=reason,
                )
                session_findings[i] = updated
                return updated
        raise FindingNotFound(finding_id)

    def restore_finding(
        self,
        session_id: str,
        finding_id: int,
    ) -> PersistedFinding:
        record = self.sessions.get(session_id)
        if record is None:
            raise SessionNotFound(session_id)

        session_findings = self.findings.get(session_id, [])
        for i, f in enumerate(session_findings):
            if f.id == finding_id:
                updated = replace(
                    f,
                    status="active",
                    dismissed_at=None,
                    dismissed_by=None,
                    dismissal_reason=None,
                )
                session_findings[i] = updated
                return updated
        raise FindingNotFound(finding_id)

    def list_findings(
        self,
        session_id: str,
        *,
        at_seq: int | None = None,
        latest_only: bool = True,
        include_dismissed: bool = False,
    ) -> tuple[PersistedFinding, ...]:
        record = self.sessions.get(session_id)
        if record is None:
            return ()
        findings_list = self.findings.get(session_id, [])
        if not include_dismissed:
            findings_list = [f for f in findings_list if f.status == "active"]
        if at_seq is not None:
            return tuple(f for f in findings_list if f.at_seq == at_seq)
        if latest_only:
            return tuple(f for f in findings_list if f.at_seq == record.validated_at_seq)
        return tuple(findings_list)

    def list_dismissed_findings(
        self,
        session_id: str,
    ) -> tuple[PersistedFinding, ...]:
        record = self.sessions.get(session_id)
        if record is None:
            return ()
        return tuple(f for f in self.findings.get(session_id, []) if f.status == "dismissed")

    def update_status(self, session_id: str, status: str) -> SessionData:
        record = self.sessions.get(session_id)
        if record is None:
            raise SessionNotFound(session_id)
        updated = replace(record, status=status)
        self.sessions[session_id] = updated
        return updated

    def list(
        self,
        owner_id: str | None = None,
        status: str | None = None,
    ) -> tuple[SessionData, ...]:
        sessions = list(self.sessions.values())
        if owner_id is not None:
            sessions = [s for s in sessions if s.owner_id == owner_id]
        if status is not None:
            sessions = [s for s in sessions if s.status == status]
        return tuple(sessions)

    def list_summaries(
        self,
        *,
        owner_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[SessionSummary, ...]:
        filtered = list(self.sessions.values())
        if owner_id is not None:
            filtered = [s for s in filtered if s.owner_id == owner_id]
        if status is not None:
            filtered = [s for s in filtered if s.status == status]

        sorted_sessions = sorted(
            filtered,
            key=lambda s: s.created_at or datetime.min,
            reverse=True,
        )
        paged = sorted_sessions[offset : offset + limit]
        summaries: list[SessionSummary] = []
        for s in paged:
            session_findings = self.findings.get(s.id, [])
            findings_count = len(
                [
                    f
                    for f in session_findings
                    if f.at_seq == s.validated_at_seq and f.status == "active"
                ]
            )
            edits_count = (
                len(self.edit_repository.list_events(s.id))
                if self.edit_repository is not None
                else 0
            )
            summaries.append(
                SessionSummary(
                    session_id=s.id,
                    document_id=s.document_id,
                    omr_engine=s.omr_engine,
                    model_version=s.model_version,
                    status=s.status,
                    created_at=s.created_at or datetime.min,
                    owner_id=s.owner_id,
                    findings_count=findings_count,
                    edits_count=edits_count,
                )
            )
        return tuple(summaries)
