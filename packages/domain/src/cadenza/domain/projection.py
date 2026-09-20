"""Proyección del log de ediciones sobre el `ScoreIR` crudo (ADR-0007).

El estado actual de un documento es el resultado de **aplicar la secuencia de
`EditEvent`** sobre el `ScoreIR` original. Esta proyección es pura: no muta el
`ScoreIR` de entrada y es determinista respecto de `seq`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from fractions import Fraction
from typing import Any

from .anchor import Anchor, EventKind
from .edit import EditEvent, EditOp
from .score import Event, Measure, ScoreIR


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


def _apply_to_measure(measure: Measure, anchor: Anchor, edit: EditEvent) -> Measure:
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

    if edit.op in (EditOp.SET_PITCH, EditOp.SET_ACCIDENTAL):
        events[position] = replace(target, pitch=_value(edit.after, "pitch"))
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
        raise UnsupportedEditOpError(f"operación no proyectable: {edit.op.value}")

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
