"""Caso de uso: reabrir una sesión finalizada (ADR-0009, ADR-0012, ADR-0014, #34)."""

from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import Forbidden, SessionNotFound
from ..ports.edit_event_repository import EditEventRepository
from ..ports.session_repository import SessionRepository
from ..session_status import SessionStatus
from ..user import Role, User


@dataclass(frozen=True)
class ReopenResult:
    """Resultado de la reapertura de una sesión (ADR-0014, #34)."""

    session_id: str
    status: str
    current_seq: int


def reopen_session(
    session_id: str,
    *,
    session_repository: SessionRepository,
    edit_repository: EditEventRepository,
    current_user: User,
) -> ReopenResult:
    """Reabre una sesión finalizada para permitir nuevas ediciones.

    1. Comprueba existencia y propiedad según ADR-0012.
    2. Transiciona el estado a `correcting` (#34).
    3. Devuelve la sesión actualizada con su secuencia actual.
    """

    session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)

    if current_user.role == Role.TRANSCRIPTOR and session_data.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    if current_user.role == Role.INVESTIGADOR and session_data.owner_id != current_user.id:
        raise Forbidden("Un investigador solo puede reabrir sus propias sesiones")

    # 1. Recuperar ediciones y determinar secuencia actual
    edits = edit_repository.list_events(session_id)
    current_seq = edits[-1].seq if edits else 0

    # 2. Transicionar de nuevo a correcting (o transcribed si nunca hubo ediciones)
    new_status = SessionStatus.CORRECTING if edits else SessionStatus.TRANSCRIBED
    updated = session_repository.update_status(session_id, new_status)

    return ReopenResult(
        session_id=session_id,
        status=updated.status,
        current_seq=current_seq,
    )
