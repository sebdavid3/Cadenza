"""Caso de uso: descartar un hallazgo como falso positivo (#36, ADR-0012, ADR-0014)."""

from __future__ import annotations

from datetime import UTC, datetime

from ..exceptions import Forbidden, SessionClosed, SessionNotFound
from ..ports.effort_repository import EffortRepository
from ..ports.session_repository import PersistedFinding, SessionRepository
from ..session_status import SessionStatus
from ..user import Role, User


def dismiss_finding(
    session_id: str,
    finding_id: int,
    *,
    session_repository: SessionRepository,
    current_user: User,
    effort_repository: EffortRepository | None = None,
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

    # Con `effort_repository`, la orden cuenta en el registro de esfuerzo si cambia el estado del
    # posible error (#188, ADR-0050 §4): repetirla sobre uno que ya lo estaba no es otra acción.
    changes = effort_repository is not None and any(
        finding.id == finding_id and finding.status == "active"
        for finding in session_repository.list_findings(
            session_id, latest_only=False, include_dismissed=True
        )
    )

    dismissed = session_repository.dismiss_finding(
        session_id,
        finding_id,
        user=current_user.username,
        reason=reason,
    )
    if changes and effort_repository is not None:
        effort_repository.add_finding_action(session_id, "dismissed", now=datetime.now(UTC))
    return dismissed
