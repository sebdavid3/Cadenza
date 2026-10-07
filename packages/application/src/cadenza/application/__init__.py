"""Capa de aplicación hexagonal de Cadenza (ADR-0009)."""

from .exceptions import (
    ApplicationError,
    InvalidEdit,
    SequenceConflict,
    SessionNotFound,
)
from .ports import (
    EditEventRepository,
    PersistedFinding,
    SessionData,
    SessionRepository,
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
    "EditEventRepository",
    "InvalidEdit",
    "PersistedFinding",
    "SequenceConflict",
    "SessionData",
    "SessionDetail",
    "SessionNotFound",
    "SessionRepository",
    "TranscribeResult",
    "append_edit",
    "get_session",
    "list_findings",
    "transcribe_score",
]
