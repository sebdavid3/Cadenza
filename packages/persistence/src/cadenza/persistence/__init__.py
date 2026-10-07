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
    UserRecord,
)
from .repository import EditEventRepository, SqlAlchemyEditEventRepository
from .session_repository import SqlAlchemySessionRepository
from .user_repository import SqlAlchemyUserRepository

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
    "SqlAlchemyUserRepository",
    "UserRecord",
    "create_engine_for_url",
    "create_memory_engine",
    "create_schema",
    "create_session_factory",
    "session_scope",
]
