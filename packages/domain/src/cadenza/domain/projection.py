"""Proyección del log de ediciones sobre el `ScoreIR` crudo (ADR-0007).

El estado actual de un documento es el resultado de **aplicar la secuencia de
`EditEvent`** sobre el `ScoreIR` original. Esta proyección es pura: no muta el
`ScoreIR` de entrada y es determinista respecto de `seq`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import replace
from fractions import Fraction
from typing import Any, Final

from .anchor import Anchor, EventKind
from .clef import Clef
from .edit import EditEvent, EditOp
from .key_signature import KeySignature
from .score import Event, Measure, ScoreIR

_PITCH_RE: Final[re.Pattern[str]] = re.compile(r"^([A-Ga-g])(#{1,2}|b{1,2}|-{1,2}|x)?(-?\d+)$")

_ACCIDENTAL_MAP: Final[dict[str, str]] = {
    "": "",
    "natural": "",
    "n": "",
    "none": "",
    "#": "#",
    "sharp": "#",
    "##": "##",
    "x": "##",
    "double-sharp": "##",
    "doublesharp": "##",
    "b": "b",
    "-": "b",
    "flat": "b",
    "bb": "bb",
    "--": "bb",
    "double-flat": "bb",
    "doubleflat": "bb",
}


class UnsupportedEditOpError(ValueError):
    """La operación de edición no puede proyectarse sobre un `ScoreIR` de evento."""


def _value(payload: Mapping[str, Any] | None, key: str) -> Any:
    if payload is None:
        return None
    return payload.get(key)


def _fraction(value: object) -> Fraction | None:
    if value is None:
        return None
    if isinstance(value, Fraction):
        return value
    return Fraction(str(value))


def _extract_clef(payload: Mapping[str, Any] | None) -> Clef | None:
    if payload is None:
        return None
    raw = payload.get("clef")
    if raw is None and "sign" in payload:
        raw = payload
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
    raise ValueError(f"payload de clave no válido: {raw!r}")


def _extract_key_signature(payload: Mapping[str, Any] | None) -> KeySignature | None:
    if payload is None:
        return None
    raw = payload.get("key_signature")
    if raw is None:
        raw = payload.get("key")
    if raw is None and "fifths" in payload:
        raw = payload
    if raw is None:
        return None
    if isinstance(raw, KeySignature):
        return raw
    if isinstance(raw, Mapping):
        return KeySignature.from_primitive(raw)
    if isinstance(raw, int):
        return KeySignature(fifths=raw)
    if isinstance(raw, str):
        return KeySignature(fifths=int(raw))
    raise ValueError(f"payload de armadura no válido: {raw!r}")


def _apply_accidental(pitch: str | None, payload: Mapping[str, Any] | None) -> str:
    if pitch is None:
        raise ValueError("cannot apply SetAccidental to an event without pitch")
    match = _PITCH_RE.match(pitch.strip())
    if not match:
        raise ValueError(f"malformed pitch string: {pitch!r}")
    letter = match.group(1).upper()
    octave = match.group(3)

    if payload is None:
        new_acc = ""
    elif "accidental" in payload:
        raw_acc = payload["accidental"]
        new_acc = "" if raw_acc is None else str(raw_acc).strip()
    elif payload.get("pitch"):
        pitch_match = _PITCH_RE.match(str(payload["pitch"]).strip())
        new_acc = pitch_match.group(2) or "" if pitch_match else ""
    else:
        new_acc = ""

    normalized_acc = _ACCIDENTAL_MAP.get(new_acc.lower(), new_acc)
    return f"{letter}{normalized_acc}{octave}"


def _apply_to_measure(measure: Measure, anchor: Anchor, edit: EditEvent) -> Measure:
    if edit.op is EditOp.SET_CLEF:
        return replace(measure, clef=_extract_clef(edit.after))

    if edit.op is EditOp.SET_KEY:
        return replace(measure, key_signature=_extract_key_signature(edit.after))

    events = list(measure.events)
    voice_positions = [
        position for position, event in enumerate(events) if event.voice == anchor.voice
    ]

    if edit.op is EditOp.INSERT_EVENT:
        if anchor.event_index > len(voice_positions):
            raise IndexError(
                f"anchor {anchor.sort_key()} fuera de rango para compás {measure.number}"
            )
        if anchor.event_index == len(voice_positions):
            insert_pos = voice_positions[-1] + 1 if voice_positions else len(events)
        else:
            insert_pos = voice_positions[anchor.event_index]

        bbox_raw = _value(edit.after, "bbox")
        bbox = (
            (float(bbox_raw[0]), float(bbox_raw[1]), float(bbox_raw[2]), float(bbox_raw[3]))
            if bbox_raw is not None
            else None
        )
        conf_raw = _value(edit.after, "confidence")
        confidence = float(conf_raw) if conf_raw is not None else None

        events.insert(
            insert_pos,
            Event(
                kind=EventKind(_value(edit.after, "kind") or EventKind.NOTE.value),
                voice=anchor.voice,
                pitch=_value(edit.after, "pitch"),
                duration_beats=_fraction(_value(edit.after, "duration_beats")),
                bbox=bbox,
                confidence=confidence,
            ),
        )
        return replace(measure, events=tuple(events))

    if anchor.event_index >= len(voice_positions):
        raise IndexError(
            f"anchor {anchor.sort_key()} apunta a un evento inexistente del compás {measure.number}"
        )
    position = voice_positions[anchor.event_index]
    target = events[position]

    if edit.op is EditOp.SET_PITCH:
        events[position] = replace(target, pitch=_value(edit.after, "pitch"))
    elif edit.op is EditOp.SET_ACCIDENTAL:
        events[position] = replace(target, pitch=_apply_accidental(target.pitch, edit.after))
    elif edit.op is EditOp.SET_DURATION:
        events[position] = replace(
            target, duration_beats=_fraction(_value(edit.after, "duration_beats"))
        )
    elif edit.op is EditOp.DELETE_EVENT:
        del events[position]
    else:
        op_label = edit.op.value if hasattr(edit.op, "value") else str(edit.op)
        raise UnsupportedEditOpError(f"operación no proyectable: {op_label}")

    return replace(measure, events=tuple(events))


def apply_edit(score: ScoreIR, edit: EditEvent) -> ScoreIR:
    """Devuelve un nuevo `ScoreIR` con `edit` aplicado; el original no se muta."""

    anchor = edit.anchor
    if anchor.part >= len(score.parts):
        raise IndexError(f"parte fuera de rango: {anchor.part}")

    part = score.parts[anchor.part]
    if anchor.staff >= len(part.staves):
        raise IndexError(f"pentagrama fuera de rango: {anchor.staff}")

    staff = part.staves[anchor.staff]
    measures = list(staff.measures)
    for index, measure in enumerate(measures):
        if measure.number == anchor.measure:
            measures[index] = _apply_to_measure(measure, anchor, edit)
            break
    else:
        raise IndexError(f"compás inexistente: {anchor.measure}")

    new_staff = replace(staff, measures=tuple(measures))
    staves = list(part.staves)
    staves[anchor.staff] = new_staff
    new_part = replace(part, staves=tuple(staves))
    parts = list(score.parts)
    parts[anchor.part] = new_part
    return replace(score, parts=tuple(parts))


def materialize(score: ScoreIR, edits: Iterable[EditEvent]) -> ScoreIR:
    """Reconstruye el estado actual aplicando los eventos en orden de `seq`."""

    result = score
    for edit in sorted(edits, key=lambda event: event.seq):
        result = apply_edit(result, edit)
    return result


def origin_anchor(anchor: Anchor, at_seq: int, edits: Iterable[EditEvent]) -> Anchor | None:
    """Devuelve el ancla del mismo evento en el estado 0 (documento crudo), o None si fue insertado.

    Deshace la regla de desplazamiento (ADR-0011) recorriendo las ediciones relevantes
    en orden decreciente desde `at_seq` hasta 1.
    """
    if at_seq < 0:
        raise ValueError("at_seq must be >= 0")
    if at_seq == 0:
        return anchor

    relevant = [
        e
        for e in edits
        if 1 <= e.seq <= at_seq
        and e.anchor.part == anchor.part
        and e.anchor.staff == anchor.staff
        and e.anchor.measure == anchor.measure
        and e.anchor.voice == anchor.voice
    ]
    relevant.sort(key=lambda e: e.seq, reverse=True)

    pos = anchor.event_index
    for edit in relevant:
        if edit.op is EditOp.INSERT_EVENT:
            if pos == edit.anchor.event_index:
                return None
            if pos > edit.anchor.event_index:
                pos -= 1
        elif edit.op is EditOp.DELETE_EVENT:
            if pos >= edit.anchor.event_index:
                pos += 1

    return replace(anchor, event_index=pos)


def translate_anchor(
    anchor: Anchor,
    from_seq: int,
    to_seq: int,
    edits: Iterable[EditEvent],
) -> Anchor | None:
    """Traduce un ancla entre dos estados de la sesión (`from_seq` -> `to_seq`).

    Si el evento fue borrado entre ambos estados, devuelve None.
    Si el ancla fue insertada y se retrocede antes de su creación, devuelve None.
    """
    if from_seq < 0 or to_seq < 0:
        raise ValueError("from_seq and to_seq must be >= 0")
    if from_seq == to_seq:
        return anchor
    if to_seq == 0:
        return origin_anchor(anchor, from_seq, edits)

    if from_seq > to_seq:
        relevant = [
            e
            for e in edits
            if to_seq < e.seq <= from_seq
            and e.anchor.part == anchor.part
            and e.anchor.staff == anchor.staff
            and e.anchor.measure == anchor.measure
            and e.anchor.voice == anchor.voice
        ]
        relevant.sort(key=lambda e: e.seq, reverse=True)
        pos = anchor.event_index
        for edit in relevant:
            if edit.op is EditOp.INSERT_EVENT:
                if pos == edit.anchor.event_index:
                    return None
                if pos > edit.anchor.event_index:
                    pos -= 1
            elif edit.op is EditOp.DELETE_EVENT:
                if pos >= edit.anchor.event_index:
                    pos += 1
        return replace(anchor, event_index=pos)

    # from_seq < to_seq: avanzamos en el tiempo
    relevant = [
        e
        for e in edits
        if from_seq < e.seq <= to_seq
        and e.anchor.part == anchor.part
        and e.anchor.staff == anchor.staff
        and e.anchor.measure == anchor.measure
        and e.anchor.voice == anchor.voice
    ]
    relevant.sort(key=lambda e: e.seq)
    pos = anchor.event_index
    for edit in relevant:
        if edit.op is EditOp.INSERT_EVENT:
            if pos >= edit.anchor.event_index:
                pos += 1
        elif edit.op is EditOp.DELETE_EVENT:
            if pos == edit.anchor.event_index:
                return None
            if pos > edit.anchor.event_index:
                pos -= 1

    return replace(anchor, event_index=pos)
