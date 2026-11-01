"""Ediciones del compás y de los tresillos: validación, estado previo y proyección (ADR-0044, #236).

Dos operaciones de tipo «fijar», como las de marcas (ADR-0039): el servidor guarda en `before`
el estado que sustituyen, con la forma de su `after`, y la compensatoria intercambia los dos
(`create_inverse_edit`), de modo que deshacer es exacto (ADR-0007, ADR-0017).

- `SetTime`, anclada al compás (como `SetKey`, ADR-0010):
  ``{"time_signature": {"beats", "beat_type", "symbol"?} | None, "measures"?: k}``. Cambia el
  compás desde el compás del ancla hasta el siguiente cambio, en todos los pentagramas de la
  parte (la métrica es de la parte: todos sus pentagramas comparten la duración del compás).
  La importación da a cada compás su métrica efectiva, así que «hasta el siguiente cambio» es
  el **tramo**: el compás del ancla y los siguientes que llevan su misma indicación (o ninguna),
  hasta el primero que lleva otra. El compás del ancla pasa a llevar la indicación de `after`
  y los demás del tramo que llevaban una, la nueva vigente. `measures` fija cuántos compases
  cambia; sin él, el tramo entero. La instantánea los lleva siempre, para que deshacer devuelva
  exactamente esos compases. Solo la compensatoria escribe ``None`` (un compás que no llevaba
  indicación y hereda la del anterior); de un cliente, se rechaza.
- `SetTuplet`, anclada al primer evento de un tramo de una voz de un compás:
  ``{"durations": [d1, ..., dn]}``, las figuras finales de los n eventos seguidos desde el ancla.
  Poner un tresillo de 3:2 multiplica cada figura por 2/3 y quitarlo, por 3/2: el servidor
  exige una de las dos cosas para todo el tramo. Una sola edición convierte un compás de doce
  corcheas en cuatro tresillos, y se deshace de un paso.

Ninguna mueve un evento: el `event_index` de las anclas no cambia (ADR-0002, ADR-0011).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from fractions import Fraction
from typing import Any, Final

from .anchor import Anchor
from .duration_rules import check_duration
from .edit import EditEvent, EditOp
from .edit_errors import InvalidEditPayload
from .score import Event, Measure, Part, ScoreIR, Staff
from .time_signature import SYMBOL_METERS, TimeSignature, same_time_notation

_TIME_KEYS: Final[frozenset[str]] = frozenset({"time_signature", "measures"})
_SIGNATURE_KEYS: Final[frozenset[str]] = frozenset({"beats", "beat_type", "symbol"})
_TUPLET_KEYS: Final[frozenset[str]] = frozenset({"durations"})
# Las métricas que se escriben: numerador hasta 32 y denominador de la redonda a la fusa.
_MAX_BEATS: Final[int] = 32
_BEAT_TYPES: Final[frozenset[int]] = frozenset({1, 2, 4, 8, 16, 32})
# Tresillo de 3:2: tres figuras en el tiempo de dos.
PUT_TRIPLET: Final[Fraction] = Fraction(2, 3)
REMOVE_TRIPLET: Final[Fraction] = Fraction(3, 2)


# --- Localizar ---------------------------------------------------------------------------


def _part(score: ScoreIR, anchor: Anchor) -> Part:
    if anchor.part >= len(score.parts):
        raise IndexError(f"parte fuera de rango: {anchor.part}")
    part = score.parts[anchor.part]
    if anchor.staff >= len(part.staves):
        raise IndexError(f"pentagrama fuera de rango: {anchor.staff}")
    return part


def _position(staff: Staff, number: int) -> int | None:
    return next((i for i, m in enumerate(staff.measures) if m.number == number), None)


def _anchor_measure(score: ScoreIR, anchor: Anchor) -> Measure:
    part = _part(score, anchor)
    staff = part.staves[anchor.staff]
    index = _position(staff, anchor.measure)
    if index is None:
        raise IndexError(f"compás inexistente: {anchor.measure}")
    return staff.measures[index]


def _voice_events(measure: Measure, voice: int) -> list[Event]:
    return [event for event in measure.events if event.voice == voice]


# --- SetTime -----------------------------------------------------------------------------


def _effective_before(measures: Sequence[Measure], index: int) -> TimeSignature | None:
    """La indicación vigente al empezar el compás `index`: la del último anterior que la lleva."""

    for measure in reversed(measures[:index]):
        if measure.time_signature is not None:
            return measure.time_signature
    return None


def _run_length(measures: Sequence[Measure], index: int) -> int:
    """Cuántos compases, desde `index`, llevan la indicación vigente en él o ninguna: hasta el
    siguiente cambio."""

    current = measures[index].time_signature or _effective_before(measures, index)
    length = 1
    for measure in measures[index + 1 :]:
        signature = measure.time_signature
        if signature is not None and not same_time_notation(signature, current):
            break
        length += 1
    return length


def _staves_with(part: Part, number: int) -> list[tuple[int, int]]:
    """(pentagrama, posición del compás) de los pentagramas de la parte que tienen el compás."""

    found: list[tuple[int, int]] = []
    for staff_index, staff in enumerate(part.staves):
        position = _position(staff, number)
        if position is not None:
            found.append((staff_index, position))
    return found


def _parse_signature(value: object) -> TimeSignature | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise InvalidEditPayload(
            f"'time_signature' debe ser {{'beats', 'beat_type', 'symbol'?}} o null: {value!r}"
        )
    unknown = sorted(set(value.keys()).difference(_SIGNATURE_KEYS))
    if unknown:
        raise InvalidEditPayload(
            f"el compás no admite {', '.join(unknown)} (campos: beats, beat_type, symbol)"
        )
    missing = sorted({"beats", "beat_type"}.difference(value.keys()))
    if missing:
        raise InvalidEditPayload(f"el compás requiere {', '.join(missing)}")
    beats, beat_type = value["beats"], value["beat_type"]
    if isinstance(beats, bool) or not isinstance(beats, int) or not 1 <= beats <= _MAX_BEATS:
        raise InvalidEditPayload(f"'beats' debe ser un entero entre 1 y {_MAX_BEATS}: {beats!r}")
    if (
        isinstance(beat_type, bool)
        or not isinstance(beat_type, int)
        or beat_type not in _BEAT_TYPES
    ):
        raise InvalidEditPayload(f"'beat_type' debe ser 1, 2, 4, 8, 16 o 32: {beat_type!r}")
    symbol = value.get("symbol")
    if symbol is not None:
        meter = SYMBOL_METERS.get(symbol) if isinstance(symbol, str) else None
        if meter is None:
            raise InvalidEditPayload(f"'symbol' debe ser 'common', 'cut' o null: {symbol!r}")
        if meter != (beats, beat_type):
            raise InvalidEditPayload(
                f"el símbolo {symbol!r} es el compás {meter[0]}/{meter[1]}, no {beats}/{beat_type}"
            )
    return TimeSignature(beats, beat_type, symbol)


def _parse_measures(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidEditPayload(f"'measures' debe ser un entero >= 1: {value!r}")
    return value


def _time_scope(score: ScoreIR, anchor: Anchor) -> tuple[Part, list[tuple[int, int]], int]:
    """Los pentagramas de la parte con el compás del ancla y la longitud de su tramo.

    `InvalidEditPayload` si los pentagramas no llevan la misma indicación en ese compás o sus
    tramos no tienen la misma longitud: un solo `before` no podría devolverlos."""

    _anchor_measure(score, anchor)
    part = _part(score, anchor)
    staves = _staves_with(part, anchor.measure)
    signatures = [part.staves[s].measures[p].time_signature for s, p in staves]
    if any(not same_time_notation(signature, signatures[0]) for signature in signatures):
        raise InvalidEditPayload(
            f"los pentagramas de la parte no llevan la misma indicación de compás en el compás "
            f"{anchor.measure}"
        )
    runs = {_run_length(part.staves[s].measures, p) for s, p in staves}
    if len(runs) != 1:
        raise InvalidEditPayload(
            f"los pentagramas de la parte no cambian de compás en los mismos compases desde el "
            f"compás {anchor.measure}"
        )
    return part, staves, runs.pop()


def _check_time(score: ScoreIR, anchor: Anchor, after: object) -> None:
    if not isinstance(after, Mapping):
        raise InvalidEditPayload("SetTime requiere un objeto 'after'")
    unknown = sorted(set(after.keys()).difference(_TIME_KEYS))
    if unknown:
        raise InvalidEditPayload(
            f"SetTime no admite {', '.join(unknown)} en 'after' "
            "(campos admitidos: measures, time_signature)"
        )
    if "time_signature" not in after:
        raise InvalidEditPayload("SetTime requiere time_signature en 'after'")
    if after["time_signature"] is None:
        # La importación da a cada compás su métrica: un compás sin ella dejaría de comprobarse
        # (ADR-0040) y de rellenarse al exportar (#152). Solo la compensatoria escribe null, para
        # devolver un compás que no la tenía.
        raise InvalidEditPayload(
            "SetTime requiere un compás en 'time_signature': para quitar un cambio, pon el del "
            "compás anterior"
        )
    _parse_signature(after["time_signature"])
    _, _, run = _time_scope(score, anchor)
    if "measures" in after:
        measures = _parse_measures(after["measures"])
        if measures > run:
            raise InvalidEditPayload(
                f"'measures' ({measures}) pasa del siguiente cambio de compás: desde el compás "
                f"{anchor.measure} rige en {run}"
            )


def _snapshot_time(score: ScoreIR, anchor: Anchor, after: object) -> dict[str, Any]:
    part, staves, run = _time_scope(score, anchor)
    staff, position = staves[0]
    signature = part.staves[staff].measures[position].time_signature
    # Los compases que cambia la edición: los que da el cliente o el tramo entero.
    measures = after.get("measures", run) if isinstance(after, Mapping) else run
    return {
        "time_signature": None if signature is None else signature.to_primitive(),
        "measures": measures,
    }


def _apply_time(score: ScoreIR, anchor: Anchor, after: Mapping[str, Any]) -> ScoreIR:
    signature = _parse_signature(after["time_signature"])
    part = _part(score, anchor)
    staves = list(part.staves)
    found = False
    for staff_index, staff in enumerate(part.staves):
        position = _position(staff, anchor.measure)
        if position is None:
            continue
        found = True
        measures = list(staff.measures)
        run = (
            _parse_measures(after["measures"])
            if "measures" in after
            else _run_length(measures, position)
        )
        vigente = signature or _effective_before(measures, position)
        measures[position] = replace(measures[position], time_signature=signature)
        for index in range(position + 1, min(position + run, len(measures))):
            if measures[index].time_signature is not None:
                measures[index] = replace(measures[index], time_signature=vigente)
        staves[staff_index] = replace(staff, measures=tuple(measures))
    if not found:
        raise IndexError(f"compás inexistente: {anchor.measure}")
    parts = list(score.parts)
    parts[anchor.part] = replace(part, staves=tuple(staves))
    return replace(score, parts=tuple(parts))


# --- SetTuplet ---------------------------------------------------------------------------


def _has_triplet(duration: Fraction) -> bool:
    return duration.denominator % 3 == 0


def _tuplet_range(score: ScoreIR, anchor: Anchor, count: int) -> list[Event]:
    events = _voice_events(_anchor_measure(score, anchor), anchor.voice)
    if anchor.event_index >= len(events):
        raise IndexError(
            f"anchor {anchor.sort_key()} apunta a un evento inexistente del compás {anchor.measure}"
        )
    end = anchor.event_index + count
    if end > len(events):
        raise InvalidEditPayload(
            f"'durations' tiene {count} figuras y desde el ancla la voz solo tiene "
            f"{len(events) - anchor.event_index} eventos en el compás {anchor.measure}"
        )
    if events[anchor.event_index].is_chord:
        raise InvalidEditPayload(
            "el tramo empieza a mitad de un acorde: ánclalo en su primera nota"
        )
    if end < len(events) and events[end].is_chord:
        raise InvalidEditPayload("el tramo acaba a mitad de un acorde: incluye todas sus notas")
    return events[anchor.event_index : end]


def _parse_durations(after: object) -> list[object]:
    if not isinstance(after, Mapping):
        raise InvalidEditPayload("SetTuplet requiere un objeto 'after'")
    if set(after.keys()) != _TUPLET_KEYS:
        raise InvalidEditPayload("SetTuplet requiere exactamente 'durations' en 'after'")
    durations = after["durations"]
    if not isinstance(durations, list | tuple) or not durations:
        raise InvalidEditPayload(f"'durations' debe ser una lista no vacía: {durations!r}")
    return list(durations)


def _check_tuplet(score: ScoreIR, anchor: Anchor, after: object) -> None:
    durations = _parse_durations(after)
    events = _tuplet_range(score, anchor, len(durations))
    ratios: set[Fraction] = set()
    for event, raw in zip(events, durations, strict=True):
        if event.duration_beats is None:
            # Una nota de adorno no ocupa tiempo (ADR-0028): se queda sin figura.
            if raw is not None:
                raise InvalidEditPayload("una nota de adorno no tiene figura: su duración es null")
            continue
        if raw is None:
            raise InvalidEditPayload("solo una nota de adorno tiene la duración null")
        duration = check_duration(raw)
        ratio = duration / event.duration_beats
        if ratio not in (PUT_TRIPLET, REMOVE_TRIPLET):
            raise InvalidEditPayload(
                f"un tresillo multiplica cada figura por 2/3 (ponerlo) o por 3/2 (quitarlo): "
                f"{event.duration_beats} no pasa a {duration}"
            )
        putting = ratio == PUT_TRIPLET
        if putting == _has_triplet(event.duration_beats) or putting != _has_triplet(duration):
            # Una figura con puntillo por 2/3 es otra figura sin tresillo (3/2 → 1).
            raise InvalidEditPayload(
                "solo se pone el tresillo a figuras que no lo llevan y que pasan a llevarlo, y "
                f"solo se quita a las que lo llevan: {event.duration_beats} no pasa a {duration}"
            )
        ratios.add(ratio)
    if not ratios:
        raise InvalidEditPayload(
            "el tramo solo tiene notas de adorno: no hay figuras a las que poner o quitar el "
            "tresillo"
        )
    if len(ratios) != 1:
        raise InvalidEditPayload(
            "SetTuplet pone o quita el tresillo a todo el tramo, no las dos cosas a la vez"
        )


def _snapshot_tuplet(score: ScoreIR, anchor: Anchor, after: object) -> dict[str, Any]:
    events = _tuplet_range(score, anchor, len(_parse_durations(after)))
    return {
        "durations": [
            None if event.duration_beats is None else str(event.duration_beats) for event in events
        ]
    }


def _apply_tuplet(score: ScoreIR, anchor: Anchor, after: Mapping[str, Any]) -> ScoreIR:
    durations = list(after["durations"])
    part = _part(score, anchor)
    staff = part.staves[anchor.staff]
    position = _position(staff, anchor.measure)
    if position is None:
        raise IndexError(f"compás inexistente: {anchor.measure}")
    measure = staff.measures[position]
    events = list(measure.events)
    in_voice = [i for i, event in enumerate(events) if event.voice == anchor.voice]
    targets = in_voice[anchor.event_index : anchor.event_index + len(durations)]
    if len(targets) != len(durations):
        raise IndexError(
            f"anchor {anchor.sort_key()}: el tramo de {len(durations)} eventos no cabe en la voz"
        )
    for index, raw in zip(targets, durations, strict=True):
        events[index] = replace(
            events[index], duration_beats=None if raw is None else Fraction(str(raw))
        )
    measures = list(staff.measures)
    measures[position] = replace(measure, events=tuple(events))
    staves = list(part.staves)
    staves[anchor.staff] = replace(staff, measures=tuple(measures))
    parts = list(score.parts)
    parts[anchor.part] = replace(part, staves=tuple(staves))
    return replace(score, parts=tuple(parts))


# --- Entrada -----------------------------------------------------------------------------


def validate_meter_after(
    score: ScoreIR, anchor: Anchor, op: EditOp, after: Mapping[str, Any] | None
) -> None:
    """Comprueba el `after` de `SetTime` o `SetTuplet` sobre el estado `score` (ADR-0044).

    `InvalidEditPayload` si no es válido; `IndexError` si el ancla no apunta a su compás o
    a su evento."""

    if op is EditOp.SET_TIME:
        _check_time(score, anchor, after)
    elif op is EditOp.SET_TUPLET:
        _check_tuplet(score, anchor, after)
    else:
        raise ValueError(f"operación que no es de compás ni de tresillos: {op.value}")


def snapshot_meter_before(
    score: ScoreIR, anchor: Anchor, op: EditOp, after: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Estado que sustituye la edición, en la forma de su `after` (con la longitud del tramo en
    `SetTime`). Se calcula sobre un `after` ya validado."""

    if op is EditOp.SET_TIME:
        return _snapshot_time(score, anchor, after)
    if op is EditOp.SET_TUPLET:
        return _snapshot_tuplet(score, anchor, after)
    raise ValueError(f"operación que no es de compás ni de tresillos: {op.value}")


def has_complete_meter_before(op: EditOp, before: Mapping[str, Any]) -> bool:
    """Si `before` basta para que la compensatoria devuelva el estado exacto."""

    if op is EditOp.SET_TIME:
        return _TIME_KEYS.issubset(before.keys())
    return isinstance(before.get("durations"), list | tuple)


def apply_meter_edit(score: ScoreIR, edit: EditEvent) -> ScoreIR:
    """Aplica `SetTime` o `SetTuplet`; no muta `score`. `ValueError` si su `after` no se
    entiende, `IndexError` si no encuentra lo que fija."""

    after = edit.after
    if after is None:
        raise ValueError(f"{edit.op.value} sin 'after' no se puede aplicar")
    try:
        if edit.op is EditOp.SET_TIME:
            return _apply_time(score, edit.anchor, after)
        if edit.op is EditOp.SET_TUPLET:
            return _apply_tuplet(score, edit.anchor, after)
    except (KeyError, TypeError, InvalidEditPayload) as exc:
        raise ValueError(f"'after' de {edit.op.value} no válido: {exc!r}") from exc
    raise ValueError(f"operación que no es de compás ni de tresillos: {edit.op.value}")
