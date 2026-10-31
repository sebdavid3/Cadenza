"""Adaptador SQLAlchemy del registro de la capa de sugerencias (ADR-0036 §8)."""

from __future__ import annotations

from datetime import UTC, datetime

from cadenza.application import SuggestionModelRegistry, SuggestionModelVersionData
from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from .models import SuggestionModelVersionRecord


def _to_data(record: SuggestionModelVersionRecord) -> SuggestionModelVersionData:
    return SuggestionModelVersionData(
        version=record.version,
        artifact_hash=record.artifact_hash,
        dataset_hash=record.dataset_hash,
        config_hash=record.config_hash,
        seed=record.seed,
        model_type=record.model_type,
        feature_version=record.feature_version,
        metrics=dict(record.metrics),
        promoted=record.promoted,
        created_at=record.created_at,
    )


class SqlAlchemySuggestionModelRegistry(SuggestionModelRegistry):
    """Versiones de la capa en `suggestion_model_versions`, con una sola promovida a la vez."""

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def register(self, version: SuggestionModelVersionData) -> SuggestionModelVersionData:
        if self._session.get(SuggestionModelVersionRecord, version.version) is not None:
            raise ValueError(f"version already registered: {version.version}")
        record = SuggestionModelVersionRecord(
            version=version.version,
            artifact_hash=version.artifact_hash,
            dataset_hash=version.dataset_hash,
            config_hash=version.config_hash,
            seed=version.seed,
            model_type=version.model_type,
            feature_version=version.feature_version,
            metrics=dict(version.metrics),
            promoted=version.promoted,
            created_at=version.created_at or datetime.now(UTC),
        )
        self._session.add(record)
        self._session.flush()
        return _to_data(record)

    def promote(self, version_id: str) -> SuggestionModelVersionData:
        target = self._session.get(SuggestionModelVersionRecord, version_id)
        if target is None:
            raise KeyError(version_id)
        self._session.execute(update(SuggestionModelVersionRecord).values(promoted=False))
        target.promoted = True
        self._session.flush()
        return _to_data(target)

    def active(self) -> SuggestionModelVersionData | None:
        stmt = (
            select(SuggestionModelVersionRecord)
            .where(SuggestionModelVersionRecord.promoted.is_(True))
            .order_by(SuggestionModelVersionRecord.created_at.desc())
        )
        record = self._session.scalars(stmt).first()
        return None if record is None else _to_data(record)

    def versions(self) -> tuple[SuggestionModelVersionData, ...]:
        stmt = select(SuggestionModelVersionRecord).order_by(
            SuggestionModelVersionRecord.created_at.asc(), SuggestionModelVersionRecord.version
        )
        return tuple(_to_data(r) for r in self._session.scalars(stmt).all())
