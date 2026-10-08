"""Caso de uso: listar hallazgos vigentes de una sesión (ADR-0009, ADR-0012, #45)."""

from __future__ import annotations

from ..exceptions import SessionNotFound
from ..ports.session_repository import PersistedFinding, SessionRepository
from ..user import Role, User


def list_findings(
    session_id: str,
    *,
    session_repository: SessionRepository,
    current_user: User,
    at_seq: int | None = None,
    latest_only: bool = True,
) -> tuple[PersistedFinding, ...]:
    """Devuelve los hallazgos de la sesión, verificando existencia y propiedad."""

    session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)

    if current_user.role == Role.TRANSCRIPTOR and session_data.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    return session_repository.list_findings(
        session_id,
        at_seq=at_seq,
        latest_only=latest_only,
    )
