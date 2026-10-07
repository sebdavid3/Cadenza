"""Caso de uso: recuperar sesión y proyectar estado actual (ADR-0009, ADR-0012, #45)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from cadenza.domain import (
    EditEvent,
    ScoreIR,
    UnsupportedEditOpError,
    materialize,
)

from ..exceptions import SessionNotFound
from ..ports.edit_event_repository import EditEventRepository
from ..ports.session_repository import PersistedFinding, SessionRepository
from ..user import Role, User


@dataclass(frozen=True)
class SessionDetail:
    """Detalle completo de una sesión con su estado actual materializado."""

    session_id: str
    document_id: str
    omr_engine: str
    document: dict[str, Any]
    findings: tuple[PersistedFinding, ...]
    edits: tuple[EditEvent, ...]
    current_score: dict[str, Any] | None
    image_artifact: str | None = None
    model_version: str | None = None
    status: str = "transcribed"


def _project(document: dict[str, Any], edits: Sequence[EditEvent]) -> dict[str, Any] | None:
    """Materializa el `ScoreIR` actual aplicando el log de ediciones; None si no es proyectable."""

    if not edits:
        return None
    try:
        score = ScoreIR.from_primitive(document["score"])
        return materialize(score, edits).to_primitive()
    except (UnsupportedEditOpError, KeyError, IndexError, ValueError):
        return None


def get_session(
    session_id: str,
    *,
    session_repository: SessionRepository,
    edit_repository: EditEventRepository,
    current_user: User,
) -> SessionDetail:
    """Recupera la sesión, sus hallazgos, log de ediciones y estado proyectado.

    Aplica la regla de acceso (ADR-0012): un transcriptor solo accede a sus propias
    sesiones (las ajenas responden como inexistentes); un investigador puede leer todas.
    """

    session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)

    if current_user.role == Role.TRANSCRIPTOR and session_data.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    findings = session_repository.list_findings(session_id)
    edits = edit_repository.list_events(session_id)
    current_score = _project(session_data.document, edits)

    return SessionDetail(
        session_id=session_data.id,
        document_id=session_data.document_id,
        omr_engine=session_data.omr_engine,
        document=session_data.document,
        findings=findings,
        edits=edits,
        current_score=current_score,
        image_artifact=session_data.image_artifact,
        model_version=session_data.model_version,
        status=session_data.status,
    )
