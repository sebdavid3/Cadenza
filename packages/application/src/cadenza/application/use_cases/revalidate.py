"""Caso de uso: revalidar partitura tras correcciones (ADR-0009, ADR-0012, ADR-0013, #11)."""

from __future__ import annotations

from dataclasses import dataclass

from cadenza.validation import ValidationEngine

from ..current_validation import store_current_validation
from ..exceptions import SessionNotFound
from ..ports.edit_event_repository import EditEventRepository
from ..ports.session_repository import PersistedFinding, SessionRepository
from ..ports.suggestion_model import SuggestionModel
from ..user import Role, User


@dataclass(frozen=True)
class RevalidateResult:
    """Resultado de la revalidación de la partitura (ADR-0013, #11)."""

    session_id: str
    current_seq: int
    findings: tuple[PersistedFinding, ...]


def revalidate(
    session_id: str,
    *,
    validator: ValidationEngine,
    session_repository: SessionRepository,
    edit_repository: EditEventRepository,
    current_user: User,
    suggestion_model: SuggestionModel | None = None,
) -> RevalidateResult:
    """Revalida la partitura sobre su estado materializado actual.

    1. Recupera la sesión y comprueba permisos (ADR-0012).
    2. Valida el estado actual con `store_current_validation`: las reglas y la capa sobre el
       estado materializado, con los hallazgos asociados al último `seq` aplicado; hereda los
       descartes (#36) y los rechazos (ADR-0036 §4) de la validación vigente mientras su evento
       no cambie (ADR-0035), y en `unassisted` no ejecuta nada (D38).
    3. Devuelve solo los hallazgos activos (#36).
    """

    session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)

    if current_user.role == Role.TRANSCRIPTOR and session_data.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    validation = store_current_validation(
        session_data,
        edit_repository.list_events(session_id),
        validator=validator,
        session_repository=session_repository,
        suggestion_model=suggestion_model,
    )
    return RevalidateResult(
        session_id=session_id,
        current_seq=validation.seq,
        findings=validation.active,
    )
