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
from typing import Any, Final

from cadenza.domain import (
    Anchor,
    EditEvent,
    EditOp,
    Event,
    EventKind,
    ScoreIR,
)

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
            if current_target.pitch != g.pitch:
                p_let, p_acc, p_oct = split_pitch(current_target.pitch)
                g_let, g_acc, g_oct = split_pitch(g.pitch)
                if p_let and g_let and p_let == g_let and p_oct == g_oct:
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
            edits.append(
                _make_edit(
                    document_id=document_id,
                    seq=seq,
                    anchor=anchor,
                    op=EditOp.DELETE_EVENT,
                    author=author,
                    before=before_dict,
                    after=None,
                )
            )
            seq += 1
            del current_events[curr_idx]

        elif p is None and g is not None:
            # Inserción
            anchor = replace(anchor_base, event_index=curr_idx)
            after_dict = {
                "kind": g.kind.value,
                "pitch": g.pitch,
                "duration_beats": g.duration_beats,
                "tie": g.tie.value if g.tie is not None else None,
                "is_chord": g.is_chord,
            }
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
    Garantiza formalmente que `materialize(predicted, edits)` genera eventos y atributos
    idénticos a los del `ground_truth`.
    """
    edits: list[EditEvent] = []
    seq = base_seq

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

                # 3. Eventos por voz
                voices = sorted(
                    {e.voice for e in pred_meas.events} | {e.voice for e in gt_meas.events}
                )
                if not voices:
                    voices = [0]

                for v in voices:
                    p_events = [e for e in pred_meas.events if e.voice == v]
                    g_events = [e for e in gt_meas.events if e.voice == v]
                    v_edits, seq = _derive_voice_edits(
                        part_idx=part_idx,
                        staff_idx=staff_idx,
                        staff_id=pred_staff.id,
                        meas_num=pred_meas.number,
                        voice_idx=v,
                        pred_events=p_events,
                        gt_events=g_events,
                        start_seq=seq,
                        document_id=document_id,
                        author=author,
                    )
                    edits.extend(v_edits)

    return edits


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
                    ):
                        return False
    return True
