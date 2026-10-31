"""Caso de uso: finalizar sesión de transcripción (ADR-0009, ADR-0012, ADR-0014, #34)."""

from __future__ import annotations

from dataclasses import dataclass

from cadenza.validation import ValidationEngine

from ..current_validation import store_current_validation
from ..exceptions import Forbidden, SessionClosed, SessionNotFound
from ..ports.edit_event_repository import EditEventRepository
from ..ports.session_repository import PersistedFinding, SessionRepository
from ..ports.suggestion_model import SuggestionModel
from ..session_status import SessionStatus
from ..user import Role, User


@dataclass(frozen=True)
class FinalizeResult:
    """Resultado de la finalización de una sesión (ADR-0014, #34)."""

    session_id: str
    status: str
    final_seq: int
    findings: tuple[PersistedFinding, ...]


def finalize_session(
    session_id: str,
    *,
    validator: ValidationEngine,
    session_repository: SessionRepository,
    edit_repository: EditEventRepository,
    current_user: User,
    suggestion_model: SuggestionModel | None = None,
) -> FinalizeResult:
    """Finaliza una sesión marcándola como cerrada para nuevas ediciones.

    1. Comprueba existencia y propiedad según ADR-0012.
    2. Una sesión ya finalizada no se vuelve a finalizar: `SessionClosed` (409). Su validación
       final no se rehace hasta reabrirla (ADR-0043).
    3. Valida el estado actual como una revalidación (`store_current_validation`, D65): las
       reglas y la capa, heredando los descartes y los rechazos de la validación vigente; en
       `unassisted` no corre nada y se guardan los hallazgos vacíos (ADR-0040 §13).
    4. Actualiza el estado a `finalized` (#34).
    5. Devuelve el estado, el seq final y los hallazgos activos, como `revalidate`.
    """

    session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)

    if current_user.role == Role.TRANSCRIPTOR and session_data.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    if current_user.role == Role.INVESTIGADOR and session_data.owner_id != current_user.id:
        raise Forbidden("Un investigador solo puede finalizar sus propias sesiones")

    if session_data.status == SessionStatus.FINALIZED:
        raise SessionClosed(session_id)

    validation = store_current_validation(
        session_data,
        edit_repository.list_events(session_id),
        validator=validator,
        session_repository=session_repository,
        suggestion_model=suggestion_model,
    )
    updated = session_repository.update_status(session_id, SessionStatus.FINALIZED)

    return FinalizeResult(
        session_id=session_id,
        status=updated.status,
        final_seq=validation.seq,
        findings=validation.active,
    )
