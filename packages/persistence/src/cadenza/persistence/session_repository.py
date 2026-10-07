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
            owner_id=session.owner_id,
            document_id=session.document_id,
            omr_engine=session.omr_engine,
            model_version=session.model_version,
            status=session.status,
            image_artifact=session.image_artifact,
            document=session.document,
        )
        record.findings = [
            FindingRecord(
                at_seq=finding.at_seq,
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
            owner_id=record.owner_id,
            document_id=record.document_id,
            omr_engine=record.omr_engine,
            document=record.document,
            created_at=record.created_at,
            image_artifact=record.image_artifact,
            model_version=record.model_version,
            status=record.status,
        )

    def list(self, owner_id: str | None = None) -> tuple[SessionData, ...]:
        stmt = select(SessionRecord)
        if owner_id is not None:
            stmt = stmt.where(SessionRecord.owner_id == owner_id)
        stmt = stmt.order_by(SessionRecord.created_at)
        records = self._session.scalars(stmt).all()
        return tuple(
            SessionData(
                id=record.id,
                owner_id=record.owner_id,
                document_id=record.document_id,
                omr_engine=record.omr_engine,
                document=record.document,
                created_at=record.created_at,
                image_artifact=record.image_artifact,
                model_version=record.model_version,
                status=record.status,
            )
            for record in records
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
                at_seq=row.at_seq,
            )
            for row in rows
        )
