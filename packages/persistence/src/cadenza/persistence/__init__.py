"""Persistencia de Cadenza (SQLAlchemy + JSONB)."""

from __future__ import annotations

from .artifact_store import FilesystemArtifactStore
from .database import (
    SessionFactory,
    create_engine_for_url,
    create_memory_engine,
    create_schema,
    create_session_factory,
    session_scope,
)
from .models import (
    ArtifactRecord,
    Base,
    EditEventRecord,
    FindingRecord,
    ImmutableEditEventError,
    Session,
)
from .repository import EditEventRepository, SqlAlchemyEditEventRepository
from .session_repository import SqlAlchemySessionRepository

__all__ = [
    "ArtifactRecord",
    "Base",
    "EditEventRecord",
    "EditEventRepository",
    "FilesystemArtifactStore",
    "FindingRecord",
    "ImmutableEditEventError",
    "Session",
    "SessionFactory",
    "SqlAlchemyEditEventRepository",
    "SqlAlchemySessionRepository",
    "create_engine_for_url",
    "create_memory_engine",
    "create_schema",
    "create_session_factory",
    "session_scope",
]
