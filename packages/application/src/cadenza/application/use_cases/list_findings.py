"""Caso de uso: listar hallazgos vigentes de una sesión (ADR-0009)."""

from __future__ import annotations

from ..exceptions import SessionNotFound
from ..ports.session_repository import PersistedFinding, SessionRepository


def list_findings(
    session_id: str,
    *,
    session_repository: SessionRepository,
) -> tuple[PersistedFinding, ...]:
    """Devuelve los hallazgos vigentes asociados a una sesión verificando su existencia."""

    session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)

    return session_repository.list_findings(session_id)
