"""Adaptador SQLAlchemy para el repositorio de métricas de esfuerzo (ADR-0004, #13, ADR-0050)."""

from __future__ import annotations

from datetime import datetime

from cadenza.application import (
    EffortMetricsData,
    EffortRepository,
    EffortSegment,
    FindingAction,
)
from cadenza.application.ports.effort_repository import empty_accumulated
from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from .models import EffortMetricsRecord


class SqlAlchemyEffortRepository(EffortRepository):
    """Implementación de EffortRepository respaldada por SQLAlchemy."""

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def add(self, metrics: EffortMetricsData) -> EffortMetricsData:
        record = EffortMetricsRecord(
            id=metrics.id,
            session_id=metrics.session_id,
            duration_ms=metrics.duration_ms,
            time_to_first_edit_ms=metrics.time_to_first_edit_ms,
            interventions=metrics.interventions,
            created_at=metrics.created_at,
        )
        self._session.add(record)
        self._session.flush()
        return self._to_dto(record)

    def list_by_session(self, session_id: str) -> tuple[EffortMetricsData, ...]:
        records = self._session.scalars(
            select(EffortMetricsRecord)
            .where(EffortMetricsRecord.session_id == session_id)
            .order_by(EffortMetricsRecord.created_at.asc(), EffortMetricsRecord.id.asc())
        ).all()
        return tuple(self._to_dto(r) for r in records)

    def get_latest(self, session_id: str) -> EffortMetricsData | None:
        record = self._session.scalars(
            select(EffortMetricsRecord)
            .where(EffortMetricsRecord.session_id == session_id)
            .order_by(EffortMetricsRecord.created_at.desc(), EffortMetricsRecord.id.desc())
        ).first()
        if record is None:
            return None
        return self._to_dto(record)

    def _accumulated(
        self, session_id: str, *, for_update: bool = False
    ) -> EffortMetricsRecord | None:
        stmt = select(EffortMetricsRecord).where(
            EffortMetricsRecord.session_id == session_id,
            EffortMetricsRecord.accumulated.is_(True),
        )
        # En PostgreSQL bloquea la fila hasta el final de la transacción; SQLite lo ignora (y
        # escribe de una en una).
        if for_update:
            stmt = stmt.with_for_update()
        return self._session.scalars(stmt).one_or_none()

    def get_accumulated(
        self, session_id: str, *, for_update: bool = False
    ) -> EffortMetricsData | None:
        record = self._accumulated(session_id, for_update=for_update)
        return None if record is None else self._to_dto(record)

    def _create(self, metrics: EffortMetricsData) -> EffortMetricsRecord:
        # Dos creaciones a la vez chocan con el índice único parcial: la segunda falla con un
        # error de integridad y la petición se puede repetir sin haber contado nada (ADR-0050).
        record = EffortMetricsRecord(
            id=metrics.id,
            session_id=metrics.session_id,
            duration_ms=metrics.duration_ms,
            time_to_first_edit_ms=metrics.time_to_first_edit_ms,
            interventions=metrics.interventions,
            created_at=metrics.created_at,
            accumulated=True,
            segments=[],
            interventions_by_class={},
            findings_dismissed=0,
            findings_restored=0,
            suggestions_applied=0,
            suggestions_rejected=0,
            updated_at=metrics.updated_at,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def save_accumulated(self, metrics: EffortMetricsData) -> EffortMetricsData:
        record = self._accumulated(metrics.session_id, for_update=True) or self._create(metrics)
        record.duration_ms = metrics.duration_ms
        record.time_to_first_edit_ms = metrics.time_to_first_edit_ms
        record.interventions = dict(metrics.interventions)
        record.segments = [segment.to_primitive() for segment in metrics.segments]
        record.interventions_by_class = {
            name: dict(counts) for name, counts in metrics.interventions_by_class.items()
        }
        record.suggestions_applied = metrics.suggestions_applied
        record.suggestions_rejected = metrics.suggestions_rejected
        record.updated_at = metrics.updated_at
        self._session.flush()
        return self._to_dto(record)

    def add_finding_action(
        self, session_id: str, action: FindingAction, *, now: datetime
    ) -> EffortMetricsData:
        record = self._accumulated(session_id) or self._create(empty_accumulated(session_id, now))
        column = (
            EffortMetricsRecord.findings_dismissed
            if action == "dismissed"
            else EffortMetricsRecord.findings_restored
        )
        # Una suma en la base, no en Python: no pisa otra que llegue a la vez.
        self._session.execute(
            update(EffortMetricsRecord)
            .where(EffortMetricsRecord.id == record.id)
            .values({column: column + 1, EffortMetricsRecord.updated_at: now})
            .execution_options(synchronize_session=False)
        )
        self._session.refresh(record)
        return self._to_dto(record)

    @staticmethod
    def _to_dto(record: EffortMetricsRecord) -> EffortMetricsData:
        return EffortMetricsData(
            id=record.id,
            session_id=record.session_id,
            duration_ms=record.duration_ms,
            time_to_first_edit_ms=record.time_to_first_edit_ms,
            interventions=dict(record.interventions) if record.interventions else {},
            created_at=record.created_at,
            accumulated=bool(record.accumulated),
            segments=tuple(EffortSegment.from_primitive(s) for s in record.segments or ()),
            interventions_by_class={
                name: {str(k): int(v) for k, v in counts.items()}
                for name, counts in (record.interventions_by_class or {}).items()
            },
            findings_dismissed=record.findings_dismissed or 0,
            findings_restored=record.findings_restored or 0,
            suggestions_applied=record.suggestions_applied or 0,
            suggestions_rejected=record.suggestions_rejected or 0,
            updated_at=record.updated_at,
        )
