"""Adaptador SQLAlchemy para el repositorio de sesiones (ADR-0009)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from cadenza.application import (
    PersistedFinding,
    SessionData,
    SessionNotFound,
    SessionRepository,
    SessionSummary,
)
from cadenza.domain import Finding
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession

from .models import EditEventRecord, FindingRecord
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
            validated_at_seq=session.validated_at_seq,
            image_artifact=session.image_artifact,
            document=session.document,
            created_at=session.created_at or datetime.now(UTC),
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
            validated_at_seq=record.validated_at_seq,
        )

    def update_status(self, session_id: str, status: str) -> SessionData:
        record = self._session.get(SessionRecord, session_id)
        if record is None:
            raise SessionNotFound(session_id)
        record.status = status
        self._session.flush()
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
            validated_at_seq=record.validated_at_seq,
        )

    def list(
        self,
        owner_id: str | None = None,
        status: str | None = None,
    ) -> tuple[SessionData, ...]:
        stmt = select(SessionRecord)
        if owner_id is not None:
            stmt = stmt.where(SessionRecord.owner_id == owner_id)
        if status is not None:
            stmt = stmt.where(SessionRecord.status == status)
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
                validated_at_seq=record.validated_at_seq,
            )
            for record in records
        )

    def replace_findings(
        self,
        session_id: str,
        findings: Sequence[Finding],
        *,
        at_seq: int,
    ) -> tuple[PersistedFinding, ...]:
        record = self._session.get(SessionRecord, session_id)
        if record is None:
            raise SessionNotFound(session_id)
        record.validated_at_seq = at_seq

        # Re-evaluar el mismo estado sustituye sus hallazgos (idempotencia por
        # `(session_id, at_seq)`); los de otros estados se conservan (ADR-0013).
        self._session.execute(
            delete(FindingRecord).where(
                FindingRecord.session_id == session_id,
                FindingRecord.at_seq == at_seq,
            )
        )

        new_records = [
            FindingRecord(
                session_id=session_id,
                at_seq=at_seq,
                rule_id=finding.rule_id,
                severity=finding.severity.value,
                message=finding.message,
                suggested_fix=finding.suggested_fix,
                anchor=finding.anchor.to_primitive(),
            )
            for finding in findings
        ]
        self._session.add_all(new_records)
        self._session.flush()

        return tuple(
            PersistedFinding(
                id=r.id,
                rule_id=r.rule_id,
                severity=r.severity,
                message=r.message,
                suggested_fix=r.suggested_fix,
                anchor=r.anchor,
                at_seq=r.at_seq,
            )
            for r in new_records
        )

    def list_findings(
        self,
        session_id: str,
        *,
        at_seq: int | None = None,
        latest_only: bool = True,
    ) -> tuple[PersistedFinding, ...]:
        stmt = select(FindingRecord).where(FindingRecord.session_id == session_id)
        if at_seq is not None:
            stmt = stmt.where(FindingRecord.at_seq == at_seq)
        elif latest_only:
            record = self._session.get(SessionRecord, session_id)
            if record is None:
                return ()
            stmt = stmt.where(FindingRecord.at_seq == record.validated_at_seq)

        rows = self._session.scalars(stmt.order_by(FindingRecord.id)).all()
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

    def list_summaries(
        self,
        *,
        owner_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[SessionSummary, ...]:
        findings_count_sq = (
            select(func.count(FindingRecord.id))
            .where(
                FindingRecord.session_id == SessionRecord.id,
                FindingRecord.at_seq == SessionRecord.validated_at_seq,
            )
            .correlate(SessionRecord)
            .scalar_subquery()
        )
        edits_count_sq = (
            select(func.count(EditEventRecord.id))
            .where(EditEventRecord.session_id == SessionRecord.id)
            .correlate(SessionRecord)
            .scalar_subquery()
        )

        stmt = select(
            SessionRecord.id,
            SessionRecord.document_id,
            SessionRecord.omr_engine,
            SessionRecord.model_version,
            SessionRecord.status,
            SessionRecord.created_at,
            SessionRecord.owner_id,
            findings_count_sq.label("findings_count"),
            edits_count_sq.label("edits_count"),
        )
        if owner_id is not None:
            stmt = stmt.where(SessionRecord.owner_id == owner_id)
        if status is not None:
            stmt = stmt.where(SessionRecord.status == status)

        stmt = (
            stmt.order_by(SessionRecord.created_at.desc(), SessionRecord.id.desc())
            .offset(offset)
            .limit(limit)
        )

        rows = self._session.execute(stmt).all()
        return tuple(
            SessionSummary(
                session_id=row.id,
                document_id=row.document_id,
                omr_engine=row.omr_engine,
                model_version=row.model_version,
                status=row.status,
                created_at=row.created_at,
                owner_id=row.owner_id,
                findings_count=int(row.findings_count or 0),
                edits_count=int(row.edits_count or 0),
            )
            for row in rows
        )
