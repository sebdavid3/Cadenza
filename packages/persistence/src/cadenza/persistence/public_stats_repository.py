"""Adaptador SQLAlchemy de las cifras públicas de los errores de HOMR (#423, ADR-0073)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from cadenza.application import PublicStatsGroup, PublicStatsRepository
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from .models import PublicStatsRecord


def _utc(moment: datetime) -> datetime:
    """SQLite devuelve las fechas sin zona: se leen como UTC, que es como se guardan."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _to_group(record: PublicStatsRecord) -> PublicStatsGroup:
    return PublicStatsGroup(
        id=record.id,
        source=record.source,
        computed_at=_utc(record.computed_at),
        format_version=record.format_version,
        min_sessions=record.min_sessions,
        sessions=record.sessions,
        stats=None if record.stats is None else dict(record.stats),
        source_sha256=record.source_sha256,
    )


class SqlAlchemyPublicStatsRepository(PublicStatsRepository):
    """Los grupos en `public_stats`, una fila por grupo."""

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def list(self) -> tuple[PublicStatsGroup, ...]:
        stmt = select(PublicStatsRecord).order_by(PublicStatsRecord.source, PublicStatsRecord.id)
        return tuple(_to_group(r) for r in self._session.scalars(stmt).all())

    def replace(self, source: str, groups: Sequence[PublicStatsGroup]) -> None:
        if any(group.source != source for group in groups):
            raise ValueError(f"todos los grupos han de ser de {source}")
        self._session.execute(delete(PublicStatsRecord).where(PublicStatsRecord.source == source))
        self._session.flush()
        self._session.add_all(
            PublicStatsRecord(
                id=group.id,
                source=group.source,
                computed_at=group.computed_at.astimezone(UTC),
                format_version=group.format_version,
                min_sessions=group.min_sessions,
                sessions=group.sessions,
                source_sha256=group.source_sha256,
                stats=None if group.stats is None else dict(group.stats),
            )
            for group in groups
        )
        self._session.flush()
