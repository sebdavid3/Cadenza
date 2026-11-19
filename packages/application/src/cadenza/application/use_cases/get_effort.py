"""Caso de uso: consultar métricas de esfuerzo de una sesión (#13, ADR-0012)."""

from __future__ import annotations

from ..access import require_owner
from ..exceptions import SessionNotFound
from ..ports.effort_repository import EffortMetricsData, EffortRepository
from ..ports.session_repository import SessionRepository
from ..user import User


def get_effort(
    session_repo: SessionRepository,
    effort_repo: EffortRepository,
    *,
    session_id: str,
    current_user: User,
) -> tuple[EffortMetricsData, ...]:
    """Recupera las métricas de esfuerzo de una sesión respetando las reglas de acceso.

    - Control de acceso (ADR-0012, ADR-0070): solo el dueño consulta sus métricas; una
      sesión ajena lanza SessionNotFound (404).
    """
    session = session_repo.get(session_id)
    if session is None:
        raise SessionNotFound(session_id)

    require_owner(session.owner_id, current_user, session_id)

    return effort_repo.list_by_session(session_id)
