"""Caso de uso: restaurar un hallazgo previamente descartado (#36, ADR-0012, ADR-0014)."""

from __future__ import annotations

from datetime import UTC, datetime

from ..access import require_owner
from ..exceptions import SessionClosed, SessionNotFound
from ..ports.effort_repository import EffortRepository
from ..ports.session_repository import PersistedFinding, SessionRepository
from ..session_status import SessionStatus
from ..user import User


def restore_finding(
    session_id: str,
    finding_id: int,
    *,
    session_repository: SessionRepository,
    current_user: User,
    effort_repository: EffortRepository | None = None,
) -> PersistedFinding:
    """Restaura un hallazgo previamente descartado devolviéndolo a estado activo.

    - Control de autorización (ADR-0012, ADR-0070): una sesión ajena responde 404
      (SessionNotFound); la del dueño, 200.
    - Verificación del ciclo de vida (ADR-0014):
      * Sesión finalizada responde 409 (SessionClosed).
    """
    session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)

    require_owner(session_data.owner_id, current_user, session_id)

    if session_data.status == SessionStatus.FINALIZED:
        raise SessionClosed(session_id)

    # Con `effort_repository`, la orden cuenta en el registro de esfuerzo si cambia el estado del
    # posible error (#188, ADR-0050 §4): repetirla sobre uno que ya lo estaba no es otra acción.
    changes = effort_repository is not None and any(
        finding.id == finding_id and finding.status == "dismissed"
        for finding in session_repository.list_findings(
            session_id, latest_only=False, include_dismissed=True
        )
    )

    restored = session_repository.restore_finding(
        session_id,
        finding_id,
    )
    if changes and effort_repository is not None:
        effort_repository.add_finding_action(session_id, "restored", now=datetime.now(UTC))
    return restored
