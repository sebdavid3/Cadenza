"""Capa de aplicación hexagonal de Cadenza (ADR-0009)."""

from .exceptions import (
    ApplicationError,
    ArtifactNotFound,
    DuplicateUsername,
    InvalidEdit,
    SequenceConflict,
    SessionNotFound,
    UserNotFound,
)
from .ports import (
    ArtifactStore,
    EditEventRepository,
    InMemoryArtifactStore,
    InMemoryUserRepository,
    PersistedFinding,
    SessionData,
    SessionRepository,
    UserRepository,
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
from .user import Role, User

__all__ = [
    "ApplicationError",
    "ArtifactNotFound",
    "ArtifactStore",
    "DuplicateUsername",
    "EditEventRepository",
    "InMemoryArtifactStore",
    "InMemoryUserRepository",
    "InvalidEdit",
    "PersistedFinding",
    "Role",
    "SequenceConflict",
    "SessionData",
    "SessionDetail",
    "SessionNotFound",
    "SessionRepository",
    "TranscribeResult",
    "User",
    "UserNotFound",
    "UserRepository",
    "append_edit",
    "compute_sha256",
    "get_session",
    "list_findings",
    "transcribe_score",
]
