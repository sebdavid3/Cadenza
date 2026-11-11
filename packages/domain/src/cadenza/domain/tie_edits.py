"""La ligadura de prolongación como edición: `SetTie` (ADR-0055, #312).

Una ligadura de prolongación son dos valores de `Event.tie`, uno en cada nota, que pueden estar
en compases distintos. `SetTie` los fija en una edición de tipo «fijar», anclada en la nota donde
empieza la ligadura:

    {"tie": t, "next": {"measure": m, "voice": v, "event_index": i, "tie": t2} | null}

Cada valor se lee como dos marcas: «llega una ligadura» (`stop`, `continue`) y «sale una
ligadura» (`start`, `continue`). Con `next`, la edición pone o quita la ligadura entre la nota del
ancla y la otra: solo cambian lo que sale de la primera y lo que llega a la segunda, las dos a la
vez. La otra nota es lo que sigue a la del ancla, como lo busca `tie.resolution` (ADR-0040 §10):
una nota del grupo siguiente de su voz, sin contar las notas de adorno, o, si su grupo es el
último de su voz en el compás, una del primer grupo de cualquier voz del compás siguiente de su
pentagrama. Poner exige la misma altura; quitar, no. Sin `next`, solo se quitan marcas de la nota
del ancla: una ligadura que no llega a ninguna nota o que llega sin salir de ninguna.

El servidor guarda en `before` los valores que había, con la misma forma, y la compensatoria
intercambia los dos (`create_inverse_edit`): deshacer es exacto. No mueve ningún evento.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, Final

from .anchor import Anchor, EventKind
from .chords import chord_bounds
from .edit_errors import InvalidEditPayload
from .score import Event, Measure, ScoreIR, Staff
from .tie import Tie

_TIE_KEYS: Final[frozenset[str]] = frozenset({"tie", "next"})
_NEXT_KEYS: Final[frozenset[str]] = frozenset({"measure", "voice", "event_index", "tie"})
_TIES: Final[dict[str, Tie]] = {tie.value: tie for tie in Tie}
_ARRIVES: Final[frozenset[Tie]] = frozenset({Tie.STOP, Tie.CONTINUE})
_LEAVES: Final[frozenset[Tie]] = frozenset({Tie.START, Tie.CONTINUE})
_PITCH: Final[re.Pattern[str]] = re.compile(r"^([A-Ga-g])(#{1,2}|b{1,2}|-{1,2}|x)?(-?\d+)$")
_ALTER: Final[dict[str, int]] = {
    "": 0,
    "#": 1,
    "##": 2,
    "x": 2,
    "b": -1,
    "bb": -2,
    "-": -1,
    "--": -2,
}

Place = tuple[int, int, int]
"""(número del compás, voz, índice del evento en la voz)."""


def _arrives(tie: Tie | None) -> bool:
    return tie in _ARRIVES


def _leaves(tie: Tie | None) -> bool:
    return tie in _LEAVES


def _value(tie: Tie | None) -> str | None:
    return None if tie is None else tie.value


def _pitch_key(pitch: str | None) -> tuple[str, int, int] | None:
    match = None if pitch is None else _PITCH.match(pitch.strip())
    if match is None:
        return None
    return match.group(1).upper(), _ALTER[match.group(2) or ""], int(match.group(3))


def same_pitch(a: Event, b: Event) -> bool:
    """Si dos notas tienen la misma altura escrita: letra, alteración y octava."""

    key = _pitch_key(a.pitch)
    return key is not None and key == _pitch_key(b.pitch)


# --- Leer el `after` ---------------------------------------------------------------------


def _parse_tie(value: object, where: str = "") -> Tie | None:
    if value is None:
        return None
    if isinstance(value, str) and value in _TIES:
        return _TIES[value]
    raise InvalidEditPayload(f"'tie' no válido{where}: {value!r} (start, continue, stop o null)")


def _parse_after(after: object) -> tuple[Tie | None, tuple[Place, Tie | None] | None]:
    if not isinstance(after, Mapping):
        raise InvalidEditPayload("SetTie requiere un objeto 'after'")
    if set(after.keys()) != _TIE_KEYS:
        raise InvalidEditPayload("SetTie requiere exactamente 'tie' y 'next' en 'after'")
    tie = _parse_tie(after["tie"])
    raw = after["next"]
    if raw is None:
        return tie, None
    if not isinstance(raw, Mapping) or set(raw.keys()) != _NEXT_KEYS:
        raise InvalidEditPayload(
            f"'next' debe ser {{'measure', 'voice', 'event_index', 'tie'}} o null: {raw!r}"
        )
    numbers: list[int] = []
    for key in ("measure", "voice", "event_index"):
        value = raw[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise InvalidEditPayload(f"'{key}' de 'next' debe ser un entero >= 0: {value!r}")
        numbers.append(value)
    place: Place = (numbers[0], numbers[1], numbers[2])
    return tie, (place, _parse_tie(raw["tie"], " en 'next'"))


# --- Localizar -----------------------------------------------------------------------------


def _staff(score: ScoreIR, anchor: Anchor) -> Staff:
    if anchor.part >= len(score.parts):
        raise IndexError(f"parte fuera de rango: {anchor.part}")
    part = score.parts[anchor.part]
    if anchor.staff >= len(part.staves):
        raise IndexError(f"pentagrama fuera de rango: {anchor.staff}")
    return part.staves[anchor.staff]


def _measure_position(staff: Staff, number: int) -> int | None:
    return next((i for i, m in enumerate(staff.measures) if m.number == number), None)


def _voice_events(measure: Measure, voice: int) -> list[Event]:
    return [event for event in measure.events if event.voice == voice]


def _anchored(score: ScoreIR, anchor: Anchor) -> tuple[Staff, int, Event]:
    """El pentagrama del ancla, la posición de su compás y su evento; `IndexError` si no está."""

    staff = _staff(score, anchor)
    position = _measure_position(staff, anchor.measure)
    if position is None:
        raise IndexError(f"compás inexistente: {anchor.measure}")
    events = _voice_events(staff.measures[position], anchor.voice)
    if anchor.event_index >= len(events):
        raise IndexError(
            f"anchor {anchor.sort_key()} apunta a un evento inexistente del compás {anchor.measure}"
        )
    return staff, position, events[anchor.event_index]


def _event_at(staff: Staff, place: Place) -> Event | None:
    measure_number, voice, index = place
    position = _measure_position(staff, measure_number)
    if position is None:
        return None
    events = _voice_events(staff.measures[position], voice)
    return events[index] if index < len(events) else None


def _first_timed_group(events: Sequence[Event], start: int = 0) -> tuple[int, int] | None:
    """El primer grupo de la voz desde `start` que ocupa tiempo (sin las notas de adorno). Los
    silencios invisibles del final de la voz no cuentan: tras ellos no hay nada, como en
    `tie.resolution` (ADR-0040 §10), y la ligadura cruza la barra."""

    index = start
    while index < len(events):
        group_start, group_end = chord_bounds(events, index)
        # Una nota de adorno tiene duración 0 o nula (ADR-0028): no ocupa tiempo.
        if events[group_start].duration_beats:
            if all(event.hidden or not event.duration_beats for event in events[group_start:]):
                return None
            return group_start, group_end
        index = group_end
    return None


def following(staff: Staff, position: int, voice: int, index: int) -> list[Place]:
    """Lo que sigue a la nota `index` de la voz en el compás `position` del pentagrama: el grupo
    siguiente de su voz o, si el suyo es el último, el primer grupo de cada voz del compás
    siguiente. Vacío si no hay nada (la nota acaba el pentagrama)."""

    measure = staff.measures[position]
    events = _voice_events(measure, voice)
    _, end = chord_bounds(events, index)
    group = _first_timed_group(events, end)
    if group is not None:
        return [(measure.number, voice, k) for k in range(*group)]
    if position + 1 >= len(staff.measures):
        return []
    later = staff.measures[position + 1]
    found: list[Place] = []
    for other in sorted({event.voice for event in later.events}):
        first = _first_timed_group(_voice_events(later, other))
        if first is not None:
            found.extend((later.number, other, k) for k in range(*first))
    return found


def _preceding(staff: Staff, position: int, place: Place) -> list[Place]:
    """Las notas a las que sigue la de `place` (lo que sigue a cada una la incluye): de donde
    puede venir la ligadura que le llega. Están en su compás o en el anterior."""

    found: list[Place] = []
    for index in range(max(position - 1, 0), position + 1):
        measure = staff.measures[index]
        for voice in sorted({event.voice for event in measure.events}):
            for k, event in enumerate(_voice_events(measure, voice)):
                if event.kind is EventKind.NOTE and place in following(staff, index, voice, k):
                    found.append((measure.number, voice, k))
    return found


def _check_loose(staff: Staff, position: int, anchor: Anchor, note: Event, tie: Tie | None) -> None:
    """Sin `next` solo se quita una marca suelta: una ligadura que sale sin llegar a ninguna nota
    o que llega sin salir de ninguna. Si tiene pareja, se quita con ella (ADR-0055 §1)."""

    if (_arrives(tie) and not _arrives(note.tie)) or (_leaves(tie) and not _leaves(note.tie)):
        raise InvalidEditPayload(
            "sin 'next', SetTie solo quita la ligadura de la nota del ancla: para poner una, "
            "'next' es la otra nota"
        )
    if tie == note.tie:
        raise InvalidEditPayload("SetTie no cambia nada: la nota ya tiene esa ligadura")
    place: Place = (anchor.measure, anchor.voice, anchor.event_index)
    if _leaves(note.tie) and not _leaves(tie):
        for other in following(staff, position, anchor.voice, anchor.event_index):
            event = _event_at(staff, other)
            if event is not None and _arrives(event.tie):
                raise InvalidEditPayload(
                    "la ligadura que sale de la nota llega a otra: quítala con 'next', la otra nota"
                )
    if _arrives(note.tie) and not _arrives(tie):
        for source in _preceding(staff, position, place):
            event = _event_at(staff, source)
            if event is not None and _leaves(event.tie):
                raise InvalidEditPayload(
                    "la ligadura que llega a la nota sale de otra: quítala anclada en esa nota, "
                    "con 'next' esta"
                )


# --- Validar, la instantánea y la proyección ------------------------------------------------


def check_tie(score: ScoreIR, anchor: Anchor, after: object) -> None:
    """`InvalidEditPayload` si el `after` de `SetTie` no es válido sobre `score`; `IndexError` si
    el ancla no apunta a un evento."""

    tie, nxt = _parse_after(after)
    staff, position, note = _anchored(score, anchor)
    if note.kind is not EventKind.NOTE:
        raise InvalidEditPayload(f"SetTie se aplica a notas, no a '{note.kind.value}'")
    if nxt is None:
        _check_loose(staff, position, anchor, note, tie)
        return
    place, next_tie = nxt
    if not note.duration_beats:
        raise InvalidEditPayload("una nota de adorno no se liga")
    other = _event_at(staff, place)
    if other is None:
        raise InvalidEditPayload(
            f"la otra nota de la ligadura no existe: compás {place[0]}, voz {place[1]}, "
            f"evento {place[2]}"
        )
    if other.kind is not EventKind.NOTE:
        raise InvalidEditPayload("la otra nota de la ligadura es un silencio: solo se ligan notas")
    if not other.duration_beats:
        raise InvalidEditPayload("una nota de adorno no se liga")
    if place not in following(staff, position, anchor.voice, anchor.event_index):
        raise InvalidEditPayload(
            "la otra nota no es lo que sigue a la del ancla: una nota del grupo siguiente de su "
            "voz o, si es la última de su voz en el compás, del primero de una voz del compás "
            "siguiente"
        )
    if _arrives(tie) != _arrives(note.tie):
        raise InvalidEditPayload(
            "SetTie cambia la ligadura que sale de la nota del ancla: lo que le llega no cambia"
        )
    if _leaves(next_tie) != _leaves(other.tie):
        raise InvalidEditPayload(
            "SetTie cambia la ligadura que llega a la otra nota: lo que sale de ella no cambia"
        )
    linked = _leaves(tie)
    if _arrives(next_tie) != linked:
        raise InvalidEditPayload(
            "una ligadura sale de una nota y llega a la otra: las dos cambian a la vez"
        )
    if linked == _leaves(note.tie) and linked == _arrives(other.tie):
        raise InvalidEditPayload("SetTie no cambia nada: las notas ya están así")
    if linked and not same_pitch(note, other):
        raise InvalidEditPayload(
            f"una ligadura de prolongación une dos notas de la misma altura: {note.pitch} y "
            f"{other.pitch}"
        )


def snapshot_tie(score: ScoreIR, anchor: Anchor, after: object) -> dict[str, Any]:
    """Los valores que tienen las notas que fija el `after` (ya validado), con su forma."""

    _, nxt = _parse_after(after)
    staff, _, note = _anchored(score, anchor)
    if nxt is None:
        return {"tie": _value(note.tie), "next": None}
    place, _ = nxt
    other = _event_at(staff, place)
    if other is None:
        raise IndexError(f"la otra nota de la ligadura no existe: {place}")
    measure, voice, index = place
    return {
        "tie": _value(note.tie),
        "next": {
            "measure": measure,
            "voice": voice,
            "event_index": index,
            "tie": _value(other.tie),
        },
    }


def has_complete_tie_before(before: Mapping[str, Any]) -> bool:
    return _TIE_KEYS.issubset(before.keys())


def _with_tie(score: ScoreIR, anchor: Anchor, place: Place, tie: Tie | None) -> ScoreIR:
    staff = _staff(score, anchor)
    measure_number, voice, index = place
    position = _measure_position(staff, measure_number)
    if position is None:
        raise IndexError(f"compás inexistente: {measure_number}")
    measure = staff.measures[position]
    events = list(measure.events)
    in_voice = [i for i, event in enumerate(events) if event.voice == voice]
    if index >= len(in_voice):
        raise IndexError(f"evento inexistente: compás {measure_number}, voz {voice}, {index}")
    events[in_voice[index]] = replace(events[in_voice[index]], tie=tie)
    measures = list(staff.measures)
    measures[position] = replace(measure, events=tuple(events))
    part = score.parts[anchor.part]
    staves = list(part.staves)
    staves[anchor.staff] = replace(staff, measures=tuple(measures))
    parts = list(score.parts)
    parts[anchor.part] = replace(part, staves=tuple(staves))
    return replace(score, parts=tuple(parts))


def apply_tie(score: ScoreIR, anchor: Anchor, after: Mapping[str, Any]) -> ScoreIR:
    """Fija los valores del `after` en las notas (también los de la compensatoria, que no se
    valida); no muta `score`."""

    tie, nxt = _parse_after(after)
    result = _with_tie(score, anchor, (anchor.measure, anchor.voice, anchor.event_index), tie)
    if nxt is not None:
        place, next_tie = nxt
        result = _with_tie(result, anchor, place, next_tie)
    return result
