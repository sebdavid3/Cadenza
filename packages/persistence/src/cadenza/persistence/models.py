"""Modelos SQLAlchemy de Cadenza (persistencia con JSONB).

El tipo JSON se resuelve como ``JSONB`` en PostgreSQL y como ``JSON`` en SQLite,
de modo que los tests corren en memoria sin servidor y producción usa JSONB
indexable (ADR-0004).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

JsonDocument = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    """Base declarativa de todos los modelos de Cadenza."""


class Session(Base):
    """Un documento procesado por el sistema."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(255), nullable=False)
    omr_engine: Mapped[str] = mapped_column(String(64), nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    findings: Mapped[list[FindingRecord]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    edits: Mapped[list[EditEventRecord]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class FindingRecord(Base):
    """Hallazgo de validación anclado a un evento del documento."""

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    anchor: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[Session] = relationship(back_populates="findings")


class EditEventRecord(Base):
    """Corrección humana inmutable (append-only) anclada a un evento (ADR-0007)."""

    __tablename__ = "edit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    op: Mapped[str] = mapped_column(String(32), nullable=False)
    author: Mapped[str] = mapped_column(String(128), nullable=False)
    anchor: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    session: Mapped[Session] = relationship(back_populates="edits")
