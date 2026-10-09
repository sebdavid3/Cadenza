"""Adaptador SQLAlchemy para Model Registry persistente (ADR-0008, ARCHITECTURE.md §6.2, #21)."""

from __future__ import annotations

from datetime import UTC, datetime

from cadenza.application import (
    EvaluationMetrics,
    ModelRegistry,
    ModelVersionData,
    PromotionRejected,
    PromotionThreshold,
)
from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from .models import ModelVersionRecord


def _record_to_data(record: ModelVersionRecord) -> ModelVersionData:
    return ModelVersionData(
        version=record.version,
        artifact_hash=record.artifact_hash,
        dataset_hash=record.dataset_hash,
        config_hash=record.config_hash,
        metrics=EvaluationMetrics(ser=record.ser, omr_ned=record.omr_ned),
        promoted=record.promoted,
        created_at=record.created_at,
    )


class SqlAlchemyModelRegistry(ModelRegistry):
    """Adaptador de persistencia relacional para el Model Registry."""

    def __init__(
        self,
        session: DbSession,
        threshold: PromotionThreshold | None = None,
    ) -> None:
        self._session = session
        self._threshold = threshold or PromotionThreshold(max_ser=1.0, max_omr_ned=1.0)

    def register(self, version: ModelVersionData) -> ModelVersionData:
        existing = self._session.get(ModelVersionRecord, version.version)
        if existing is not None:
            raise ValueError(f"version already registered: {version.version}")

        created_at = version.created_at or datetime.now(UTC)
        record = ModelVersionRecord(
            version=version.version,
            artifact_hash=version.artifact_hash,
            dataset_hash=version.dataset_hash,
            config_hash=version.config_hash,
            ser=version.metrics.ser,
            omr_ned=version.metrics.omr_ned,
            promoted=version.promoted,
            created_at=created_at,
        )
        self._session.add(record)
        self._session.flush()
        return _record_to_data(record)

    def promote(self, version_id: str) -> ModelVersionData:
        target = self._session.get(ModelVersionRecord, version_id)
        if target is None:
            raise KeyError(version_id)

        metrics = EvaluationMetrics(ser=target.ser, omr_ned=target.omr_ned)
        if not self._threshold.accepts(metrics):
            raise PromotionRejected(
                f"{version_id} no supera el umbral (ser={target.ser}, omr_ned={target.omr_ned})"
            )

        # Desmarca cualquier versión previamente promovida para garantizar exclusividad
        self._session.execute(update(ModelVersionRecord).values(promoted=False))
        target.promoted = True
        self._session.flush()
        return _record_to_data(target)

    def active(self) -> ModelVersionData | None:
        stmt = (
            select(ModelVersionRecord)
            .where(ModelVersionRecord.promoted == True)  # noqa: E712
            .order_by(ModelVersionRecord.created_at.desc())
        )
        record = self._session.scalars(stmt).first()
        if record is None:
            return None
        return _record_to_data(record)

    def versions(self) -> tuple[ModelVersionData, ...]:
        stmt = select(ModelVersionRecord).order_by(ModelVersionRecord.created_at.asc())
        records = self._session.scalars(stmt).all()
        return tuple(_record_to_data(r) for r in records)
