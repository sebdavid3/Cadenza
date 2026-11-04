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
from .effort_repository import SqlAlchemyEffortRepository
from .model_registry import SqlAlchemyModelRegistry
from .models import (
    ArtifactRecord,
    Base,
    EditEventRecord,
    EffortMetricsRecord,
    FindingRecord,
    ImmutableEditEventError,
    ModelVersionRecord,
    PreviewRecord,
    Session,
    SuggestionModelVersionRecord,
    SuggestionRecord,
    UserRecord,
)
from .preview_repository import SqlAlchemyPreviewRepository
from .repository import EditEventRepository, SqlAlchemyEditEventRepository
from .session_repository import SqlAlchemySessionRepository
from .suggestion_model_registry import SqlAlchemySuggestionModelRegistry
from .user_repository import SqlAlchemyUserRepository

__all__ = [
    "ArtifactRecord",
    "Base",
    "EditEventRecord",
    "EditEventRepository",
    "EffortMetricsRecord",
    "FilesystemArtifactStore",
    "FindingRecord",
    "ImmutableEditEventError",
    "ModelVersionRecord",
    "PreviewRecord",
    "Session",
    "SessionFactory",
    "SqlAlchemyEditEventRepository",
    "SqlAlchemyEffortRepository",
    "SqlAlchemyModelRegistry",
    "SqlAlchemyPreviewRepository",
    "SqlAlchemySessionRepository",
    "SqlAlchemySuggestionModelRegistry",
    "SqlAlchemyUserRepository",
    "SuggestionModelVersionRecord",
    "SuggestionRecord",
    "UserRecord",
    "create_engine_for_url",
    "create_memory_engine",
    "create_schema",
    "create_session_factory",
    "session_scope",
]
