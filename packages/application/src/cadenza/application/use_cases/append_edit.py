"""Caso de uso: añadir edición al log append-only (ADR-0007, ADR-0009, ADR-0011, ADR-0012, #10)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any

from cadenza.domain import (
    Anchor,
    Clef,
    EditEvent,
    EditOp,
    InvalidEditPayload,
    KeySignature,
    ScoreIR,
    TimingMap,
    UnsupportedEditOpError,
    apply_edit,
    normalize_accidental,
    snapshot_before,
    validate_after,
)

from ..exceptions import (
    Forbidden,
    InvalidEdit,
    SequenceConflict,
    SessionClosed,
    SessionNotFound,
)
from ..ports.edit_event_repository import EditEventRepository
from ..ports.score_exporter import ScoreExporter
from ..ports.score_state_cache import CachedScoreState, ScoreStateCache, ScoreStateKey
from ..ports.session_repository import SessionRepository
from ..score_state import load_state, store_state, timing_of, try_musicxml_of
from ..session_status import SessionStatus
from ..stage_timing import timed_stage
from ..user import Role, User


def _extract_clef(payload: Mapping[str, Any] | None) -> Clef | None:
    if payload is None:
        return None
    raw = payload.get("clef") if "clef" in payload else payload
    if raw is None:
        return None
    if isinstance(raw, Clef):
        return raw
    if isinstance(raw, Mapping):
        return Clef.from_primitive(raw)
    if isinstance(raw, str):
        name = raw.strip().lower()
        if name in ("treble", "sol", "g"):
            return Clef.treble()
        if name in ("bass", "fa", "f"):
            return Clef.bass()
        if name in ("alto", "do3", "c3"):
            return Clef.alto()
        if name in ("tenor", "do4", "c4"):
            return Clef.tenor()
        return Clef(sign=raw.strip().upper())
    return None


def _extract_key_signature(payload: Mapping[str, Any] | None) -> KeySignature | None:
    if payload is None:
        return None
    if "key_signature" in payload:
        raw = payload["key_signature"]
    elif "key" in payload:
        raw = payload["key"]
    else:
        raw = payload
    if raw is None:
        return None
    if isinstance(raw, KeySignature):
        return raw
    if isinstance(raw, Mapping):
        return KeySignature.from_primitive(raw)
    if isinstance(raw, int):
        return KeySignature(fifths=raw)
    return None


def _validate_before(
    score: ScoreIR,
    anchor: Anchor,
    op: EditOp,
    before: Mapping[str, Any] | None,
) -> None:
    """Exige que el `before` que envía el cliente, si lo envía, coincida con el estado."""

    if not before:
        return
    try:
        _check_before(score, anchor, op, before)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise InvalidEdit(f"Estado previo 'before' no válido para {op.value}: {exc!r}") from exc


def _check_before(
    score: ScoreIR,
    anchor: Anchor,
    op: EditOp,
    before: Mapping[str, Any],
) -> None:
    if anchor.part >= len(score.parts):
        raise InvalidEdit(f"Parte fuera de rango: {anchor.part}")
    part = score.parts[anchor.part]

    if anchor.staff >= len(part.staves):
        raise InvalidEdit(f"Pentagrama fuera de rango: {anchor.staff}")
    staff = part.staves[anchor.staff]

    measure = next((m for m in staff.measures if m.number == anchor.measure), None)
    if measure is None:
        raise InvalidEdit(f"Compás inexistente: {anchor.measure}")

    if op is EditOp.SET_CLEF:
        expected_clef = _extract_clef(before)
        if measure.clef != expected_clef:
            raise InvalidEdit(
                f"Estado previo 'before' de clave no coincide: "
                f"esperado '{measure.clef}', recibido '{expected_clef}'"
            )
        return

    if op is EditOp.SET_KEY:
        expected_key = _extract_key_signature(before)
        if measure.key_signature != expected_key:
            raise InvalidEdit(
                f"Estado previo 'before' de armadura no coincide: "
                f"esperado '{measure.key_signature}', recibido '{expected_key}'"
            )
        return

    if op is EditOp.INSERT_EVENT:
        return

    voice_events = [e for e in measure.events if e.voice == anchor.voice]
    if anchor.event_index >= len(voice_events):
        raise InvalidEdit(
            f"Ancla apunta a un evento inexistente en el compás {measure.number}: "
            f"índice {anchor.event_index} (total {len(voice_events)})"
        )
    target = voice_events[anchor.event_index]
    before_map = dict(before)

    if "pitch" in before_map and before_map["pitch"] != target.pitch:
        raise InvalidEdit(
            f"Estado previo 'before' de pitch no coincide: "
            f"esperado '{target.pitch}', recibido '{before_map['pitch']}'"
        )

    if "duration_beats" in before_map:
        raw_dur = before_map["duration_beats"]
        expected_dur = Fraction(str(raw_dur)) if raw_dur is not None else None
        if target.duration_beats != expected_dur:
            raise InvalidEdit(
                f"Estado previo 'before' de duration_beats no coincide: "
                f"esperado {target.duration_beats}, recibido {expected_dur}"
            )

    if "kind" in before_map:
        raw_kind = str(before_map["kind"])
        actual_kind = target.kind.value if hasattr(target.kind, "value") else str(target.kind)
        if actual_kind != raw_kind:
            raise InvalidEdit(
                f"Estado previo 'before' de kind no coincide: "
                f"esperado '{actual_kind}', recibido '{raw_kind}'"
            )

    if "tie" in before_map:
        raw_tie = str(before_map["tie"]) if before_map["tie"] is not None else None
        actual_tie = target.tie.value if target.tie is not None else None
        if actual_tie != raw_tie:
            raise InvalidEdit(
                f"Estado previo 'before' de tie no coincide: "
                f"esperado '{actual_tie}', recibido '{raw_tie}'"
            )

    if "accidental" in before_map:
        actual_accidental = (snapshot_before(score, anchor, EditOp.SET_ACCIDENTAL) or {}).get(
            "accidental"
        )
        raw_accidental = before_map["accidental"]
        if normalize_accidental(raw_accidental) != normalize_accidental(actual_accidental):
            raise InvalidEdit(
                f"Estado previo 'before' de accidental no coincide: "
                f"esperado '{actual_accidental}', recibido '{raw_accidental}'"
            )


@dataclass(frozen=True)
class AppliedEdit:
    """Una edición guardada y el estado que crea, para devolverlo en un solo viaje (#275).

    `musicxml` es None si el estado nuevo no se pudo exportar (se pide a `/export`); `timing`
    es None si el mapa de tiempos no cambia respecto del estado `base_seq`.
    """

    edit: EditEvent
    current_seq: int
    current_score: ScoreIR
    status: str
    musicxml: str | None
    timing: TimingMap | None


@dataclass(frozen=True)
class _Appended:
    edit: EditEvent
    status: str
    previous_key: ScoreStateKey
    previous: CachedScoreState
    key: ScoreStateKey
    state: CachedScoreState


def _append(
    session_id: str,
    *,
    anchor: Anchor,
    op: EditOp,
    session_repository: SessionRepository,
    edit_repository: EditEventRepository,
    current_user: User,
    base_seq: int,
    author: str | None,
    edit_id: str | None,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    created_at: datetime | None,
    score_cache: ScoreStateCache | None,
) -> _Appended:
    with timed_stage("db"):
        session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)

    if current_user.role == Role.TRANSCRIPTOR and session_data.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    if current_user.role == Role.INVESTIGADOR and session_data.owner_id != current_user.id:
        raise Forbidden("Un investigador solo puede editar sus propias sesiones")

    # 1. Comprobar que la sesión no esté finalizada (#34, ADR-0014)
    if session_data.status == SessionStatus.FINALIZED:
        raise SessionClosed(session_id)

    # 2. Verificar base_seq contra el estado actual de la sesión (ADR-0011, #48)
    with timed_stage("db"):
        existing_edits = edit_repository.list_events(session_id)
    current_seq = existing_edits[-1].seq if existing_edits else 0
    if base_seq != current_seq:
        raise SequenceConflict(
            expected_seq=current_seq,
            actual_seq=base_seq,
            message=(
                f"Conflicto de secuencia: base_seq={base_seq} no coincide con "
                f"el estado actual de la sesión (seq={current_seq})"
            ),
        )

    # 3. Estado materializado previo a la edición: de la caché o reconstruido desde el log
    #    (#275, ADR-0037). La validación de la edición se hace siempre sobre él.
    previous_key, previous = load_state(
        session_id, session_data.document, existing_edits, score_cache
    )
    current_score = previous.score

    with timed_stage("materialize"):
        # 4. Validar que 'before', si el cliente lo envía, coincida con el elemento anclado (#10)
        _validate_before(current_score, anchor, op, before)

        # 5. Validar 'after' y fijar 'before' con la instantánea del servidor (ADR-0017, #117)
        try:
            validate_after(current_score, anchor, op, after)
            server_before = snapshot_before(current_score, anchor, op)
        except InvalidEditPayload as exc:
            raise InvalidEdit(f"Contenido de 'after' no válido para {op.value}: {exc}") from exc
        except IndexError as exc:
            raise InvalidEdit(f"Edición no aplicable sobre el estado actual: {exc}") from exc
        except (TypeError, ValueError, OverflowError) as exc:
            # Defensa: un valor JSON inesperado nunca debe producir un 500 ni persistirse.
            raise InvalidEdit(f"Contenido de 'after' no válido para {op.value}: {exc!r}") from exc

        # El log leído es el del estado `base_seq`: la edición siguiente es la `current_seq + 1`
        # (#275: sin otra consulta). La restricción única (sesión, seq) sigue impidiendo que dos
        # peticiones a la vez guarden el mismo número.
        seq = current_seq + 1
        effective_author = author or current_user.username

        edit = EditEvent(
            id=edit_id or str(uuid.uuid4()),
            document_id=session_data.document_id,
            seq=seq,
            anchor=anchor,
            op=op,
            author=effective_author,
            created_at=created_at or datetime.now(UTC),
            before=server_before,
            after=after,
        )

        # 6. Validar que la edición sea aplicable sobre el estado actual (#10). Lo que devuelve es
        #    el estado nuevo: el mismo que daría `materialize` con el log que incluye la edición.
        try:
            new_score = apply_edit(current_score, edit)
        except (IndexError, ValueError, UnsupportedEditOpError) as exc:
            raise InvalidEdit(f"Edición no aplicable sobre el estado actual: {exc}") from exc

    with timed_stage("db"):
        # 7. Persistir la edición en el log append-only
        appended = edit_repository.append(session_id, edit)

        # 8. Si la sesión estaba en 'transcribed', pasa a 'correcting' (#34, ADR-0014)
        status = str(session_data.status)
        if session_data.status == SessionStatus.TRANSCRIBED:
            session_repository.update_status(session_id, SessionStatus.CORRECTING)
            status = str(SessionStatus.CORRECTING)

    # La clave lleva el id de la edición: si la transacción no se confirma, nadie la encuentra.
    key = ScoreStateKey(session_id=session_id, seq=appended.seq, last_edit_id=appended.id)
    state = store_state(score_cache, key, CachedScoreState(score=new_score))
    return _Appended(
        edit=appended,
        status=status,
        previous_key=previous_key,
        previous=previous,
        key=key,
        state=state,
    )


def append_edit(
    session_id: str,
    *,
    anchor: Anchor,
    op: EditOp,
    session_repository: SessionRepository,
    edit_repository: EditEventRepository,
    current_user: User,
    base_seq: int = 0,
    author: str | None = None,
    edit_id: str | None = None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    created_at: datetime | None = None,
    score_cache: ScoreStateCache | None = None,
) -> EditEvent:
    """Añade un nuevo evento inmutable al log de la sesión verificando su existencia y propiedad.

    La autoría la fija el servidor a partir del usuario actual (ADR-0012).
    Verifica que base_seq coincida con el seq del estado actual de la sesión (ADR-0011, #48).
    Aplica y valida la edición sobre el estado materializado actual antes de persistir (#10).
    Rechaza un `after` incoherente con la operación y guarda como `before` la instantánea
    del estado que fija el servidor, para que deshacer sea exacto (ADR-0017, #117).
    Con `score_cache`, el estado previo sale de la caché si está y el nuevo se guarda en ella
    (#275, ADR-0037); la validación es la misma.
    """

    return _append(
        session_id,
        anchor=anchor,
        op=op,
        session_repository=session_repository,
        edit_repository=edit_repository,
        current_user=current_user,
        base_seq=base_seq,
        author=author,
        edit_id=edit_id,
        before=before,
        after=after,
        created_at=created_at,
        score_cache=score_cache,
    ).edit


def append_edit_with_state(
    session_id: str,
    *,
    anchor: Anchor,
    op: EditOp,
    session_repository: SessionRepository,
    edit_repository: EditEventRepository,
    exporter: ScoreExporter,
    current_user: User,
    base_seq: int = 0,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    score_cache: ScoreStateCache | None = None,
) -> AppliedEdit:
    """`append_edit` y, además, el estado que crea, para que la vista lo muestre sin volver a
    pedirlo (#275, ADR-0037).

    Devuelve el `ScoreIR` nuevo, su MusicXML y su mapa de tiempos, este solo si cambia
    respecto del estado `base_seq`. La edición se valida y se guarda igual que con
    `append_edit`.
    """

    done = _append(
        session_id,
        anchor=anchor,
        op=op,
        session_repository=session_repository,
        edit_repository=edit_repository,
        current_user=current_user,
        base_seq=base_seq,
        author=None,
        edit_id=None,
        before=before,
        after=after,
        created_at=None,
        score_cache=score_cache,
    )
    state, musicxml = try_musicxml_of(done.key, done.state, exporter, score_cache)
    _, previous_timing = timing_of(done.previous_key, done.previous, score_cache)
    state, timing = timing_of(done.key, state, score_cache)
    return AppliedEdit(
        edit=done.edit,
        current_seq=done.edit.seq,
        current_score=state.score,
        status=done.status,
        musicxml=musicxml,
        timing=None if timing == previous_timing else timing,
    )
