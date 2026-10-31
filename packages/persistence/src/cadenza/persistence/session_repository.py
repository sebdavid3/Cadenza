"""Adaptador SQLAlchemy para el repositorio de sesiones (ADR-0009)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from cadenza.application import (
    FindingNotFound,
    NewSuggestion,
    PersistedFinding,
    PersistedSuggestion,
    SessionData,
    SessionNotFound,
    SessionRepository,
    SessionSummary,
    SuggestionConflict,
    SuggestionNotFound,
)
from cadenza.domain import Finding
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session as DbSession

from .models import EditEventRecord, FindingRecord, SuggestionRecord
from .models import Session as SessionRecord


def _to_persisted_suggestion(record: SuggestionRecord) -> PersistedSuggestion:
    return PersistedSuggestion(
        id=record.id,
        session_id=record.session_id,
        finding_id=record.finding_id,
        at_seq=record.at_seq,
        rank=record.rank,
        op=record.op,
        anchor=record.anchor,
        before=record.before,
        after=record.after,
        confidence=record.confidence,
        confidence_level=record.confidence_level,
        explanation=record.explanation,
        source=record.source,
        model_version=record.model_version,
        response=record.response,
        responded_by=record.responded_by,
        responded_at=record.responded_at,
        applied_seq=record.applied_seq,
        inherited_from=record.inherited_from,
    )


def _suggestion_record(
    new: NewSuggestion, *, session_id: str, finding_id: int, at_seq: int, rank: int
) -> SuggestionRecord:
    edit = new.edit
    inherited = new.inherited
    return SuggestionRecord(
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


def _to_persisted_finding(
    record: FindingRecord, suggestions: Sequence[PersistedSuggestion] = ()
) -> PersistedFinding:
    return PersistedFinding(
        id=record.id,
        rule_id=record.rule_id,
        severity=record.severity,
        message=record.message,
        suggested_fix=record.suggested_fix,
        anchor=record.anchor,
        at_seq=record.at_seq,
        status=record.status,
        dismissed_at=record.dismissed_at,
        dismissed_by=record.dismissed_by,
        dismissal_reason=record.dismissal_reason,
        suggestions=tuple(suggestions),
    )


class SqlAlchemySessionRepository(SessionRepository):
    """Implementación de SessionRepository respaldada por SQLAlchemy."""

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def _store_suggestions(
        self,
        session_id: str,
        records: Sequence[FindingRecord],
        suggestions: Sequence[Sequence[NewSuggestion]] | None,
    ) -> None:
        if not suggestions:
            return
        rows = [
            _suggestion_record(
                new, session_id=session_id, finding_id=record.id, at_seq=record.at_seq, rank=rank
            )
            for record, news in zip(records, suggestions, strict=True)
            for rank, new in enumerate(news)
        ]
        self._session.add_all(rows)
        self._session.flush()

    def _attach(
        self, session_id: str, records: Sequence[FindingRecord]
    ) -> tuple[PersistedFinding, ...]:
        ids = [record.id for record in records]
        by_finding: dict[int, list[PersistedSuggestion]] = {}
        if ids:
            stmt = (
                select(SuggestionRecord)
                .where(
                    SuggestionRecord.session_id == session_id,
                    SuggestionRecord.finding_id.in_(ids),
                )
                .order_by(SuggestionRecord.finding_id, SuggestionRecord.rank)
            )
            for row in self._session.scalars(stmt).all():
                assert row.finding_id is not None
                by_finding.setdefault(row.finding_id, []).append(_to_persisted_suggestion(row))
        return tuple(
            _to_persisted_finding(record, by_finding.get(record.id, ())) for record in records
        )

    def add(
        self,
        session: SessionData,
        findings: Sequence[Finding],
        suggestions: Sequence[Sequence[NewSuggestion]] | None = None,
    ) -> SessionData:
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
            condition=session.condition,
            test_score_id=session.test_score_id,
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
                status="active",
            )
            for finding in findings
        ]
        self._session.add(record)
        self._session.flush()
        self._store_suggestions(session.id, record.findings, suggestions)
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
            condition=record.condition,
            test_score_id=record.test_score_id,
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
            condition=record.condition,
            test_score_id=record.test_score_id,
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
                condition=record.condition,
                test_score_id=record.test_score_id,
            )
            for record in records
        )

    def replace_findings(
        self,
        session_id: str,
        findings: Sequence[Finding],
        *,
        at_seq: int,
        dismissed_statuses: Sequence[PersistedFinding | None] | None = None,
        suggestions: Sequence[Sequence[NewSuggestion]] | None = None,
    ) -> tuple[PersistedFinding, ...]:
        record = self._session.get(SessionRecord, session_id)
        if record is None:
            raise SessionNotFound(session_id)
        record.validated_at_seq = at_seq

        # Las sugerencias de ese estado: sin respuesta se van con su hallazgo; con respuesta se
        # conservan desvinculadas (ADR-0036 §4).
        self._session.execute(
            delete(SuggestionRecord).where(
                SuggestionRecord.session_id == session_id,
                SuggestionRecord.at_seq == at_seq,
                SuggestionRecord.response.is_(None),
            )
        )
        self._session.execute(
            update(SuggestionRecord)
            .where(
                SuggestionRecord.session_id == session_id,
                SuggestionRecord.at_seq == at_seq,
            )
            .values(finding_id=None)
        )

        # Re-evaluar el mismo estado sustituye sus hallazgos (idempotencia por
        # `(session_id, at_seq)`); los de otros estados se conservan (ADR-0013).
        self._session.execute(
            delete(FindingRecord).where(
                FindingRecord.session_id == session_id,
                FindingRecord.at_seq == at_seq,
            )
        )

        new_records: list[FindingRecord] = []
        for i, finding in enumerate(findings):
            d_state = (
                dismissed_statuses[i]
                if dismissed_statuses is not None and i < len(dismissed_statuses)
                else None
            )
            new_records.append(
                FindingRecord(
                    session_id=session_id,
                    at_seq=at_seq,
                    rule_id=finding.rule_id,
                    severity=finding.severity.value,
                    message=finding.message,
                    suggested_fix=finding.suggested_fix,
                    anchor=finding.anchor.to_primitive(),
                    status=d_state.status if d_state is not None else "active",
                    dismissed_at=d_state.dismissed_at if d_state is not None else None,
                    dismissed_by=d_state.dismissed_by if d_state is not None else None,
                    dismissal_reason=d_state.dismissal_reason if d_state is not None else None,
                )
            )
        self._session.add_all(new_records)
        self._session.flush()
        self._store_suggestions(session_id, new_records, suggestions)

        return self._attach(session_id, new_records)

    def dismiss_finding(
        self,
        session_id: str,
        finding_id: int,
        *,
        user: str,
        reason: str | None = None,
    ) -> PersistedFinding:
        record = self._session.get(SessionRecord, session_id)
        if record is None:
            raise SessionNotFound(session_id)

        stmt = select(FindingRecord).where(
            FindingRecord.session_id == session_id,
            FindingRecord.id == finding_id,
        )
        finding_row = self._session.scalars(stmt).one_or_none()
        if finding_row is None:
            raise FindingNotFound(finding_id)

        finding_row.status = "dismissed"
        finding_row.dismissed_at = datetime.now(UTC)
        finding_row.dismissed_by = user
        finding_row.dismissal_reason = reason
        self._session.flush()

        return self._attach(session_id, [finding_row])[0]

    def restore_finding(
        self,
        session_id: str,
        finding_id: int,
    ) -> PersistedFinding:
        record = self._session.get(SessionRecord, session_id)
        if record is None:
            raise SessionNotFound(session_id)

        stmt = select(FindingRecord).where(
            FindingRecord.session_id == session_id,
            FindingRecord.id == finding_id,
        )
        finding_row = self._session.scalars(stmt).one_or_none()
        if finding_row is None:
            raise FindingNotFound(finding_id)

        finding_row.status = "active"
        finding_row.dismissed_at = None
        finding_row.dismissed_by = None
        finding_row.dismissal_reason = None
        self._session.flush()

        return self._attach(session_id, [finding_row])[0]

    def list_findings(
        self,
        session_id: str,
        *,
        at_seq: int | None = None,
        latest_only: bool = True,
        include_dismissed: bool = False,
    ) -> tuple[PersistedFinding, ...]:
        stmt = select(FindingRecord).where(FindingRecord.session_id == session_id)
        if not include_dismissed:
            stmt = stmt.where(FindingRecord.status == "active")
        if at_seq is not None:
            stmt = stmt.where(FindingRecord.at_seq == at_seq)
        elif latest_only:
            record = self._session.get(SessionRecord, session_id)
            if record is None:
                return ()
            stmt = stmt.where(FindingRecord.at_seq == record.validated_at_seq)

        rows = self._session.scalars(stmt.order_by(FindingRecord.id)).all()
        return self._attach(session_id, rows)

    def list_dismissed_findings(
        self,
        session_id: str,
    ) -> tuple[PersistedFinding, ...]:
        record = self._session.get(SessionRecord, session_id)
        if record is None:
            return ()
        stmt = (
            select(FindingRecord)
            .where(
                FindingRecord.session_id == session_id,
                FindingRecord.status == "dismissed",
            )
            .order_by(FindingRecord.id)
        )
        rows = self._session.scalars(stmt).all()
        return self._attach(session_id, rows)

    def get_suggestion(self, session_id: str, suggestion_id: int) -> PersistedSuggestion | None:
        row = self._session.get(SuggestionRecord, suggestion_id)
        if row is None or row.session_id != session_id:
            return None
        return _to_persisted_suggestion(row)

    def respond_suggestion(
        self,
        session_id: str,
        suggestion_id: int,
        *,
        response: str,
        user: str,
        applied_seq: int | None = None,
    ) -> PersistedSuggestion:
        row = self._session.get(SuggestionRecord, suggestion_id)
        if row is None or row.session_id != session_id:
            raise SuggestionNotFound(suggestion_id)
        # Solo si no tenía respuesta, en la misma sentencia: dos peticiones a la vez no pueden
        # cambiar una respuesta guardada (ADR-0036 §5).
        result = self._session.execute(
            update(SuggestionRecord)
            .where(
                SuggestionRecord.id == suggestion_id,
                SuggestionRecord.session_id == session_id,
                SuggestionRecord.response.is_(None),
            )
            .values(
                response=response,
                responded_by=user,
                responded_at=datetime.now(UTC),
                applied_seq=applied_seq,
            )
            .execution_options(synchronize_session=False)
        )
        if getattr(result, "rowcount", 0) != 1:
            raise SuggestionConflict(
                suggestion_id, f"La sugerencia {suggestion_id} ya tiene respuesta"
            )
        self._session.refresh(row)
        return _to_persisted_suggestion(row)

    def list_suggestions(
        self, session_id: str, *, at_seq: int | None = None
    ) -> tuple[PersistedSuggestion, ...]:
        stmt = select(SuggestionRecord).where(SuggestionRecord.session_id == session_id)
        if at_seq is not None:
            stmt = stmt.where(SuggestionRecord.at_seq == at_seq)
        rows = self._session.scalars(stmt.order_by(SuggestionRecord.id)).all()
        return tuple(_to_persisted_suggestion(row) for row in rows)

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
        findings_count_sq = (
            select(func.count(FindingRecord.id))
            .where(
                FindingRecord.session_id == SessionRecord.id,
                FindingRecord.at_seq == SessionRecord.validated_at_seq,
                FindingRecord.status == "active",
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
            SessionRecord.condition,
            SessionRecord.test_score_id,
            findings_count_sq.label("findings_count"),
            edits_count_sq.label("edits_count"),
        )
        if owner_id is not None:
            stmt = stmt.where(SessionRecord.owner_id == owner_id)
        if status is not None:
            stmt = stmt.where(SessionRecord.status == status)
        if condition is not None:
            stmt = stmt.where(SessionRecord.condition == condition)
        if test_score_id is not None:
            stmt = stmt.where(SessionRecord.test_score_id == test_score_id)

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
                condition=row.condition,
                test_score_id=row.test_score_id,
            )
            for row in rows
        )
