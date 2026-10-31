"""Caso de uso: rechazar una sugerencia de la capa (ADR-0036 §5, ADR-0012, ADR-0014)."""

from __future__ import annotations

from ..exceptions import (
    Forbidden,
    SessionClosed,
    SessionNotFound,
    SuggestionConflict,
    SuggestionNotFound,
)
from ..ports.session_repository import PersistedSuggestion, SessionRepository
from ..session_status import SessionStatus
from ..suggestions import ACCEPTED, REJECTED
from ..user import Role, User


def reject_suggestion(
    session_id: str,
    suggestion_id: int,
    *,
    session_repository: SessionRepository,
    current_user: User,
) -> PersistedSuggestion:
    """Rechaza una sugerencia: queda guardado quién y cuándo, y no cambia después.

    Como descartar un hallazgo: un transcriptor ajeno recibe 404 y un investigador ajeno 403;
    en una sesión finalizada, 409. Una sugerencia aceptada no se puede rechazar (409) y
    rechazar una ya rechazada la devuelve tal cual. Rechazar una de una validación anterior
    se admite. Rechazar no descarta el hallazgo.
    """
    session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)
    if current_user.role == Role.TRANSCRIPTOR and session_data.owner_id != current_user.id:
        raise SessionNotFound(session_id)
    if current_user.role == Role.INVESTIGADOR and session_data.owner_id != current_user.id:
        raise Forbidden("Un investigador solo puede responder sugerencias de sus propias sesiones")
    if session_data.status == SessionStatus.FINALIZED:
        raise SessionClosed(session_id)

    suggestion = session_repository.get_suggestion(session_id, suggestion_id)
    if suggestion is None:
        raise SuggestionNotFound(suggestion_id)
    if suggestion.response == ACCEPTED:
        raise SuggestionConflict(
            suggestion_id, f"La sugerencia {suggestion_id} ya se aplicó: no se puede rechazar"
        )
    if suggestion.response == REJECTED:
        return suggestion
    try:
        return session_repository.respond_suggestion(
            session_id, suggestion_id, response=REJECTED, user=current_user.username
        )
    except SuggestionConflict:
        # Otra petición la respondió entre la lectura y aquí. Si fue otro rechazo (dos clics),
        # se devuelve ese; si se aplicó, 409. La respuesta guardada no cambia.
        stored = session_repository.get_suggestion(session_id, suggestion_id)
        if stored is not None and stored.response == REJECTED:
            return stored
        raise
