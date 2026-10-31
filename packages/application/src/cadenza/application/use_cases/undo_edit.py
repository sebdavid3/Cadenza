"""Caso de uso: deshacer edición como evento compensatorio (ADR-0007, ADR-0014, #35)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cadenza.domain import (
    AnchorIndex,
    EditEvent,
    TimingMap,
    UnsupportedEditOpError,
    apply_edit,
    build_anchor_index,
    create_inverse_edit,
    get_last_active_edit,
    has_complete_before,
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
from ..ports.score_exporter import ScoreExporter
from ..ports.score_state_cache import CachedScoreState, ScoreStateCache, ScoreStateKey
from ..ports.session_repository import SessionRepository
from ..score_state import load_state, raw_score_of, store_state, timing_of, try_musicxml_of
from ..session_status import SessionStatus
from ..stage_timing import timed_stage
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
    # Lo que la vista necesita para mostrar el estado nuevo sin pedirlo (#275, ADR-0037). Con
    # `exporter`, `musicxml` es None si la exportación falla; sin él, no se exporta.
    status: str = "correcting"
    musicxml: str | None = None
    # None si el mapa de tiempos no cambia respecto del estado `base_seq`.
    timing: TimingMap | None = None


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
    score_cache: ScoreStateCache | None = None,
    exporter: ScoreExporter | None = None,
) -> UndoResult:
    """Deshace la última edición activa de la sesión registrando un evento compensatorio inverso.

    - Respeta la inmutabilidad del log append-only (ADR-0007).
    - Valida propiedad y control de acceso (ADR-0012).
    - Valida que la sesión no esté finalizada (ADR-0014).
    - Si se provee base_seq, verifica que coincida con el seq del estado actual (ADR-0011).
    - Si no hay ediciones activas por deshacer, lanza NoEditsToUndo.
    - Si la edición no guardó su estado previo completo, lanza InvalidEdit (ADR-0017).
    - Proyecta y valida el evento inverso sobre el estado materializado actual.
    - Retorna el nuevo current_seq, la partitura materializada actualizada y el índice de anclas.
    - Con `score_cache`, el estado previo sale de la caché y el nuevo se guarda; con `exporter`,
      devuelve además su MusicXML, y siempre su mapa de tiempos si cambia (#275, ADR-0037).
    """
    with timed_stage("db"):
        session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)

    if current_user.role == Role.TRANSCRIPTOR and session_data.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    if current_user.role == Role.INVESTIGADOR and session_data.owner_id != current_user.id:
        raise Forbidden("Un investigador solo puede editar sus propias sesiones")

    if session_data.status == SessionStatus.FINALIZED:
        raise SessionClosed(session_id)

    with timed_stage("db"):
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

    # Una edición guardada sin estado previo completo (anterior a ADR-0017) no se puede
    # invertir sin corromper la sesión: se rechaza en lugar de inventar el estado (#117).
    if not has_complete_before(target_edit):
        raise InvalidEdit(
            f"La edición seq={target_edit.seq} ({target_edit.op.value}) no guardó su estado "
            "previo completo y no se puede deshacer sin alterar la sesión"
        )

    previous_key, previous = load_state(
        session_id, session_data.document, existing_edits, score_cache
    )
    current_score = previous.score

    # El log leído llega a `current_seq`: la compensatoria es la siguiente (#275).
    seq = current_seq + 1
    effective_author = author or current_user.username

    inverse_edit = create_inverse_edit(
        target_edit,
        id=undo_id or str(uuid.uuid4()),
        seq=seq,
        author=effective_author,
        created_at=created_at or datetime.now(UTC),
    )

    with timed_stage("materialize"):
        try:
            new_score = apply_edit(current_score, inverse_edit)
        except (IndexError, ValueError, UnsupportedEditOpError) as exc:
            raise InvalidEdit(f"Evento compensatorio no aplicable: {exc}") from exc

    with timed_stage("db"):
        appended = edit_repository.append(session_id, inverse_edit)

        status = str(session_data.status)
        if session_data.status == SessionStatus.TRANSCRIBED:
            session_repository.update_status(session_id, SessionStatus.CORRECTING)
            status = str(SessionStatus.CORRECTING)

    key = ScoreStateKey(session_id=session_id, seq=appended.seq, last_edit_id=appended.id)
    state = store_state(score_cache, key, CachedScoreState(score=new_score))

    # El índice de anclas sigue en la respuesta del contrato v1 (ADR-0034).
    with timed_stage("materialize"):
        all_edits = (*existing_edits, appended)
        raw_anchors = (
            AnchorIndex.from_primitive(session_data.document["anchors"])
            if "anchors" in session_data.document
            else build_anchor_index(raw_score_of(session_data.document))
        )
        new_anchors = build_anchor_index(
            new_score,
            raw_anchors=raw_anchors,
            edits=all_edits,
            at_seq=seq,
        )

    musicxml: str | None = None
    if exporter is not None:
        state, musicxml = try_musicxml_of(key, state, exporter, score_cache)
    _, previous_timing = timing_of(previous_key, previous, score_cache)
    state, timing = timing_of(key, state, score_cache)

    with timed_stage("serialize"):
        current_primitive = new_score.to_primitive()
        anchors_primitive = new_anchors.to_primitive()

    return UndoResult(
        session_id=session_id,
        current_seq=seq,
        undone_edit_id=target_edit.id,
        compensatory_edit=appended,
        current_score=current_primitive,
        anchor_index=anchors_primitive,
        status=status,
        musicxml=musicxml,
        timing=None if timing == previous_timing else timing,
    )
