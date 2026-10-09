"""Caso de uso: descartar un hallazgo como falso positivo (#36, ADR-0012, ADR-0014)."""

from __future__ import annotations

from ..exceptions import Forbidden, SessionClosed, SessionNotFound
from ..ports.session_repository import PersistedFinding, SessionRepository
from ..session_status import SessionStatus
from ..user import Role, User


def dismiss_finding(
    session_id: str,
    finding_id: int,
    *,
    session_repository: SessionRepository,
    current_user: User,
    reason: str | None = None,
) -> PersistedFinding:
    """Descarta un hallazgo de validación marcándolo como falso positivo.

    - Control de autorización (ADR-0012):
      * Transcriptor ajeno responde 404 (SessionNotFound).
      * Investigador ajeno responde 403 (Forbidden).
      * Dueño responde 200.
    - Verificación del ciclo de vida (ADR-0014):
      * Sesión finalizada responde 409 (SessionClosed).
    """
    session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)

    if current_user.role == Role.TRANSCRIPTOR and session_data.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    if current_user.role == Role.INVESTIGADOR and session_data.owner_id != current_user.id:
        raise Forbidden("Un investigador solo puede descartar hallazgos en sus propias sesiones")

    if session_data.status == SessionStatus.FINALIZED:
        raise SessionClosed(session_id)

    return session_repository.dismiss_finding(
        session_id,
        finding_id,
        user=current_user.username,
        reason=reason,
    )
