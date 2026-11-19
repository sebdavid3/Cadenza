"""Derivación determinista de EditEvents a partir del diff OMR↔Ground Truth (ADR-0008, D21).

Simula al 'corrector ideal': compara el `ScoreIR` predicho (p. ej. salida de HOMR)
con el `ScoreIR` de referencia (ground truth) alineando compases y eventos por voz,
y genera la secuencia canónica de `EditEvent`s que transforma el predicho
en el de referencia satisfaciendo la propiedad formal:

    materialize(predicted, edits) == ground_truth
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any, Final

from cadenza.domain import (
    Anchor,
    Clef,
    EditEvent,
    EditOp,
    Event,
    EventKind,
    KeySignature,
    ScoreIR,
    apply_edit,
    normalize_accidental,
    snapshot_before,
    validate_after,
)
from cadenza.domain.chords import is_chord_head

KEEP_CHORD: Final[str] = "keep_chord"

_PITCH_RE: Final[re.Pattern[str]] = re.compile(r"^([A-Ga-g])(#{1,2}|b{1,2}|-{1,2}|x)?(-?\d+)$")


def split_pitch(pitch: str | None) -> tuple[str, str, str]:
    """Descompone una altura en (nombre, alteración normalizada, octava).

    Si `pitch` es None o inválido, devuelve `("", "", "")`.
    Ejemplos:
        `"Bb4"` -> `("B", "b", "4")`
        `"C#5"` -> `("C", "#", "5")`
        `"D4"`  -> `("D", "", "4")`
    """
    if pitch is None:
        return ("", "", "")
    match = _PITCH_RE.match(pitch.strip())
    if not match:
        return ("", "", "")
    letter = match.group(1).upper()
    acc = match.group(2) or ""
    if acc in ("-", "b"):
        acc = "b"
    elif acc in ("--", "bb"):
        acc = "bb"
    elif acc in ("x", "##"):
        acc = "##"
    octave = match.group(3)
    return (letter, acc, octave)


def classify_pitch_change(before: str | None, after: str | None) -> EditOp | None:
    """Operación que corrige `before` para que suene `after`, o None si no cambia.

    Con la misma letra y la misma octava es una corrección de alteración
    (`SetAccidental`); si no, un cambio de altura (`SetPitch`). La derivación y el corpus
    de correcciones (#255) clasifican con esta misma función.
    """
    if before == after:
        return None
    b_let, _, b_oct = split_pitch(before)
    a_let, _, a_oct = split_pitch(after)
    if b_let and a_let and b_let == a_let and b_oct == a_oct:
        return EditOp.SET_ACCIDENTAL
    return EditOp.SET_PITCH


@dataclass(frozen=True, slots=True)
class EditDistribution:
    """Distribución de eventos de edición clasificados por tipo de operación."""

    set_pitch: int = 0
    set_duration: int = 0
    set_accidental: int = 0
    insert_event: int = 0
    delete_event: int = 0
    set_clef: int = 0
    set_key: int = 0
    total: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "SetPitch": self.set_pitch,
            "SetDuration": self.set_duration,
            "SetAccidental": self.set_accidental,
            "InsertEvent": self.insert_event,
            "DeleteEvent": self.delete_event,
            "SetClef": self.set_clef,
            "SetKey": self.set_key,
            "Total": self.total,
        }


def count_edits_by_op(edits: Iterable[EditEvent]) -> EditDistribution:
    """Calcula la distribución de operaciones a partir de una secuencia de ediciones."""
    counts: dict[str, int] = {}
    total = 0
    for edit in edits:
        op_name = edit.op.value if hasattr(edit.op, "value") else str(edit.op)
        counts[op_name] = counts.get(op_name, 0) + 1
        total += 1

    return EditDistribution(
        set_pitch=counts.get(EditOp.SET_PITCH.value, 0),
        set_duration=counts.get(EditOp.SET_DURATION.value, 0),
        set_accidental=counts.get(EditOp.SET_ACCIDENTAL.value, 0),
        insert_event=counts.get(EditOp.INSERT_EVENT.value, 0),
        delete_event=counts.get(EditOp.DELETE_EVENT.value, 0),
        set_clef=counts.get(EditOp.SET_CLEF.value, 0),
        set_key=counts.get(EditOp.SET_KEY.value, 0),
        total=total,
    )


def _substitution_cost(p: Event, g: Event) -> float:
    if p == g:
        return 0.0
    if p.kind != g.kind:
        # Nota vs Silencio: requiere reemplazo estructural (Delete + Insert)
        return float("inf")

    if p.kind is EventKind.REST:
        # Un silencio que se ve y uno invisible (ADR-0032) no se sustituyen: Delete + Insert.
        if p.hidden != g.hidden:
            return float("inf")
        return 1.0 if p.duration_beats != g.duration_beats else 0.0

    # Ambas son notas (EventKind.NOTE)
    if p.tie != g.tie or p.is_chord != g.is_chord:
        return float("inf")

    cost = 0.0
    if p.pitch != g.pitch:
        cost += 1.0
    if p.duration_beats != g.duration_beats:
        cost += 1.0
    return cost


def align_voice_events(
    pred_events: Sequence[Event],
    gt_events: Sequence[Event],
) -> list[tuple[Event | None, Event | None]]:
    """Alinea dos secuencias de eventos de una voz minimizando el costo de edición."""
    n = len(pred_events)
    m = len(gt_events)

    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i * 1.0
    for j in range(1, m + 1):
        dp[0][j] = j * 1.0

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost_sub = _substitution_cost(pred_events[i - 1], gt_events[j - 1])
            sub_total = dp[i - 1][j - 1] + cost_sub
            del_total = dp[i - 1][j] + 1.0
            ins_total = dp[i][j - 1] + 1.0
            dp[i][j] = min(sub_total, del_total, ins_total)

    alignment: list[tuple[Event | None, Event | None]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            cost_sub = _substitution_cost(pred_events[i - 1], gt_events[j - 1])
            if cost_sub < float("inf") and abs(dp[i][j] - (dp[i - 1][j - 1] + cost_sub)) < 1e-6:
                alignment.append((pred_events[i - 1], gt_events[j - 1]))
                i -= 1
                j -= 1
                continue
        if j > 0 and abs(dp[i][j] - (dp[i][j - 1] + 1.0)) < 1e-6:
            alignment.append((None, gt_events[j - 1]))
            j -= 1
            continue
        if i > 0 and abs(dp[i][j] - (dp[i - 1][j] + 1.0)) < 1e-6:
            alignment.append((pred_events[i - 1], None))
            i -= 1
            continue
        if i > 0:
            alignment.append((pred_events[i - 1], None))
            i -= 1
        elif j > 0:
            alignment.append((None, gt_events[j - 1]))
            j -= 1

    alignment.reverse()
    return alignment


def _insert_after(g: Event) -> dict[str, Any]:
    """El `after` de `InsertEvent` que inserta el evento `g` de la verdad."""

    after_dict: dict[str, Any] = {
        "kind": g.kind.value,
        "pitch": g.pitch,
        "duration_beats": g.duration_beats,
        "tie": g.tie.value if g.tie is not None else None,
        "is_chord": g.is_chord,
    }
    if g.hidden:
        # Solo si lo es: sin silencios invisibles, las ediciones son las de antes.
        after_dict["hidden"] = True
    return after_dict


def _make_edit(
    *,
    document_id: str,
    seq: int,
    anchor: Anchor,
    op: EditOp,
    author: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    edit_id: str | None = None,
    created_at: datetime | None = None,
) -> EditEvent:
    return EditEvent(
        id=edit_id or f"edit-{document_id}-{seq}-{uuid.uuid4().hex[:8]}",
        document_id=document_id,
        seq=seq,
        anchor=anchor,
        op=op,
        author=author,
        created_at=created_at or datetime.now(UTC),
        before=before,
        after=after,
    )


def _derive_voice_edits(
    *,
    part_idx: int,
    staff_idx: int,
    staff_id: str,
    meas_num: int,
    voice_idx: int,
    pred_events: Sequence[Event],
    gt_events: Sequence[Event],
    start_seq: int,
    document_id: str,
    author: str,
) -> tuple[list[EditEvent], int]:
    aligned = align_voice_events(pred_events, gt_events)
    current_events = list(pred_events)
    edits: list[EditEvent] = []
    seq = start_seq
    curr_idx = 0

    anchor_base = Anchor(
        part=part_idx,
        staff=staff_idx,
        measure=meas_num,
        voice=voice_idx,
        event_index=0,
        staff_id=staff_id,
    )

    for p, g in aligned:
        if p is not None and g is not None:
            anchor = replace(anchor_base, event_index=curr_idx)
            current_target = current_events[curr_idx]

            # 1. Pitch / Accidental
            pitch_op = classify_pitch_change(current_target.pitch, g.pitch)
            if pitch_op is not None:
                p_let, p_acc, p_oct = split_pitch(current_target.pitch)
                _, g_acc, _ = split_pitch(g.pitch)
                if pitch_op is EditOp.SET_ACCIDENTAL:
                    # Misma letra y octava: corrección de alteración puntual
                    edits.append(
                        _make_edit(
                            document_id=document_id,
                            seq=seq,
                            anchor=anchor,
                            op=EditOp.SET_ACCIDENTAL,
                            author=author,
                            before={"accidental": p_acc},
                            after={"accidental": g_acc},
                        )
                    )
                    seq += 1
                    current_events[curr_idx] = replace(
                        current_target,
                        pitch=f"{p_let}{g_acc}{p_oct}",
                    )
                    current_target = current_events[curr_idx]
                else:
                    # Diferente letra u octava: cambio de nota
                    edits.append(
                        _make_edit(
                            document_id=document_id,
                            seq=seq,
                            anchor=anchor,
                            op=EditOp.SET_PITCH,
                            author=author,
                            before={"pitch": current_target.pitch},
                            after={"pitch": g.pitch},
                        )
                    )
                    seq += 1
                    current_events[curr_idx] = replace(current_target, pitch=g.pitch)
                    current_target = current_events[curr_idx]

            # 2. Duration
            if current_target.duration_beats != g.duration_beats:
                edits.append(
                    _make_edit(
                        document_id=document_id,
                        seq=seq,
                        anchor=anchor,
                        op=EditOp.SET_DURATION,
                        author=author,
                        before={"duration_beats": current_target.duration_beats},
                        after={"duration_beats": g.duration_beats},
                    )
                )
                seq += 1
                current_events[curr_idx] = replace(current_target, duration_beats=g.duration_beats)
                current_target = current_events[curr_idx]

            curr_idx += 1

        elif p is not None and g is None:
            # Eliminación
            anchor = replace(anchor_base, event_index=curr_idx)
            target = current_events[curr_idx]
            before_dict = {
                "kind": target.kind.value,
                "pitch": target.pitch,
                "duration_beats": target.duration_beats,
            }
            # La primera nota de un acorde se borra con `keep_chord` y la siguiente pasa a ser
            # la primera, con la figura y las marcas del acorde (ADR-0055 §3, #456).
            head = is_chord_head(current_events, curr_idx)
            edits.append(
                _make_edit(
                    document_id=document_id,
                    seq=seq,
                    anchor=anchor,
                    op=EditOp.DELETE_EVENT,
                    author=author,
                    before=before_dict,
                    after={KEEP_CHORD: True} if head else None,
                )
            )
            seq += 1
            del current_events[curr_idx]
            if head:
                current_events[curr_idx] = replace(
                    current_events[curr_idx],
                    is_chord=False,
                    duration_beats=target.duration_beats,
                    articulations=target.articulations,
                    fermata=target.fermata,
                    slurs=target.slurs,
                )

        elif p is None and g is not None:
            # Inserción
            anchor = replace(anchor_base, event_index=curr_idx)
            after_dict = _insert_after(g)
            edits.append(
                _make_edit(
                    document_id=document_id,
                    seq=seq,
                    anchor=anchor,
                    op=EditOp.INSERT_EVENT,
                    author=author,
                    before=None,
                    after=after_dict,
                )
            )
            seq += 1
            current_events.insert(curr_idx, g)
            curr_idx += 1

    return edits, seq


def derive_edit_events(
    predicted: ScoreIR,
    ground_truth: ScoreIR,
    *,
    document_id: str = "doc-1",
    author: str = "ideal_corrector",
    base_seq: int = 1,
) -> list[EditEvent]:
    """Deriva la lista de `EditEvent`s que transforma `predicted` en `ground_truth`.

    Recorre por compás y voz alineando los eventos y atributos (clef, key_signature).
    Cada edición es válida para la API sobre el estado que dejan las anteriores (#456):
    `replay_edits(predicted, edits)` no falla. Si la alineación de una voz de un compás da
    una edición que la API rechaza, esa voz se reescribe entera (borrar e insertar); si
    tampoco así es posible (la verdad tiene algo que ninguna edición crea, como una nota
    `is_chord` tras un silencio), la voz se deja sin derivar y el resultado no reproduce la
    verdad. Lo mismo con una clave o una armadura que la API rechace.
    """
    edits: list[EditEvent] = []
    seq = base_seq
    # El estado tras las ediciones ya derivadas: cada una se valida sobre el suyo, como la API.
    state = predicted

    for part_idx, pred_part in enumerate(predicted.parts):
        if part_idx >= len(ground_truth.parts):
            break
        gt_part = ground_truth.parts[part_idx]

        for staff_idx, pred_staff in enumerate(pred_part.staves):
            if staff_idx >= len(gt_part.staves):
                break
            gt_staff = gt_part.staves[staff_idx]

            meas_count = min(len(pred_staff.measures), len(gt_staff.measures))
            for m_idx in range(meas_count):
                pred_meas = pred_staff.measures[m_idx]
                gt_meas = gt_staff.measures[m_idx]
                measure_start, measure_seq = len(edits), seq

                # 1. Clave (SET_CLEF)
                if pred_meas.clef != gt_meas.clef and gt_meas.clef is not None:
                    clef_anchor = Anchor(
                        part=part_idx,
                        staff=staff_idx,
                        measure=pred_meas.number,
                        voice=0,
                        event_index=0,
                        staff_id=pred_staff.id,
                    )
                    edits.append(
                        _make_edit(
                            document_id=document_id,
                            seq=seq,
                            anchor=clef_anchor,
                            op=EditOp.SET_CLEF,
                            author=author,
                            before=(
                                {"clef": pred_meas.clef.to_primitive()} if pred_meas.clef else None
                            ),
                            after={"clef": gt_meas.clef.to_primitive()},
                        )
                    )
                    seq += 1

                # 2. Armadura (SET_KEY)
                if (
                    pred_meas.key_signature != gt_meas.key_signature
                    and gt_meas.key_signature is not None
                ):
                    key_anchor = Anchor(
                        part=part_idx,
                        staff=staff_idx,
                        measure=pred_meas.number,
                        voice=0,
                        event_index=0,
                        staff_id=pred_staff.id,
                    )
                    edits.append(
                        _make_edit(
                            document_id=document_id,
                            seq=seq,
                            anchor=key_anchor,
                            op=EditOp.SET_KEY,
                            author=author,
                            before=(
                                {"key_signature": pred_meas.key_signature.to_primitive()}
                                if pred_meas.key_signature
                                else None
                            ),
                            after={"key_signature": gt_meas.key_signature.to_primitive()},
                        )
                    )
                    seq += 1

                # La clave y la armadura, al estado; sin ellas si la API las rechazaría.
                try:
                    state = replay_edits(state, edits[measure_start:])
                except InvalidDerivedEdit:
                    del edits[measure_start:]
                    seq = measure_seq

                # 3. Eventos por voz
                voices = sorted(
                    {e.voice for e in pred_meas.events} | {e.voice for e in gt_meas.events}
                )
                if not voices:
                    voices = [0]

                for v in voices:
                    p_events = [e for e in pred_meas.events if e.voice == v]
                    g_events = [e for e in gt_meas.events if e.voice == v]
                    voice_args: dict[str, Any] = {
                        "part_idx": part_idx,
                        "staff_idx": staff_idx,
                        "staff_id": pred_staff.id,
                        "meas_num": pred_meas.number,
                        "voice_idx": v,
                        "pred_events": p_events,
                        "gt_events": g_events,
                        "start_seq": seq,
                        "document_id": document_id,
                        "author": author,
                    }
                    v_edits, next_seq = _derive_voice_edits(**voice_args)
                    try:
                        voice_state = replay_edits(state, v_edits)
                    except InvalidDerivedEdit:
                        # La alineación da una edición que la API rechaza (p. ej. un evento
                        # entre las notas de un acorde, ADR-0055 §2): la voz del compás se
                        # reescribe entera, que siempre es válido (#456).
                        v_edits, next_seq = _rewrite_voice_edits(**voice_args)
                        try:
                            voice_state = replay_edits(state, v_edits)
                        except InvalidDerivedEdit:
                            # Ni así: la verdad tiene algo que ninguna edición de la API crea.
                            # La voz se queda sin derivar, sin tumbar la partitura entera.
                            continue
                    state, seq = voice_state, next_seq
                    edits.extend(v_edits)

    return edits


def _rewrite_voice_edits(
    *,
    part_idx: int,
    staff_idx: int,
    staff_id: str,
    meas_num: int,
    voice_idx: int,
    pred_events: Sequence[Event],
    gt_events: Sequence[Event],
    start_seq: int,
    document_id: str,
    author: str,
) -> tuple[list[EditEvent], int]:
    """Borra los eventos leídos de la voz del compás, del último al primero, e inserta los de
    la verdad en orden. Del último al primero, ninguno es la primera nota de un acorde de dos o
    más notas cuando se borra, y cada inserción va al final: ninguna parte un acorde."""

    anchor_base = Anchor(
        part=part_idx,
        staff=staff_idx,
        measure=meas_num,
        voice=voice_idx,
        event_index=0,
        staff_id=staff_id,
    )
    edits: list[EditEvent] = []
    seq = start_seq
    for index in range(len(pred_events) - 1, -1, -1):
        target = pred_events[index]
        edits.append(
            _make_edit(
                document_id=document_id,
                seq=seq,
                anchor=replace(anchor_base, event_index=index),
                op=EditOp.DELETE_EVENT,
                author=author,
                before={
                    "kind": target.kind.value,
                    "pitch": target.pitch,
                    "duration_beats": target.duration_beats,
                },
                after=None,
            )
        )
        seq += 1
    for index, g in enumerate(gt_events):
        edits.append(
            _make_edit(
                document_id=document_id,
                seq=seq,
                anchor=replace(anchor_base, event_index=index),
                op=EditOp.INSERT_EVENT,
                author=author,
                before=None,
                after=_insert_after(g),
            )
        )
        seq += 1
    return edits, seq


class InvalidDerivedEdit(ValueError):
    """Una edición derivada que la API rechazaría (`POST /sessions/{id}/edits`)."""


def check_edit(score: ScoreIR, edit: EditEvent) -> None:
    """Valida `edit` sobre el estado `score` como la API: su `before` (el de `append_edit`) y su
    `after` (`validate_after`, ADR-0017). Lanza `InvalidDerivedEdit` si la rechazaría."""

    try:
        _check_before(score, edit)
        validate_after(score, edit.anchor, edit.op, edit.after)
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise InvalidDerivedEdit(f"{edit.op.value} en {edit.anchor.sort_key()}: {exc}") from exc


def replay_edits(score: ScoreIR, edits: Iterable[EditEvent]) -> ScoreIR:
    """Aplica `edits` en orden validando cada una sobre su estado base, como la API.

    A diferencia de `materialize`, que solo aplica, lanza `InvalidDerivedEdit` en la primera
    edición que la API rechazaría (#456).
    """

    state = score
    for edit in sorted(edits, key=lambda event: event.seq):
        check_edit(state, edit)
        try:
            state = apply_edit(state, edit)
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise InvalidDerivedEdit(
                f"{edit.op.value} en {edit.anchor.sort_key()}: no se aplica: {exc}"
            ) from exc
    return state


def _check_before(score: ScoreIR, edit: EditEvent) -> None:
    """El `before` de la edición, si lo lleva, coincide con el estado (como `append_edit`)."""

    before = edit.before
    if not before or edit.op is EditOp.INSERT_EVENT:
        return
    anchor = edit.anchor
    staff = score.parts[anchor.part].staves[anchor.staff]
    measure = next((m for m in staff.measures if m.number == anchor.measure), None)
    if measure is None:
        raise ValueError(f"compás inexistente: {anchor.measure}")
    if edit.op is EditOp.SET_CLEF:
        raw = before.get("clef")
        expected = None if raw is None else Clef.from_primitive(raw)
        if measure.clef != expected:
            raise ValueError(f"before de clave no coincide: {measure.clef} frente a {expected}")
        return
    if edit.op is EditOp.SET_KEY:
        raw = before.get("key_signature")
        expected_key = None if raw is None else KeySignature.from_primitive(raw)
        if measure.key_signature != expected_key:
            raise ValueError(
                f"before de armadura no coincide: {measure.key_signature} frente a {expected_key}"
            )
        return
    events = [e for e in measure.events if e.voice == anchor.voice]
    if anchor.event_index >= len(events):
        raise IndexError(f"ancla fuera de rango en el compás {measure.number}")
    target = events[anchor.event_index]
    if "pitch" in before and before["pitch"] != target.pitch:
        raise ValueError(f"before de pitch no coincide: {target.pitch} frente a {before['pitch']}")
    if "duration_beats" in before:
        raw_dur = before["duration_beats"]
        expected_dur = None if raw_dur is None else Fraction(str(raw_dur))
        if target.duration_beats != expected_dur:
            raise ValueError(
                f"before de duration_beats no coincide: {target.duration_beats} frente a "
                f"{expected_dur}"
            )
    if "kind" in before and before["kind"] != target.kind.value:
        raise ValueError(
            f"before de kind no coincide: {target.kind.value} frente a {before['kind']}"
        )
    if "accidental" in before:
        actual = (snapshot_before(score, anchor, EditOp.SET_ACCIDENTAL) or {}).get("accidental")
        if normalize_accidental(before["accidental"]) != normalize_accidental(actual):
            raise ValueError(
                f"before de accidental no coincide: {actual} frente a {before['accidental']}"
            )


def is_structurally_equal(
    score_a: ScoreIR,
    score_b: ScoreIR,
    *,
    compare_time_signatures: bool = False,
) -> bool:
    """Verifica si dos ScoreIR son musicalmente idénticos a nivel de compases y eventos."""
    if len(score_a.parts) != len(score_b.parts):
        return False
    for part_a, part_b in zip(score_a.parts, score_b.parts, strict=True):
        if len(part_a.staves) != len(part_b.staves):
            return False
        for staff_a, staff_b in zip(part_a.staves, part_b.staves, strict=True):
            if len(staff_a.measures) != len(staff_b.measures):
                return False
            for m_a, m_b in zip(staff_a.measures, staff_b.measures, strict=True):
                if m_a.clef != m_b.clef:
                    return False
                if m_a.key_signature != m_b.key_signature:
                    return False
                if compare_time_signatures and m_a.time_signature != m_b.time_signature:
                    return False
                if len(m_a.events) != len(m_b.events):
                    return False
                for ev_a, ev_b in zip(m_a.events, m_b.events, strict=True):
                    if (
                        ev_a.kind != ev_b.kind
                        or ev_a.voice != ev_b.voice
                        or ev_a.pitch != ev_b.pitch
                        or ev_a.duration_beats != ev_b.duration_beats
                        or ev_a.tie != ev_b.tie
                        or ev_a.is_chord != ev_b.is_chord
                        or ev_a.hidden != ev_b.hidden
                    ):
                        return False
    return True
