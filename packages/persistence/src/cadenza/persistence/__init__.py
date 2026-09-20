"""Persistencia de Cadenza (SQLAlchemy + JSONB)."""

from __future__ import annotations

from .database import (
    SessionFactory,
    create_engine_for_url,
    create_memory_engine,
    create_schema,
    create_session_factory,
    session_scope,
)
from .models import Base, EditEventRecord, FindingRecord, ImmutableEditEventError, Session
from .repository import EditEventRepository, SqlAlchemyEditEventRepository

__all__ = [
    "Base",
    "EditEventRecord",
    "EditEventRepository",
    "FindingRecord",
    "ImmutableEditEventError",
    "Session",
    "SessionFactory",
    "SqlAlchemyEditEventRepository",
    "create_engine_for_url",
    "create_memory_engine",
    "create_schema",
    "create_session_factory",
    "session_scope",
]
