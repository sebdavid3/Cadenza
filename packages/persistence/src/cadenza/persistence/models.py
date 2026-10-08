"""Modelos SQLAlchemy de Cadenza (persistencia con JSONB).

El tipo JSON se resuelve como ``JSONB`` en PostgreSQL y como ``JSON`` en SQLite,
de modo que los tests corren en memoria sin servidor y producción usa JSONB
indexable (ADR-0004).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

JsonDocument = JSON().with_variant(JSONB(), "postgresql")


class ImmutableEditEventError(RuntimeError):
    """Se intentó mutar o borrar un `EditEvent` ya persistido (ADR-0007)."""


class Base(DeclarativeBase):
    """Base declarativa de todos los modelos de Cadenza."""


class UserRecord(Base):
    """Cuenta de usuario y rol para control de acceso y autoría (ADR-0012)."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sessions: Mapped[list[Session]] = relationship(back_populates="owner")


class Session(Base):
    """Un documento procesado por el sistema."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_sessions_owner_id"),
        server_default="default-user",
        nullable=False,
    )
    document_id: Mapped[str] = mapped_column(String(255), nullable=False)
    omr_engine: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), server_default="transcribed", default="transcribed", nullable=False
    )
    validated_at_seq: Mapped[int] = mapped_column(
        Integer, server_default="0", default=0, nullable=False
    )
    image_artifact: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(
            "artifacts.sha256",
            ondelete="SET NULL",
            name="fk_sessions_image_artifact",
        ),
        nullable=True,
    )
    document: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    owner: Mapped[UserRecord] = relationship("UserRecord", back_populates="sessions")
    artifact: Mapped[ArtifactRecord | None] = relationship(
        "ArtifactRecord", foreign_keys=[image_artifact]
    )
    findings: Mapped[list[FindingRecord]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    # Sin `delete-orphan`: el log de ediciones es inmutable y no se borra con la
    # sesión (ADR-0007). La FK con `ondelete="RESTRICT"` lo refuerza en la base.
    edits: Mapped[list[EditEventRecord]] = relationship(back_populates="session")
    effort_metrics: Mapped[list[EffortMetricsRecord]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class FindingRecord(Base):
    """Hallazgo de validación anclado a un evento del documento."""

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    at_seq: Mapped[int] = mapped_column(Integer, server_default="0", default=0, nullable=False)
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    anchor: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), server_default="active", default="active", nullable=False
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dismissal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[Session] = relationship(back_populates="findings")


class EditEventRecord(Base):
    """Corrección humana inmutable (append-only) anclada a un evento (ADR-0007)."""

    __tablename__ = "edit_events"
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_edit_events_session_seq"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    op: Mapped[str] = mapped_column(String(32), nullable=False)
    author: Mapped[str] = mapped_column(String(128), nullable=False)
    anchor: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument, nullable=True)
    reverts_edit_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("edit_events.id", ondelete="RESTRICT", name="fk_edit_events_reverts_edit_id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    session: Mapped[Session] = relationship(back_populates="edits")


@event.listens_for(EditEventRecord, "before_update")
def _forbid_edit_event_update(*_args: object) -> None:
    raise ImmutableEditEventError(
        "EditEventRecord es inmutable: no se permite UPDATE sobre eventos pasados (ADR-0007)."
    )


@event.listens_for(EditEventRecord, "before_delete")
def _forbid_edit_event_delete(*_args: object) -> None:
    raise ImmutableEditEventError(
        "EditEventRecord es inmutable: no se permite DELETE de eventos pasados (ADR-0007)."
    )


class ArtifactRecord(Base):
    """Índice de artefactos direccionados por contenido en el ArtifactStore (ADR-0004)."""

    __tablename__ = "artifacts"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EffortMetricsRecord(Base):
    """Métricas de esfuerzo humano en la corrección de una sesión (ADR-0004, #13)."""

    __tablename__ = "effort_metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    time_to_first_edit_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interventions: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[Session] = relationship(back_populates="effort_metrics")


class ModelVersionRecord(Base):
    """Versión registrada en el Model Registry (ADR-0008, ARCHITECTURE.md §7.2, #21)."""

    __tablename__ = "model_versions"

    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    artifact_hash: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "artifacts.sha256",
            ondelete="RESTRICT",
            name="fk_model_versions_artifact_hash",
        ),
        nullable=False,
    )
    dataset_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ser: Mapped[float] = mapped_column(Float, nullable=False)
    omr_ned: Mapped[float] = mapped_column(Float, nullable=False)
    promoted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    artifact: Mapped[ArtifactRecord] = relationship("ArtifactRecord", foreign_keys=[artifact_hash])
