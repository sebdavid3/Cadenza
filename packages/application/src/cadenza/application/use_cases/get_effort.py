"""Caso de uso: consultar métricas de esfuerzo de una sesión (#13, ADR-0012)."""

from __future__ import annotations

from ..exceptions import SessionNotFound
from ..ports.effort_repository import EffortMetricsData, EffortRepository
from ..ports.session_repository import SessionRepository
from ..user import Role, User


def get_effort(
    session_repo: SessionRepository,
    effort_repo: EffortRepository,
    *,
    session_id: str,
    current_user: User,
) -> tuple[EffortMetricsData, ...]:
    """Recupera las métricas de esfuerzo de una sesión respetando las reglas de acceso.

    - Control de acceso ADR-0012:
      * Transcriptor ajeno recibe SessionNotFound (404).
      * Investigador puede consultar las métricas de cualquier sesión (200).
      * Dueño puede consultar sus propias métricas (200).
    """
    session = session_repo.get(session_id)
    if session is None:
        raise SessionNotFound(session_id)

    if current_user.role == Role.TRANSCRIPTOR and session.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    return effort_repo.list_by_session(session_id)
