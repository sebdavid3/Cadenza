"""Capa de aplicación hexagonal de Cadenza (ADR-0009)."""

from .exceptions import (
    ApplicationError,
    ArtifactNotFound,
    InvalidEdit,
    SequenceConflict,
    SessionNotFound,
)
from .ports import (
    ArtifactStore,
    EditEventRepository,
    InMemoryArtifactStore,
    PersistedFinding,
    SessionData,
    SessionRepository,
    compute_sha256,
)
from .use_cases import (
    SessionDetail,
    TranscribeResult,
    append_edit,
    get_session,
    list_findings,
    transcribe_score,
)

__all__ = [
    "ApplicationError",
    "ArtifactNotFound",
    "ArtifactStore",
    "EditEventRepository",
    "InMemoryArtifactStore",
    "InvalidEdit",
    "PersistedFinding",
    "SequenceConflict",
    "SessionData",
    "SessionDetail",
    "SessionNotFound",
    "SessionRepository",
    "TranscribeResult",
    "append_edit",
    "compute_sha256",
    "get_session",
    "list_findings",
    "transcribe_score",
]
