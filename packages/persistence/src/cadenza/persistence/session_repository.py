"""Adaptador SQLAlchemy para el repositorio de sesiones (ADR-0009)."""

from __future__ import annotations

from collections.abc import Sequence

from cadenza.application import PersistedFinding, SessionData, SessionRepository
from cadenza.domain import Finding
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .models import FindingRecord
from .models import Session as SessionRecord


class SqlAlchemySessionRepository(SessionRepository):
    """Implementación de SessionRepository respaldada por SQLAlchemy."""

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def add(self, session: SessionData, findings: Sequence[Finding]) -> SessionData:
        record = SessionRecord(
            id=session.id,
            document_id=session.document_id,
            omr_engine=session.omr_engine,
            document=session.document,
        )
        record.findings = [
            FindingRecord(
                rule_id=finding.rule_id,
                severity=finding.severity.value,
                message=finding.message,
                suggested_fix=finding.suggested_fix,
                anchor=finding.anchor.to_primitive(),
            )
            for finding in findings
        ]
        self._session.add(record)
        self._session.flush()
        return session

    def get(self, session_id: str) -> SessionData | None:
        record = self._session.get(SessionRecord, session_id)
        if record is None:
            return None
        return SessionData(
            id=record.id,
            document_id=record.document_id,
            omr_engine=record.omr_engine,
            document=record.document,
            created_at=record.created_at,
        )

    def list_findings(self, session_id: str) -> tuple[PersistedFinding, ...]:
        rows = self._session.scalars(
            select(FindingRecord)
            .where(FindingRecord.session_id == session_id)
            .order_by(FindingRecord.id)
        ).all()
        return tuple(
            PersistedFinding(
                id=row.id,
                rule_id=row.rule_id,
                severity=row.severity,
                message=row.message,
                suggested_fix=row.suggested_fix,
                anchor=row.anchor,
            )
            for row in rows
        )
