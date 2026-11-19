"""Adaptador SQLAlchemy de las cifras públicas de los errores de HOMR (#423, ADR-0073)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from cadenza.application import (
    PublicStatsGroup,
    PublicStatsImage,
    PublicStatsRepository,
    PublicStatsScore,
)
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from .models import PublicStatsRecord, PublicStatsScoreRecord


def _utc(moment: datetime) -> datetime:
    """En UTC: SQLite devuelve las fechas sin zona (se guardan en UTC) y PostgreSQL, en la zona
    de la conexión."""
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


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
    """Los grupos en `public_stats`, una fila por grupo, y el detalle de las partituras de los
    corpus en `public_stats_scores`, una fila por partitura."""

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
        # El detalle de las partituras de los grupos que ya no están. Sin clave foránea: así,
        # reescribir los grupos de un corpus no borra el de los que no se recalcularon.
        self._session.execute(
            delete(PublicStatsScoreRecord).where(
                PublicStatsScoreRecord.group_id.not_in(select(PublicStatsRecord.id))
            )
        )
        self._session.flush()

    def replace_scores(
        self,
        group: PublicStatsGroup,
        scores: Mapping[str, Mapping[str, Any]],
        images: Mapping[str, PublicStatsImage] | None = None,
    ) -> None:
        found = images or {}
        self._session.execute(
            delete(PublicStatsScoreRecord).where(PublicStatsScoreRecord.group_id == group.id)
        )
        self._session.flush()
        self._session.add_all(
            PublicStatsScoreRecord(
                group_id=group.id,
                score_id=score_id,
                computed_at=group.computed_at.astimezone(UTC),
                format_version=group.format_version,
                detail=dict(detail),
                image_type=found[score_id].media_type if score_id in found else None,
                image=found[score_id].content if score_id in found else None,
            )
            for score_id, detail in scores.items()
        )
        self._session.flush()

    def get_score(self, group_id: str, score_id: str) -> PublicStatsScore | None:
        stmt = (
            select(PublicStatsScoreRecord, PublicStatsRecord.source)
            .join(PublicStatsRecord, PublicStatsRecord.id == PublicStatsScoreRecord.group_id)
            .where(
                PublicStatsScoreRecord.group_id == group_id,
                PublicStatsScoreRecord.score_id == score_id,
            )
        )
        found = self._session.execute(stmt).first()
        if found is None:
            return None
        record, source = found
        return PublicStatsScore(
            group_id=record.group_id,
            score_id=record.score_id,
            source=source,
            computed_at=_utc(record.computed_at),
            format_version=record.format_version,
            detail=dict(record.detail),
        )

    def get_image(self, group_id: str, score_id: str) -> PublicStatsImage | None:
        stmt = (
            select(PublicStatsScoreRecord.image_type, PublicStatsScoreRecord.image)
            .join(PublicStatsRecord, PublicStatsRecord.id == PublicStatsScoreRecord.group_id)
            .where(
                PublicStatsScoreRecord.group_id == group_id,
                PublicStatsScoreRecord.score_id == score_id,
            )
        )
        found = self._session.execute(stmt).first()
        if found is None or found.image is None or found.image_type is None:
            return None
        return PublicStatsImage(media_type=found.image_type, content=bytes(found.image))
