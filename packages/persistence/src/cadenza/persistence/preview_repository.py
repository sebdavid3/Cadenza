"""Repositorio SQLAlchemy de las transcripciones sin cuenta (#278, ADR-0054)."""

from __future__ import annotations

from datetime import UTC, datetime

from cadenza.application import PreviewData, PreviewRepository
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession

from .models import PreviewRecord
from .session_repository import _metadata, _metadata_columns


def _aware(moment: datetime) -> datetime:
    """SQLite devuelve las fechas sin zona: se leen como UTC, que es como se guardan."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _to_data(record: PreviewRecord) -> PreviewData:
    return PreviewData(
        id=record.id,
        token_hash=record.token_hash,
        document=record.document,
        image=record.image,
        image_media_type=record.image_media_type,
        created_at=_aware(record.created_at),
        expires_at=_aware(record.expires_at),
        metadata=_metadata(record.title, record.composer, record.part_instruments),
        source_filename=record.source_filename,
    )


class SqlAlchemyPreviewRepository(PreviewRepository):
    """Las transcripciones sin cuenta en la tabla `previews`, imagen incluida."""

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def add(self, preview: PreviewData) -> None:
        self._session.add(
            PreviewRecord(
                id=preview.id,
                token_hash=preview.token_hash,
                document=preview.document,
                image=preview.image,
                image_media_type=preview.image_media_type,
                source_filename=preview.source_filename,
                created_at=preview.created_at.astimezone(UTC),
                expires_at=preview.expires_at.astimezone(UTC),
                **_metadata_columns(preview.metadata),
            )
        )
        self._session.flush()

    def get(self, preview_id: str) -> PreviewData | None:
        record = self._session.get(PreviewRecord, preview_id)
        return None if record is None else _to_data(record)

    def delete(self, preview_id: str) -> bool:
        # Un DELETE condicionado y no `session.delete`: si dos peticiones la reclaman a la vez,
        # la base deja borrar a una sola y la otra ve 0 filas.
        result = self._session.execute(delete(PreviewRecord).where(PreviewRecord.id == preview_id))
        self._session.expire_all()
        return bool(getattr(result, "rowcount", 0))

    def count_active(self, now: datetime) -> int:
        count = self._session.scalar(
            select(func.count())
            .select_from(PreviewRecord)
            .where(PreviewRecord.expires_at > now.astimezone(UTC))
        )
        return int(count or 0)

    def purge_expired(self, now: datetime) -> int:
        result = self._session.execute(
            delete(PreviewRecord).where(PreviewRecord.expires_at <= now.astimezone(UTC))
        )
        return int(getattr(result, "rowcount", 0) or 0)

    def purge_all(self) -> int:
        result = self._session.execute(delete(PreviewRecord))
        return int(getattr(result, "rowcount", 0) or 0)

    def next_expiry(self, now: datetime) -> datetime | None:
        moment = self._session.scalar(
            select(func.min(PreviewRecord.expires_at)).where(
                PreviewRecord.expires_at > now.astimezone(UTC)
            )
        )
        return None if moment is None else _aware(moment)
