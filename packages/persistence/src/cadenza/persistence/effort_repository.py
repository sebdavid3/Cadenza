"""Adaptador SQLAlchemy para el repositorio de métricas de esfuerzo (ADR-0004, #13)."""

from __future__ import annotations

from cadenza.application import EffortMetricsData, EffortRepository
from sqlalchemy import select
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

    @staticmethod
    def _to_dto(record: EffortMetricsRecord) -> EffortMetricsData:
        return EffortMetricsData(
            id=record.id,
            session_id=record.session_id,
            duration_ms=record.duration_ms,
            time_to_first_edit_ms=record.time_to_first_edit_ms,
            interventions=dict(record.interventions) if record.interventions else {},
            created_at=record.created_at,
        )
