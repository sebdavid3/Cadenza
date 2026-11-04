"""Ediciones de las marcas de notación: validación, estado previo y proyección (ADR-0039, #214).

Cuatro operaciones de tipo «fijar», como `SetPitch`: el servidor guarda en `before` el estado que
sustituyen (`snapshot_mark_before`) y la compensatoria intercambia `before` y `after`
(`create_inverse_edit`), de modo que deshacer es exacto (ADR-0007, ADR-0017).

- `SetNoteMarks`, sobre el evento del ancla: ``{"articulations": [...], "fermata": bool}``.
- `SetDynamic`, sobre el compás del ancla: ``{"offset_beats": "1/2", "mark": "mf" | None}``.
- `SetSlur` y `SetWedge`, sobre la parte del ancla: ``{"number": n, "start": ..., "stop": ...}``.
  Con los dos extremos crean la marca (el `number` debe estar libre en la parte); con los dos a
  None la quitan entera, sus dos extremos o el que quede (un huérfano, ADR-0031 §5). Un solo
  extremo solo lo escribe la compensatoria al deshacer la limpieza de un huérfano: de un cliente
  se rechaza. El ancla es el inicio (o, si no lo hay, el fin): la ligadura en su evento, el
  regulador en su compás.

Ninguna mueve un evento: el `event_index` de las anclas no cambia (ADR-0002, ADR-0011).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import replace
from fractions import Fraction
from typing import Any, Final

from .anchor import Anchor, EventKind
from .edit import EditEvent, EditOp
from .edit_errors import InvalidEditPayload
from .notation_marks import (
    Articulation,
    Dynamic,
    DynamicMark,
    Slur,
    SlurType,
    Wedge,
    WedgeType,
)
from .score import Event, Measure, Part, ScoreIR, Staff
from .timing import compute_timing_map

# Divisiones por negra con que exporta music21 (ADR-0031): una posición que no cabe en ellas no
# vuelve exacta del MusicXML.
EXPORT_DIVISIONS: Final[int] = 10080

_NOTE_MARK_KEYS: Final[frozenset[str]] = frozenset({"articulations", "fermata"})
_DYNAMIC_KEYS: Final[frozenset[str]] = frozenset({"offset_beats", "mark"})
_SPAN_KEYS: Final[frozenset[str]] = frozenset({"number", "start", "stop"})
_SLUR_SLOT_KEYS: Final[frozenset[str]] = frozenset({"staff", "measure", "voice", "event_index"})
_WEDGE_STOP_KEYS: Final[frozenset[str]] = frozenset({"staff", "measure", "offset_beats"})
_WEDGE_START_KEYS: Final[frozenset[str]] = _WEDGE_STOP_KEYS | {"type"}
_ARTICULATIONS: Final[frozenset[str]] = frozenset(a.value for a in Articulation)
_DYNAMICS: Final[frozenset[str]] = frozenset(d.value for d in DynamicMark)
_WEDGE_KINDS: Final[frozenset[str]] = frozenset(
    {WedgeType.CRESCENDO.value, WedgeType.DIMINUENDO.value}
)

# Un extremo de ligadura: pentagrama, compás, voz y posición en la voz.
SlurSlot = tuple[int, int, int, int]
# Un extremo de regulador: pentagrama, compás, posición en negras y tipo.
WedgeSlot = tuple[int, int, Fraction, WedgeType]


# --- Localizar ---------------------------------------------------------------------------


def _part(score: ScoreIR, anchor: Anchor) -> Part:
    if anchor.part >= len(score.parts):
        raise IndexError(f"parte fuera de rango: {anchor.part}")
    return score.parts[anchor.part]


def _find_measure(part: Part, staff: int, number: int) -> Measure | None:
    if staff >= len(part.staves):
        return None
    return next((m for m in part.staves[staff].measures if m.number == number), None)


def _anchor_measure(score: ScoreIR, anchor: Anchor) -> Measure:
    part = _part(score, anchor)
    if anchor.staff >= len(part.staves):
        raise IndexError(f"pentagrama fuera de rango: {anchor.staff}")
    measure = _find_measure(part, anchor.staff, anchor.measure)
    if measure is None:
        raise IndexError(f"compás inexistente: {anchor.measure}")
    return measure


def _voice_events(measure: Measure, voice: int) -> list[Event]:
    return [event for event in measure.events if event.voice == voice]


def _anchor_event(score: ScoreIR, anchor: Anchor) -> Event:
    events = _voice_events(_anchor_measure(score, anchor), anchor.voice)
    if anchor.event_index >= len(events):
        raise IndexError(
            f"anchor {anchor.sort_key()} apunta a un evento inexistente del compás {anchor.measure}"
        )
    return events[anchor.event_index]


# --- Formas --------------------------------------------------------------------------------


def _mapping(op: EditOp, value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidEditPayload(f"{op.value} requiere un objeto 'after'")
    return value


def _exact_keys(what: str, value: Mapping[str, Any], keys: frozenset[str]) -> None:
    missing = sorted(keys.difference(value.keys()))
    if missing:
        raise InvalidEditPayload(f"{what} requiere {', '.join(missing)}")
    unknown = sorted(set(value.keys()).difference(keys))
    if unknown:
        raise InvalidEditPayload(
            f"{what} no admite {', '.join(unknown)} (campos: {', '.join(sorted(keys))})"
        )


def _index(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidEditPayload(f"'{name}' debe ser un entero >= 0: {value!r}")
    return value


def _number(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidEditPayload(f"'number' debe ser un entero >= 1: {value!r}")
    return value


def parse_offset(value: object) -> Fraction:
    """Posición en negras desde el inicio del compás: un número o una fracción en texto, >= 0 y
    exacta en las divisiones de la exportación. Lanza `InvalidEditPayload` si no lo es."""

    if isinstance(value, bool) or not isinstance(value, int | float | str | Fraction):
        raise InvalidEditPayload(f"posición no válida: {value!r}")
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidEditPayload(f"posición no válida: {value!r}")
    try:
        offset = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as exc:
        raise InvalidEditPayload(f"posición no válida: {value!r}") from exc
    if offset < 0:
        raise InvalidEditPayload(f"la posición no puede ser negativa: {value!r}")
    if (offset * EXPORT_DIVISIONS).denominator != 1:
        raise InvalidEditPayload(
            f"posición no representable: {value!r} (debe caber en {EXPORT_DIVISIONS} "
            "divisiones por negra, p. ej. '1/2', '1/3', '3/4')"
        )
    return offset


def _measure_spans(score: ScoreIR) -> dict[int, tuple[Fraction, Fraction]]:
    """Inicio y duración en negras de cada compás, como los reproduce la vista (`TimingMap`)."""

    timing = compute_timing_map(score)
    numbers = sorted(timing.measure_offsets)
    spans: dict[int, tuple[Fraction, Fraction]] = {}
    for index, number in enumerate(numbers):
        start = timing.measure_offsets[number]
        end = (
            timing.measure_offsets[numbers[index + 1]]
            if index + 1 < len(numbers)
            else timing.total_beats
        )
        spans[number] = (start, end - start)
    return spans


def _check_inside(
    spans: dict[int, tuple[Fraction, Fraction]], measure: int, offset: Fraction
) -> None:
    length = spans.get(measure, (Fraction(0), Fraction(0)))[1]
    if offset > length:
        raise InvalidEditPayload(
            f"la posición {offset} queda fuera del compás {measure}, de {length} negras"
        )


# --- SetNoteMarks ------------------------------------------------------------------------


def _check_note_marks(score: ScoreIR, anchor: Anchor, after: object) -> None:
    target = _anchor_event(score, anchor)
    payload = _mapping(EditOp.SET_NOTE_MARKS, after)
    _exact_keys("SetNoteMarks", payload, _NOTE_MARK_KEYS)
    articulations = payload["articulations"]
    if not (
        isinstance(articulations, list | tuple)
        and all(isinstance(a, str) and a in _ARTICULATIONS for a in articulations)
    ):
        raise InvalidEditPayload(
            f"'articulations' debe ser una lista de {', '.join(sorted(_ARTICULATIONS))}: "
            f"{articulations!r}"
        )
    if len(set(articulations)) != len(articulations):
        raise InvalidEditPayload(f"'articulations' repite una articulación: {articulations!r}")
    if not isinstance(payload["fermata"], bool):
        raise InvalidEditPayload(f"'fermata' debe ser booleano: {payload['fermata']!r}")
    if target.hidden:
        raise InvalidEditPayload("un silencio invisible no lleva marcas")
    if target.kind is EventKind.REST:
        if articulations:
            raise InvalidEditPayload("un silencio solo lleva calderón, no articulaciones")
        return
    if target.kind is not EventKind.NOTE:
        raise InvalidEditPayload(f"SetNoteMarks no se aplica a '{target.kind.value}'")
    if target.is_chord:
        raise InvalidEditPayload("en un acorde, las marcas van en su primera nota (ADR-0031)")


# --- SetDynamic --------------------------------------------------------------------------


def _check_dynamic(score: ScoreIR, anchor: Anchor, after: object) -> None:
    measure = _anchor_measure(score, anchor)
    payload = _mapping(EditOp.SET_DYNAMIC, after)
    _exact_keys("SetDynamic", payload, _DYNAMIC_KEYS)
    offset = parse_offset(payload["offset_beats"])
    _check_inside(_measure_spans(score), measure.number, offset)
    mark = payload["mark"]
    if mark is not None and (not isinstance(mark, str) or mark not in _DYNAMICS):
        raise InvalidEditPayload(
            f"dinámica no válida: {mark!r} (admitidas: null, {', '.join(sorted(_DYNAMICS))})"
        )
    if sum(1 for dynamic in measure.dynamics if dynamic.offset_beats == offset) > 1:
        raise InvalidEditPayload(
            f"el compás {measure.number} tiene varias dinámicas en la posición {offset}"
        )


# --- SetSlur -----------------------------------------------------------------------------


def _slur_ends(part: Part, number: int) -> dict[SlurType, SlurSlot]:
    ends: dict[SlurType, SlurSlot] = {}
    for staff_index, staff in enumerate(part.staves):
        for measure in staff.measures:
            counters: dict[int, int] = {}
            for event in measure.events:
                position = counters.get(event.voice, 0)
                counters[event.voice] = position + 1
                for slur in event.slurs:
                    if slur.number == number:
                        ends.setdefault(
                            slur.type, (staff_index, measure.number, event.voice, position)
                        )
    return ends


def _slur_slot_primitive(slot: SlurSlot | None) -> dict[str, int] | None:
    if slot is None:
        return None
    staff, measure, voice, event_index = slot
    return {"staff": staff, "measure": measure, "voice": voice, "event_index": event_index}


def _parse_slur_slot(part: Part, value: object) -> tuple[SlurSlot, Event]:
    if not isinstance(value, Mapping):
        raise InvalidEditPayload(f"extremo de ligadura no válido: {value!r}")
    _exact_keys("un extremo de ligadura", value, _SLUR_SLOT_KEYS)
    slot = (
        _index("staff", value["staff"]),
        _index("measure", value["measure"]),
        _index("voice", value["voice"]),
        _index("event_index", value["event_index"]),
    )
    measure = _find_measure(part, slot[0], slot[1])
    events = [] if measure is None else _voice_events(measure, slot[2])
    if slot[3] >= len(events):
        raise InvalidEditPayload(f"el extremo de ligadura no apunta a un evento: {dict(value)!r}")
    event = events[slot[3]]
    if event.kind is not EventKind.NOTE:
        raise InvalidEditPayload("una ligadura de expresión une notas, no silencios")
    if event.is_chord:
        raise InvalidEditPayload("en un acorde, la ligadura va en su primera nota (ADR-0031)")
    return slot, event


def _onsets(score: ScoreIR, part_index: int) -> dict[SlurSlot, Fraction]:
    return {
        (t.anchor.staff, t.anchor.measure, t.anchor.voice, t.anchor.event_index): t.offset_beats
        for t in compute_timing_map(score).events
        if t.anchor.part == part_index
    }


def _slur_precedes(onsets: dict[SlurSlot, Fraction], start: SlurSlot, stop: SlurSlot) -> bool:
    """El inicio va antes que el fin: antes en el tiempo o, a la vez en la misma voz y compás
    (una nota de adorno y su nota), antes en la voz."""

    first, second = onsets.get(start), onsets.get(stop)
    if first is None or second is None:
        return False
    if first != second:
        return first < second
    return start[:3] == stop[:3] and start[3] < stop[3]


def _check_anchor_slot(anchor: Anchor, slot: SlurSlot, what: str) -> None:
    if (anchor.staff, anchor.measure, anchor.voice, anchor.event_index) != slot:
        raise InvalidEditPayload(f"el ancla debe ser el evento {what}")


def _check_slur(score: ScoreIR, anchor: Anchor, after: object) -> None:
    part = _part(score, anchor)
    payload = _mapping(EditOp.SET_SLUR, after)
    _exact_keys("SetSlur", payload, _SPAN_KEYS)
    number = _number(payload["number"])
    start, stop = payload["start"], payload["stop"]
    ends = _slur_ends(part, number)
    if start is None and stop is None:
        if not ends:
            raise InvalidEditPayload(f"la parte no tiene la ligadura de expresión {number}")
        first = ends.get(SlurType.START) or ends[SlurType.STOP]
        _check_anchor_slot(anchor, first, "del inicio de la ligadura (o de su fin, si no lo hay)")
        return
    if start is None or stop is None:
        raise InvalidEditPayload("una ligadura de expresión se crea con su inicio y su fin")
    if ends:
        raise InvalidEditPayload(f"la parte ya tiene la ligadura de expresión {number}")
    start_slot, _ = _parse_slur_slot(part, start)
    stop_slot, _ = _parse_slur_slot(part, stop)
    if not _slur_precedes(_onsets(score, anchor.part), start_slot, stop_slot):
        raise InvalidEditPayload("el fin de la ligadura debe ir después de su inicio")
    _check_anchor_slot(anchor, start_slot, "del inicio de la ligadura")


# --- SetWedge ----------------------------------------------------------------------------


def _wedge_ends(part: Part, number: int) -> dict[str, WedgeSlot]:
    ends: dict[str, WedgeSlot] = {}
    for staff_index, staff in enumerate(part.staves):
        for measure in staff.measures:
            for wedge in measure.wedges:
                if wedge.number == number:
                    role = "stop" if wedge.type is WedgeType.STOP else "start"
                    ends.setdefault(
                        role, (staff_index, measure.number, wedge.offset_beats, wedge.type)
                    )
    return ends


def _wedge_slot_primitive(slot: WedgeSlot | None, *, start: bool) -> dict[str, Any] | None:
    if slot is None:
        return None
    staff, measure, offset, kind = slot
    primitive: dict[str, Any] = {"staff": staff, "measure": measure, "offset_beats": str(offset)}
    if start:
        primitive["type"] = kind.value
    return primitive


def _parse_wedge_slot(
    part: Part,
    spans: dict[int, tuple[Fraction, Fraction]],
    value: object,
    *,
    start: bool,
) -> WedgeSlot:
    what = "el inicio de un regulador" if start else "el fin de un regulador"
    if not isinstance(value, Mapping):
        raise InvalidEditPayload(f"{what} no es válido: {value!r}")
    _exact_keys(what, value, _WEDGE_START_KEYS if start else _WEDGE_STOP_KEYS)
    staff = _index("staff", value["staff"])
    number = _index("measure", value["measure"])
    if _find_measure(part, staff, number) is None:
        raise InvalidEditPayload(f"{what} no está en un compás de la parte: {dict(value)!r}")
    offset = parse_offset(value["offset_beats"])
    _check_inside(spans, number, offset)
    kind = WedgeType.STOP
    if start:
        raw = value["type"]
        if not isinstance(raw, str) or raw not in _WEDGE_KINDS:
            raise InvalidEditPayload(f"tipo de regulador no válido: {raw!r}")
        kind = WedgeType(raw)
    return (staff, number, offset, kind)


def _check_wedge(score: ScoreIR, anchor: Anchor, after: object) -> None:
    part = _part(score, anchor)
    payload = _mapping(EditOp.SET_WEDGE, after)
    _exact_keys("SetWedge", payload, _SPAN_KEYS)
    number = _number(payload["number"])
    start, stop = payload["start"], payload["stop"]
    ends = _wedge_ends(part, number)
    if start is None and stop is None:
        if not ends:
            raise InvalidEditPayload(f"la parte no tiene el regulador {number}")
        first = ends.get("start") or ends["stop"]
        if (anchor.staff, anchor.measure) != first[:2]:
            raise InvalidEditPayload(
                "el ancla debe estar en el compás del inicio del regulador (o de su fin)"
            )
        return
    if start is None or stop is None:
        raise InvalidEditPayload("un regulador se crea con su inicio y su fin")
    if ends:
        raise InvalidEditPayload(f"la parte ya tiene el regulador {number}")
    spans = _measure_spans(score)
    start_slot = _parse_wedge_slot(part, spans, start, start=True)
    stop_slot = _parse_wedge_slot(part, spans, stop, start=False)

    def moment(slot: WedgeSlot) -> Fraction:
        return spans.get(slot[1], (Fraction(0), Fraction(0)))[0] + slot[2]

    if moment(stop_slot) <= moment(start_slot):
        raise InvalidEditPayload("el fin del regulador debe ir después de su inicio")
    if (anchor.staff, anchor.measure) != start_slot[:2]:
        raise InvalidEditPayload("el ancla debe estar en el compás del inicio del regulador")


# --- API del módulo ---------------------------------------------------------------------


_CHECKS: Final[dict[EditOp, Callable[[ScoreIR, Anchor, object], None]]] = {
    EditOp.SET_NOTE_MARKS: _check_note_marks,
    EditOp.SET_DYNAMIC: _check_dynamic,
    EditOp.SET_SLUR: _check_slur,
    EditOp.SET_WEDGE: _check_wedge,
}


def validate_mark_after(
    score: ScoreIR, anchor: Anchor, op: EditOp, after: Mapping[str, Any] | None
) -> None:
    """Comprueba el `after` de una operación de marcas sobre el estado `score` (ADR-0039).

    Lanza `InvalidEditPayload` si no es válido e `IndexError` si el ancla no apunta a lo que
    la operación necesita (el evento de `SetNoteMarks`, el compás de `SetDynamic`, la parte).
    """

    _CHECKS[op](score, anchor, after)


def snapshot_mark_before(
    score: ScoreIR, anchor: Anchor, op: EditOp, after: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Estado que sustituye la edición, en la forma de su `after`: su compensatoria lo vuelve a
    fijar. Se calcula sobre un `after` ya validado."""

    if op is EditOp.SET_NOTE_MARKS:
        target = _anchor_event(score, anchor)
        return {
            "articulations": [a.value for a in target.articulations],
            "fermata": target.fermata,
        }
    payload = _mapping(op, after)
    if op is EditOp.SET_DYNAMIC:
        offset = parse_offset(payload["offset_beats"])
        mark = next(
            (
                d.mark.value
                for d in _anchor_measure(score, anchor).dynamics
                if d.offset_beats == offset
            ),
            None,
        )
        return {"offset_beats": str(offset), "mark": mark}
    number = _number(payload["number"])
    part = _part(score, anchor)
    if op is EditOp.SET_SLUR:
        slurs = _slur_ends(part, number)
        return {
            "number": number,
            "start": _slur_slot_primitive(slurs.get(SlurType.START)),
            "stop": _slur_slot_primitive(slurs.get(SlurType.STOP)),
        }
    if op is EditOp.SET_WEDGE:
        wedges = _wedge_ends(part, number)
        return {
            "number": number,
            "start": _wedge_slot_primitive(wedges.get("start"), start=True),
            "stop": _wedge_slot_primitive(wedges.get("stop"), start=False),
        }
    raise ValueError(f"operación que no es de marcas: {op.value}")


def has_complete_mark_before(op: EditOp, before: Mapping[str, Any]) -> bool:
    """Si `before` basta para que la compensatoria devuelva el estado exacto."""

    keys = set(before.keys())
    if op is EditOp.SET_NOTE_MARKS:
        return keys >= _NOTE_MARK_KEYS
    if op is EditOp.SET_DYNAMIC:
        return keys >= _DYNAMIC_KEYS
    return keys >= _SPAN_KEYS


# --- Proyección --------------------------------------------------------------------------


def _replace_measure(
    score: ScoreIR, anchor: Anchor, change: Callable[[Measure], Measure]
) -> ScoreIR:
    part = _part(score, anchor)
    if anchor.staff >= len(part.staves):
        raise IndexError(f"pentagrama fuera de rango: {anchor.staff}")
    staff = part.staves[anchor.staff]
    measures = list(staff.measures)
    for index, measure in enumerate(measures):
        if measure.number == anchor.measure:
            measures[index] = change(measure)
            break
    else:
        raise IndexError(f"compás inexistente: {anchor.measure}")
    staves = list(part.staves)
    staves[anchor.staff] = replace(staff, measures=tuple(measures))
    return _replace_part(score, anchor.part, replace(part, staves=tuple(staves)))


def _replace_part(score: ScoreIR, index: int, part: Part) -> ScoreIR:
    parts = list(score.parts)
    parts[index] = part
    return replace(score, parts=tuple(parts))


def _map_measures(part: Part, change: Callable[[int, Measure], Measure]) -> Part:
    staves: list[Staff] = [
        replace(staff, measures=tuple(change(index, measure) for measure in staff.measures))
        for index, staff in enumerate(part.staves)
    ]
    return replace(part, staves=tuple(staves))


def _apply_note_marks(score: ScoreIR, anchor: Anchor, after: Mapping[str, Any]) -> ScoreIR:
    def change(measure: Measure) -> Measure:
        events = list(measure.events)
        positions = [i for i, event in enumerate(events) if event.voice == anchor.voice]
        if anchor.event_index >= len(positions):
            raise IndexError(
                f"anchor {anchor.sort_key()} apunta a un evento inexistente del compás "
                f"{measure.number}"
            )
        position = positions[anchor.event_index]
        events[position] = replace(
            events[position],
            articulations=tuple(Articulation(str(a)) for a in after["articulations"]),
            fermata=after["fermata"] is True,
        )
        return replace(measure, events=tuple(events))

    return _replace_measure(score, anchor, change)


def _apply_dynamic(score: ScoreIR, anchor: Anchor, after: Mapping[str, Any]) -> ScoreIR:
    offset = Fraction(str(after["offset_beats"]))
    mark = after["mark"]

    def change(measure: Measure) -> Measure:
        kept = [dynamic for dynamic in measure.dynamics if dynamic.offset_beats != offset]
        if mark is not None:
            kept.append(Dynamic(DynamicMark(str(mark)), offset))
        return replace(measure, dynamics=tuple(kept))

    return _replace_measure(score, anchor, change)


def _apply_slur(score: ScoreIR, anchor: Anchor, after: Mapping[str, Any]) -> ScoreIR:
    number = int(after["number"])
    wanted: dict[SlurSlot, SlurType] = {}
    for kind, raw in ((SlurType.START, after["start"]), (SlurType.STOP, after["stop"])):
        if raw is not None:
            slot = (
                int(raw["staff"]),
                int(raw["measure"]),
                int(raw["voice"]),
                int(raw["event_index"]),
            )
            wanted[slot] = kind
    placed: set[SlurSlot] = set()

    def change(staff_index: int, measure: Measure) -> Measure:
        counters: dict[int, int] = {}
        events: list[Event] = []
        for event in measure.events:
            position = counters.get(event.voice, 0)
            counters[event.voice] = position + 1
            slot = (staff_index, measure.number, event.voice, position)
            slurs = [slur for slur in event.slurs if slur.number != number]
            if slot in wanted:
                slurs.append(Slur(wanted[slot], number))
                placed.add(slot)
            events.append(
                replace(event, slurs=tuple(slurs)) if tuple(slurs) != event.slurs else event
            )
        return replace(measure, events=tuple(events))

    part = _map_measures(_part(score, anchor), change)
    missing = set(wanted) - placed
    if missing:
        raise IndexError(f"extremo de ligadura sin evento: {sorted(missing)}")
    return _replace_part(score, anchor.part, part)


def _apply_wedge(score: ScoreIR, anchor: Anchor, after: Mapping[str, Any]) -> ScoreIR:
    number = int(after["number"])
    wanted: dict[tuple[int, int], list[Wedge]] = {}
    for raw, start in ((after["start"], True), (after["stop"], False)):
        if raw is not None:
            kind = WedgeType(str(raw["type"])) if start else WedgeType.STOP
            wedge = Wedge(kind, number, Fraction(str(raw["offset_beats"])))
            wanted.setdefault((int(raw["staff"]), int(raw["measure"])), []).append(wedge)
    placed: set[tuple[int, int]] = set()

    def change(staff_index: int, measure: Measure) -> Measure:
        wedges = [wedge for wedge in measure.wedges if wedge.number != number]
        extra = wanted.get((staff_index, measure.number))
        if extra:
            wedges.extend(extra)
            placed.add((staff_index, measure.number))
        if len(wedges) == len(measure.wedges) and not extra:
            return measure
        return replace(measure, wedges=tuple(wedges))

    part = _map_measures(_part(score, anchor), change)
    missing = set(wanted) - placed
    if missing:
        raise IndexError(f"extremo de regulador sin compás: {sorted(missing)}")
    return _replace_part(score, anchor.part, part)


def apply_mark_edit(score: ScoreIR, edit: EditEvent) -> ScoreIR:
    """Aplica una edición de marcas; no muta `score`. `ValueError` si su `after` no se entiende,
    `IndexError` si no encuentra lo que fija."""

    after = edit.after
    if after is None:
        raise ValueError(f"{edit.op.value} sin 'after' no se puede aplicar")
    try:
        if edit.op is EditOp.SET_NOTE_MARKS:
            return _apply_note_marks(score, edit.anchor, after)
        if edit.op is EditOp.SET_DYNAMIC:
            return _apply_dynamic(score, edit.anchor, after)
        if edit.op is EditOp.SET_SLUR:
            return _apply_slur(score, edit.anchor, after)
        if edit.op is EditOp.SET_WEDGE:
            return _apply_wedge(score, edit.anchor, after)
    except (KeyError, TypeError) as exc:
        raise ValueError(f"'after' de {edit.op.value} no válido: {exc!r}") from exc
    raise ValueError(f"operación que no es de marcas: {edit.op.value}")
