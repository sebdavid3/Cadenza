"""Puerto abstracto de repositorio de sesiones (ADR-0009)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from cadenza.domain import Finding, ScoreMetadata, SuggestedEdit

from ..exceptions import (
    FindingNotFound,
    SessionNotFound,
    SuggestionConflict,
    SuggestionNotFound,
)


@dataclass(frozen=True)
class SessionData:
    """Representación desacoplada de los datos de una sesión.

    `metadata` son el título, el compositor y el instrumento de cada parte, y
    `source_filename`, el nombre del archivo subido (#235, ADR-0041): datos de la sesión, no
    del `ScoreIR` ni del log.
    """

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
    condition: str = "assisted"
    test_score_id: str | None = None
    metadata: ScoreMetadata = field(default_factory=ScoreMetadata)
    source_filename: str | None = None


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
    condition: str = "assisted"
    test_score_id: str | None = None
    metadata: ScoreMetadata = field(default_factory=ScoreMetadata)
    source_filename: str | None = None


@dataclass(frozen=True)
class PersistedSuggestion:
    """Una sugerencia guardada (ADR-0036 §4): la edición propuesta y la respuesta de la persona.

    `finding_id` queda en None si su hallazgo se sustituyó y ella ya tenía respuesta: las
    respuestas nunca se pierden. `rank` es su orden dentro del hallazgo (0 es la primera).
    """

    id: int
    session_id: str
    finding_id: int | None
    at_seq: int
    rank: int
    op: str
    anchor: dict[str, Any]
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    confidence: float | None
    confidence_level: str
    explanation: str
    source: str
    model_version: str | None
    response: str | None = None
    responded_by: str | None = None
    responded_at: datetime | None = None
    applied_seq: int | None = None
    # El rechazo que hereda (ADR-0036 §4): repite la respuesta de esa fila, no es otra.
    inherited_from: int | None = None


@dataclass(frozen=True)
class NewSuggestion:
    """Una sugerencia que se va a guardar con su hallazgo.

    `inherited` es el rechazo de la validación vigente que hereda (ADR-0036 §4): se guarda
    rechazada, con quién y cuándo la rechazó.
    """

    edit: SuggestedEdit
    inherited: PersistedSuggestion | None = None


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
    suggestions: tuple[PersistedSuggestion, ...] = ()


def suggestion_from_new(
    new: NewSuggestion,
    *,
    id: int,
    session_id: str,
    finding_id: int | None,
    at_seq: int,
    rank: int,
) -> PersistedSuggestion:
    """La fila de una sugerencia nueva, con la respuesta que hereda si la hay."""
    edit = new.edit
    inherited = new.inherited
    return PersistedSuggestion(
        id=id,
        session_id=session_id,
        finding_id=finding_id,
        at_seq=at_seq,
        rank=rank,
        op=edit.op.value,
        anchor=edit.anchor.to_primitive(),
        before=None if edit.before is None else dict(edit.before),
        after=None if edit.after is None else dict(edit.after),
        confidence=edit.confidence,
        confidence_level=edit.confidence_level or "medium",
        explanation=edit.explanation,
        source=edit.source,
        model_version=edit.model_version,
        response=None if inherited is None else inherited.response,
        responded_by=None if inherited is None else inherited.responded_by,
        responded_at=None if inherited is None else inherited.responded_at,
        inherited_from=None if inherited is None else inherited.inherited_from or inherited.id,
    )


class SessionRepository(ABC):
    """Puerto de persistencia para sesiones y sus hallazgos."""

    @abstractmethod
    def add(
        self,
        session: SessionData,
        findings: Sequence[Finding],
        suggestions: Sequence[Sequence[NewSuggestion]] | None = None,
    ) -> SessionData:
        """Persiste una nueva sesión y sus hallazgos asociados.

        `suggestions[i]` son las sugerencias del hallazgo `findings[i]` (ADR-0036 §4).
        """

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
        suggestions: Sequence[Sequence[NewSuggestion]] | None = None,
    ) -> tuple[PersistedFinding, ...]:
        """Persiste los hallazgos evaluados en at_seq y actualiza los hallazgos vigentes.

        Es idempotente por `(session_id, at_seq)`: re-evaluar el mismo estado
        sustituye los hallazgos de ese `at_seq`. Los hallazgos de otras
        secuencias se conservan para el análisis de esfuerzo (#11, ADR-0013).
        Si se provee `dismissed_statuses`, preserva el estado descartado de
        los hallazgos correspondientes (#36).
        `suggestions[i]` son las sugerencias del hallazgo `findings[i]`. Al sustituir los
        hallazgos de ese `at_seq`, sus sugerencias sin respuesta se borran con ellos y las que
        tienen respuesta se conservan desvinculadas (`finding_id` None, ADR-0036 §4).
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
    def get_suggestion(self, session_id: str, suggestion_id: int) -> PersistedSuggestion | None:
        """La sugerencia de la sesión con ese id, o None (ADR-0036 §5)."""

    @abstractmethod
    def respond_suggestion(
        self,
        session_id: str,
        suggestion_id: int,
        *,
        response: str,
        user: str,
        applied_seq: int | None = None,
    ) -> PersistedSuggestion:
        """Guarda la respuesta (`accepted` o `rejected`), quién y cuándo, solo si no tenía
        ninguna: la respuesta guardada no cambia después (ADR-0036 §5). `SuggestionNotFound` si
        no está y `SuggestionConflict` si ya tenía respuesta (dos peticiones a la vez)."""

    @abstractmethod
    def list_suggestions(
        self, session_id: str, *, at_seq: int | None = None
    ) -> tuple[PersistedSuggestion, ...]:
        """Las sugerencias de la sesión (de un `at_seq` si se da), por id."""

    @abstractmethod
    def update_status(self, session_id: str, status: str) -> SessionData:
        """Actualiza el estado del ciclo de vida de la sesión (#34, ADR-0014)."""

    @abstractmethod
    def update_metadata(self, session_id: str, metadata: ScoreMetadata) -> SessionData:
        """Sustituye el título, el compositor y los instrumentos de la sesión (#235, ADR-0041).

        No toca el log, el estado ni nada más. Lanza `SessionNotFound` si la sesión no existe.
        """

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
        condition: str | None = None,
        test_score_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[SessionSummary, ...]:
        """Devuelve resúmenes de sesiones ordenados por created_at descendente (#27)."""


class InMemorySessionRepository(SessionRepository):
    """Implementación en memoria de SessionRepository para pruebas unitarias."""

    def __init__(self, edit_repository: Any | None = None) -> None:
        self.sessions: dict[str, SessionData] = {}
        self.findings: dict[str, list[PersistedFinding]] = {}
        self.suggestions: dict[str, list[PersistedSuggestion]] = {}
        self._next_finding_id = 1
        self._next_suggestion_id = 1
        self.edit_repository = edit_repository

    def _store_suggestions(
        self,
        session_id: str,
        persisted: Sequence[PersistedFinding],
        suggestions: Sequence[Sequence[NewSuggestion]] | None,
    ) -> None:
        if suggestions is None:
            return
        rows = self.suggestions.setdefault(session_id, [])
        for finding, news in zip(persisted, suggestions, strict=True):
            for rank, new in enumerate(news):
                rows.append(
                    suggestion_from_new(
                        new,
                        id=self._next_suggestion_id,
                        session_id=session_id,
                        finding_id=finding.id,
                        at_seq=finding.at_seq,
                        rank=rank,
                    )
                )
                self._next_suggestion_id += 1

    def _with_suggestions(self, session_id: str, finding: PersistedFinding) -> PersistedFinding:
        attached = tuple(
            sorted(
                (s for s in self.suggestions.get(session_id, []) if s.finding_id == finding.id),
                key=lambda s: s.rank,
            )
        )
        return replace(finding, suggestions=attached)

    def add(
        self,
        session: SessionData,
        findings: Sequence[Finding],
        suggestions: Sequence[Sequence[NewSuggestion]] | None = None,
    ) -> SessionData:
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
        self._store_suggestions(session.id, persisted, suggestions)
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
        suggestions: Sequence[Sequence[NewSuggestion]] | None = None,
    ) -> tuple[PersistedFinding, ...]:
        record = self.sessions.get(session_id)
        if record is None:
            raise SessionNotFound(session_id)

        self.sessions[session_id] = replace(record, validated_at_seq=at_seq)
        # Las sugerencias de ese estado: sin respuesta se van con su hallazgo; con respuesta se
        # conservan desvinculadas (ADR-0036 §4).
        self.suggestions[session_id] = [
            s if s.at_seq != at_seq else replace(s, finding_id=None)
            for s in self.suggestions.get(session_id, [])
            if s.at_seq != at_seq or s.response is not None
        ]
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
        self._store_suggestions(session_id, persisted, suggestions)
        return tuple(self._with_suggestions(session_id, f) for f in persisted)

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
                return self._with_suggestions(session_id, updated)
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
                return self._with_suggestions(session_id, updated)
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
            findings_list = [f for f in findings_list if f.at_seq == at_seq]
        elif latest_only:
            findings_list = [f for f in findings_list if f.at_seq == record.validated_at_seq]
        return tuple(self._with_suggestions(session_id, f) for f in findings_list)

    def list_dismissed_findings(
        self,
        session_id: str,
    ) -> tuple[PersistedFinding, ...]:
        record = self.sessions.get(session_id)
        if record is None:
            return ()
        return tuple(
            self._with_suggestions(session_id, f)
            for f in self.findings.get(session_id, [])
            if f.status == "dismissed"
        )

    def get_suggestion(self, session_id: str, suggestion_id: int) -> PersistedSuggestion | None:
        return next(
            (s for s in self.suggestions.get(session_id, []) if s.id == suggestion_id), None
        )

    def respond_suggestion(
        self,
        session_id: str,
        suggestion_id: int,
        *,
        response: str,
        user: str,
        applied_seq: int | None = None,
    ) -> PersistedSuggestion:
        rows = self.suggestions.get(session_id, [])
        for i, row in enumerate(rows):
            if row.id == suggestion_id:
                if row.response is not None:
                    raise SuggestionConflict(
                        suggestion_id, f"La sugerencia {suggestion_id} ya tiene respuesta"
                    )
                updated = replace(
                    row,
                    response=response,
                    responded_by=user,
                    responded_at=datetime.now(UTC),
                    applied_seq=applied_seq,
                )
                rows[i] = updated
                return updated
        raise SuggestionNotFound(suggestion_id)

    def list_suggestions(
        self, session_id: str, *, at_seq: int | None = None
    ) -> tuple[PersistedSuggestion, ...]:
        return tuple(
            s for s in self.suggestions.get(session_id, []) if at_seq is None or s.at_seq == at_seq
        )

    def update_status(self, session_id: str, status: str) -> SessionData:
        record = self.sessions.get(session_id)
        if record is None:
            raise SessionNotFound(session_id)
        updated = replace(record, status=status)
        self.sessions[session_id] = updated
        return updated

    def update_metadata(self, session_id: str, metadata: ScoreMetadata) -> SessionData:
        record = self.sessions.get(session_id)
        if record is None:
            raise SessionNotFound(session_id)
        updated = replace(record, metadata=metadata)
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
        condition: str | None = None,
        test_score_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[SessionSummary, ...]:
        filtered = list(self.sessions.values())
        if owner_id is not None:
            filtered = [s for s in filtered if s.owner_id == owner_id]
        if status is not None:
            filtered = [s for s in filtered if s.status == status]
        if condition is not None:
            filtered = [s for s in filtered if s.condition == condition]
        if test_score_id is not None:
            filtered = [s for s in filtered if s.test_score_id == test_score_id]

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
                    condition=s.condition,
                    test_score_id=s.test_score_id,
                    metadata=s.metadata,
                    source_filename=s.source_filename,
                )
            )
        return tuple(summaries)
