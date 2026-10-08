"""Caso de uso: deshacer edición como evento compensatorio (ADR-0007, ADR-0014, #35)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cadenza.domain import (
    AnchorIndex,
    EditEvent,
    ScoreIR,
    UnsupportedEditOpError,
    apply_edit,
    build_anchor_index,
    create_inverse_edit,
    get_last_active_edit,
    materialize,
)

from ..exceptions import (
    Forbidden,
    InvalidEdit,
    NoEditsToUndo,
    SequenceConflict,
    SessionClosed,
    SessionNotFound,
)
from ..ports.edit_event_repository import EditEventRepository
from ..ports.session_repository import SessionRepository
from ..session_status import SessionStatus
from ..user import Role, User


@dataclass(frozen=True)
class UndoResult:
    """Resultado tras registrar un evento compensatorio en el servidor."""

    session_id: str
    current_seq: int
    undone_edit_id: str
    compensatory_edit: EditEvent
    current_score: dict[str, Any]
    anchor_index: dict[str, Any]


def undo_edit(
    session_id: str,
    *,
    session_repository: SessionRepository,
    edit_repository: EditEventRepository,
    current_user: User,
    base_seq: int | None = None,
    author: str | None = None,
    undo_id: str | None = None,
    created_at: datetime | None = None,
) -> UndoResult:
    """Deshace la última edición activa de la sesión registrando un evento compensatorio inverso.

    - Respeta la inmutabilidad del log append-only (ADR-0007).
    - Valida propiedad y control de acceso (ADR-0012).
    - Valida que la sesión no esté finalizada (ADR-0014).
    - Si se provee base_seq, verifica que coincida con el seq del estado actual (ADR-0011).
    - Si no hay ediciones activas por deshacer, lanza NoEditsToUndo.
    - Proyecta y valida el evento inverso sobre el estado materializado actual.
    - Retorna el nuevo current_seq, la partitura materializada actualizada y el índice de anclas.
    """
    session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)

    if current_user.role == Role.TRANSCRIPTOR and session_data.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    if current_user.role == Role.INVESTIGADOR and session_data.owner_id != current_user.id:
        raise Forbidden("Un investigador solo puede editar sus propias sesiones")

    if session_data.status == SessionStatus.FINALIZED:
        raise SessionClosed(session_id)

    existing_edits = edit_repository.list_events(session_id)
    current_seq = existing_edits[-1].seq if existing_edits else 0

    if base_seq is not None and base_seq != current_seq:
        raise SequenceConflict(
            expected_seq=current_seq,
            actual_seq=base_seq,
            message=(
                f"Conflicto de secuencia al deshacer: base_seq={base_seq} no coincide con "
                f"el estado actual de la sesión (seq={current_seq})"
            ),
        )

    target_edit = get_last_active_edit(existing_edits)
    if target_edit is None:
        raise NoEditsToUndo(session_id)

    raw_score = ScoreIR.from_primitive(session_data.document["score"])
    current_score = materialize(raw_score, existing_edits)

    seq = edit_repository.next_seq(session_id)
    effective_author = author or current_user.username

    inverse_edit = create_inverse_edit(
        target_edit,
        id=undo_id or str(uuid.uuid4()),
        seq=seq,
        author=effective_author,
        created_at=created_at or datetime.now(UTC),
    )

    try:
        new_score = apply_edit(current_score, inverse_edit)
    except (IndexError, ValueError, UnsupportedEditOpError) as exc:
        raise InvalidEdit(f"Evento compensatorio no aplicable: {exc}") from exc

    appended = edit_repository.append(session_id, inverse_edit)

    if session_data.status == SessionStatus.TRANSCRIBED:
        session_repository.update_status(session_id, SessionStatus.CORRECTING)

    all_edits = (*existing_edits, appended)
    raw_anchors = (
        AnchorIndex.from_primitive(session_data.document["anchors"])
        if "anchors" in session_data.document
        else build_anchor_index(raw_score)
    )
    new_anchors = build_anchor_index(
        new_score,
        raw_anchors=raw_anchors,
        edits=all_edits,
        at_seq=seq,
    )

    return UndoResult(
        session_id=session_id,
        current_seq=seq,
        undone_edit_id=target_edit.id,
        compensatory_edit=appended,
        current_score=new_score.to_primitive(),
        anchor_index=new_anchors.to_primitive(),
    )
