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
    elif edit.op is EditOp.INSERT_EVENT:
        events.insert(
            position,
            Event(
                kind=EventKind(_value(edit.after, "kind") or EventKind.NOTE.value),
                voice=anchor.voice,
                pitch=_value(edit.after, "pitch"),
                duration_beats=_fraction(_value(edit.after, "duration_beats")),
            ),
        )
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
