"""Ediciones del compás, los tresillos y la figura de un acorde: validación, estado previo y
proyección (ADR-0044, #236; ADR-0049, #243). La ligadura de prolongación (`SetTie`, ADR-0055) es
de su clase y entra por aquí, pero sus reglas están en `tie_edits`.

Tres operaciones de tipo «fijar», como las de marcas (ADR-0039): el servidor guarda en `before`
el estado que sustituyen, con la forma de su `after`, y la compensatoria intercambia los dos
(`create_inverse_edit`), de modo que deshacer es exacto (ADR-0007, ADR-0017).

- `SetTime`, anclada al compás (como `SetKey`, ADR-0010):
  ``{"time_signature": {"beats", "beat_type", "symbol"?} | None, "measures"?: k}``. Cambia el
  compás desde el compás del ancla hasta el siguiente cambio, en todos los pentagramas de la
  parte (la métrica es de la parte: todos sus pentagramas comparten la duración del compás).
  La importación da a cada compás su métrica efectiva (o ``None`` si la partitura no tiene
  compás), así que «hasta el siguiente cambio» es el **tramo**: el compás del ancla y los
  siguientes que llevan su misma indicación (o ``None`` si el tramo no tiene compás), hasta el
  primero que lleva otra. Todos los compases del tramo pasan a llevar la nueva indicación
  vigente (#329, enmienda de ADR-0044), como hace la importación, y ``None`` significa solo
  «sin compás». `measures` fija cuántos compases cambia en un tramo que ya tiene indicación;
  en un tramo en ``None`` debe cubrir el tramo entero (para no dejar ``None`` detrás de un
  compás con indicación, lo que impediría deshacer con exactitud un `SetTime` posterior). La
  instantánea lleva siempre `measures`, para que deshacer devuelva exactamente esos compases.
  Solo la compensatoria escribe ``None`` (para devolver a «sin compás» un tramo que no llevaba
  indicación); de un cliente, se rechaza. Con ``"all_parts": true``
  (#326, enmienda de ADR-0044), lo mismo en todas las partes, cada una en su tramo; la
  instantánea guarda lo de cada parte en ``parts`` y la compensatoria (la única que lo escribe)
  devuelve cada una a lo suyo. Sin él, solo la parte del ancla: un `SetTime` guardado antes de
  #326, y el candidato de `time.signature`, que es de una parte, materializan como entonces.
- `SetTuplet`, anclada al primer evento de un tramo de una voz de un compás:
  ``{"durations": [d1, ..., dn]}``, las figuras finales de los n eventos seguidos desde el ancla.
  Poner un tresillo de 3:2 multiplica cada figura por 2/3 y quitarlo, por 3/2: el servidor
  exige una de las dos cosas para todo el tramo. Una sola edición convierte un compás de doce
  corcheas en cuatro tresillos, y se deshace de un paso.
- `SetChordDuration`, anclada a la primera nota de un acorde: ``{"durations": [d, ..., d]}``,
  la figura de cada una de sus notas, todas la misma. El exportador dibuja el acorde con la
  figura de su primera nota y el mapa de tiempos da a cada nota la suya: el acorde cambia
  entero, en una edición que se deshace de un paso (D61). La instantánea guarda la figura de
  cada nota, así que deshacer es exacto aunque no fueran iguales.

Ninguna mueve un evento: el `event_index` de las anclas no cambia (ADR-0002, ADR-0011).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from fractions import Fraction
from typing import Any, Final

from .anchor import Anchor, EventKind
from .duration_rules import check_duration
from .edit import EditEvent, EditOp
from .edit_errors import InvalidEditPayload
from .score import Event, Measure, Part, ScoreIR, Staff
from .tie_edits import apply_tie, check_tie, has_complete_tie_before, snapshot_tie
from .time_signature import SYMBOL_METERS, TimeSignature, same_time_notation

_TIME_KEYS: Final[frozenset[str]] = frozenset({"time_signature", "measures"})
# Con `all_parts`, el compás cambia en todas las partes (#326); sin él, en la del ancla. La
# instantánea de un `SetTime` en todas las partes guarda en `parts` lo de cada una.
ALL_PARTS: Final[str] = "all_parts"
PARTS: Final[str] = "parts"
_TIME_CLIENT_KEYS: Final[frozenset[str]] = _TIME_KEYS | {ALL_PARTS}
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


def _part_scope(part: Part, number: int, name: str) -> tuple[list[tuple[int, int]], int] | None:
    """Los pentagramas de `part` con el compás `number` y la longitud de su tramo, o None si
    ninguno lo tiene.

    `InvalidEditPayload` si los pentagramas no llevan la misma indicación en ese compás o sus
    tramos no tienen la misma longitud: un solo `before` no podría devolverlos."""

    staves = _staves_with(part, number)
    if not staves:
        return None
    signatures = [part.staves[s].measures[p].time_signature for s, p in staves]
    if any(not same_time_notation(signature, signatures[0]) for signature in signatures):
        raise InvalidEditPayload(
            f"los pentagramas de {name} no llevan la misma indicación de compás en el compás "
            f"{number}"
        )
    runs = {_run_length(part.staves[s].measures, p) for s, p in staves}
    if len(runs) != 1:
        raise InvalidEditPayload(
            f"los pentagramas de {name} no cambian de compás en los mismos compases desde el "
            f"compás {number}"
        )
    return staves, runs.pop()


def _time_scope(score: ScoreIR, anchor: Anchor) -> tuple[Part, list[tuple[int, int]], int]:
    """Los pentagramas de la parte del ancla con su compás y la longitud de su tramo."""

    _anchor_measure(score, anchor)
    part = _part(score, anchor)
    scope = _part_scope(part, anchor.measure, "la parte")
    if scope is None:
        raise IndexError(f"compás inexistente: {anchor.measure}")
    staves, run = scope
    return part, staves, run


def _parts_scope(score: ScoreIR, anchor: Anchor) -> list[tuple[list[tuple[int, int]], int] | None]:
    """Con `all_parts` (#326): el alcance de cada parte en el compás del ancla, o None en las
    partes que no lo tienen."""

    _anchor_measure(score, anchor)
    return [
        _part_scope(part, anchor.measure, f"la parte {index + 1}")
        for index, part in enumerate(score.parts)
    ]


def _all_parts(after: object) -> bool:
    return isinstance(after, Mapping) and after.get(ALL_PARTS) is True


def _check_time(score: ScoreIR, anchor: Anchor, after: object) -> None:
    if not isinstance(after, Mapping):
        raise InvalidEditPayload("SetTime requiere un objeto 'after'")
    unknown = sorted(set(after.keys()).difference(_TIME_CLIENT_KEYS))
    if unknown:
        # `parts` es la forma por partes de la instantánea: solo la escribe la compensatoria.
        raise InvalidEditPayload(
            f"SetTime no admite {', '.join(unknown)} en 'after' "
            "(campos admitidos: all_parts, measures, time_signature)"
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
    if ALL_PARTS in after and not isinstance(after[ALL_PARTS], bool):
        raise InvalidEditPayload(f"'all_parts' debe ser true o false: {after[ALL_PARTS]!r}")
    _parse_signature(after["time_signature"])
    if _all_parts(after):
        scopes = [
            (score.parts[index], *scope)
            for index, scope in enumerate(_parts_scope(score, anchor))
            if scope is not None
        ]
    else:
        scopes = [_time_scope(score, anchor)]
    if "measures" in after:
        measures = _parse_measures(after["measures"])
        run = min(scope[2] for scope in scopes)
        if measures > run:
            raise InvalidEditPayload(
                f"'measures' ({measures}) pasa del siguiente cambio de compás: desde el compás "
                f"{anchor.measure} rige en {run}"
            )
        for part, staves, part_run in scopes:
            staff, position = staves[0]
            if part.staves[staff].measures[position].time_signature is None and measures < part_run:
                raise InvalidEditPayload(
                    f"'measures' ({measures}) debe cubrir todo el tramo sin indicación de compás "
                    f"({part_run} compases desde el compás {anchor.measure})"
                )


def _part_snapshot(
    part: Part, staves: list[tuple[int, int]], run: int, after: object
) -> dict[str, Any]:
    staff, position = staves[0]
    signature = part.staves[staff].measures[position].time_signature
    # Los compases que cambia la edición: los que da el cliente o el tramo entero.
    measures = after.get("measures", run) if isinstance(after, Mapping) else run
    return {
        "time_signature": None if signature is None else signature.to_primitive(),
        "measures": measures,
    }


def _snapshot_time(score: ScoreIR, anchor: Anchor, after: object) -> dict[str, Any]:
    part, staves, run = _time_scope(score, anchor)
    snapshot = _part_snapshot(part, staves, run, after)
    if not _all_parts(after):
        return snapshot
    # Con `all_parts`, lo de cada parte (#326): la compensatoria devuelve cada una a lo suyo
    # aunque las partes llevaran compases distintos. Arriba, lo de la parte del ancla, que es lo
    # que dice la historia y lo que compara el `before` del cliente.
    parts = [
        None if scope is None else _part_snapshot(score.parts[index], *scope, after)
        for index, scope in enumerate(_parts_scope(score, anchor))
    ]
    return {**snapshot, ALL_PARTS: True, PARTS: parts}


def _apply_time_to_part(
    part: Part, number: int, signature: TimeSignature | None, measures: int | None
) -> Part | None:
    """`part` con el compás `signature` desde el compás `number` en todos sus pentagramas, en
    `measures` compases o hasta el siguiente cambio; None si ningún pentagrama tiene el compás."""

    staves = list(part.staves)
    found = False
    for staff_index, staff in enumerate(part.staves):
        position = _position(staff, number)
        if position is None:
            continue
        found = True
        bars = list(staff.measures)
        run = measures if measures is not None else _run_length(bars, position)
        vigente = signature or _effective_before(bars, position)
        bars[position] = replace(bars[position], time_signature=signature)
        for index in range(position + 1, min(position + run, len(bars))):
            bars[index] = replace(bars[index], time_signature=vigente)
        staves[staff_index] = replace(staff, measures=tuple(bars))
    return replace(part, staves=tuple(staves)) if found else None


def _apply_time(score: ScoreIR, anchor: Anchor, after: Mapping[str, Any]) -> ScoreIR:
    parts = list(score.parts)
    if PARTS in after:
        # La compensatoria de un `SetTime` en todas las partes: cada parte vuelve a lo suyo.
        entries = after[PARTS]
        if not isinstance(entries, list | tuple) or len(entries) != len(parts):
            raise InvalidEditPayload(f"'parts' debe dar una entrada por parte: {entries!r}")
        for index, entry in enumerate(entries):
            if entry is None:
                continue
            changed = _apply_time_to_part(
                parts[index],
                anchor.measure,
                _parse_signature(entry["time_signature"]),
                _parse_measures(entry["measures"]),
            )
            if changed is None:
                raise IndexError(f"compás inexistente en la parte {index + 1}: {anchor.measure}")
            parts[index] = changed
        return replace(score, parts=tuple(parts))
    signature = _parse_signature(after["time_signature"])
    measures = _parse_measures(after["measures"]) if "measures" in after else None
    _part(score, anchor)
    targets = range(len(parts)) if _all_parts(after) else (anchor.part,)
    for index in targets:
        changed = _apply_time_to_part(parts[index], anchor.measure, signature, measures)
        if changed is not None:
            parts[index] = changed
        elif index == anchor.part:
            raise IndexError(f"compás inexistente: {anchor.measure}")
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


def _parse_durations(after: object, op: EditOp = EditOp.SET_TUPLET) -> list[object]:
    if not isinstance(after, Mapping):
        raise InvalidEditPayload(f"{op.value} requiere un objeto 'after'")
    if set(after.keys()) != _TUPLET_KEYS:
        raise InvalidEditPayload(f"{op.value} requiere exactamente 'durations' en 'after'")
    durations = after["durations"]
    if not isinstance(durations, list | tuple) or not durations:
        raise InvalidEditPayload(f"'durations' debe ser una lista no vacía: {durations!r}")
    return list(durations)


def _is_zero(raw: object) -> bool:
    """Si una duración de `after` es 0 (la de una nota de adorno)."""

    if isinstance(raw, bool) or not isinstance(raw, int | float | str | Fraction):
        return False
    try:
        return Fraction(str(raw)) == 0
    except (ValueError, ZeroDivisionError):
        return False


def _check_tuplet(score: ScoreIR, anchor: Anchor, after: object) -> None:
    durations = _parse_durations(after)
    events = _tuplet_range(score, anchor, len(durations))
    ratios: set[Fraction] = set()
    for event, raw in zip(events, durations, strict=True):
        if event.duration_beats is None:
            # Una nota de adorno de duración nula (ADR-0028): se queda sin figura, con null.
            if raw is not None:
                raise InvalidEditPayload("una nota de adorno no tiene figura: su duración es null")
            continue
        if event.duration_beats == 0:
            # Una nota de adorno de duración 0, como las da HOMR: también sin figura, con null o
            # con 0 (la instantánea del servidor la guarda como "0").
            if raw is not None and not _is_zero(raw):
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


def _durations_of(events: Sequence[Event]) -> dict[str, Any]:
    return {
        "durations": [
            None if event.duration_beats is None else str(event.duration_beats) for event in events
        ]
    }


def _snapshot_tuplet(score: ScoreIR, anchor: Anchor, after: object) -> dict[str, Any]:
    return _durations_of(_tuplet_range(score, anchor, len(_parse_durations(after))))


def _apply_durations(score: ScoreIR, anchor: Anchor, after: Mapping[str, Any]) -> ScoreIR:
    """Fija las figuras de los eventos seguidos de la voz del ancla, desde el ancla: las de un
    tresillo o las de las notas de un acorde (también las de la compensatoria, que no se
    valida)."""

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


# --- SetChordDuration --------------------------------------------------------------------


def _chord(score: ScoreIR, anchor: Anchor) -> list[Event]:
    """Las notas del acorde que empieza en el ancla, agrupadas como el exportador: una nota y las
    que la siguen en su voz marcadas `is_chord`."""

    events = _voice_events(_anchor_measure(score, anchor), anchor.voice)
    index = anchor.event_index
    if index >= len(events):
        raise IndexError(
            f"anchor {anchor.sort_key()} apunta a un evento inexistente del compás {anchor.measure}"
        )
    head = events[index]
    if head.kind is not EventKind.NOTE:
        raise InvalidEditPayload(
            "el ancla no es la primera nota de un acorde: la figura de un silencio o de una nota "
            "sola se cambia con SetDuration"
        )
    if head.is_chord and index > 0 and events[index - 1].kind is EventKind.NOTE:
        raise InvalidEditPayload(
            "el ancla es una nota de un acorde que no es la primera: ánclalo en su primera nota"
        )
    end = index + 1
    while end < len(events) and events[end].is_chord and events[end].kind is EventKind.NOTE:
        end += 1
    if end - index < 2:
        raise InvalidEditPayload(
            "el ancla no es la primera nota de un acorde: la figura de una nota sola se cambia "
            "con SetDuration"
        )
    return events[index:end]


def _check_chord_duration(score: ScoreIR, anchor: Anchor, after: object) -> None:
    durations = _parse_durations(after, EditOp.SET_CHORD_DURATION)
    notes = _chord(score, anchor)
    if len(durations) != len(notes):
        raise InvalidEditPayload(
            f"el acorde tiene {len(notes)} notas y 'durations' {len(durations)} figuras: una "
            "por nota"
        )
    if any(raw is None for raw in durations):
        raise InvalidEditPayload(
            "la figura de un acorde tiene duración: null solo lo escribe la compensatoria"
        )
    figures = {check_duration(raw) for raw in durations}
    if len(figures) != 1:
        raise InvalidEditPayload(
            "las notas de un acorde tienen una sola figura: todas las duraciones deben ser iguales"
        )


def _snapshot_chord_duration(score: ScoreIR, anchor: Anchor) -> dict[str, Any]:
    return _durations_of(_chord(score, anchor))


# --- Entrada -----------------------------------------------------------------------------


def validate_meter_after(
    score: ScoreIR, anchor: Anchor, op: EditOp, after: Mapping[str, Any] | None
) -> None:
    """Comprueba el `after` de `SetTime`, `SetTuplet` (ADR-0044), `SetChordDuration`
    (ADR-0049) o `SetTie` (ADR-0055) sobre el estado `score`.

    `InvalidEditPayload` si no es válido; `IndexError` si el ancla no apunta a su compás o
    a su evento."""

    if op is EditOp.SET_TIME:
        _check_time(score, anchor, after)
    elif op is EditOp.SET_TUPLET:
        _check_tuplet(score, anchor, after)
    elif op is EditOp.SET_CHORD_DURATION:
        _check_chord_duration(score, anchor, after)
    elif op is EditOp.SET_TIE:
        check_tie(score, anchor, after)
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
    if op is EditOp.SET_CHORD_DURATION:
        return _snapshot_chord_duration(score, anchor)
    if op is EditOp.SET_TIE:
        return snapshot_tie(score, anchor, after)
    raise ValueError(f"operación que no es de compás ni de tresillos: {op.value}")


def has_complete_meter_before(op: EditOp, before: Mapping[str, Any]) -> bool:
    """Si `before` basta para que la compensatoria devuelva el estado exacto."""

    if op is EditOp.SET_TIME:
        if not _TIME_KEYS.issubset(before.keys()):
            return False
        return before.get(ALL_PARTS) is not True or isinstance(before.get(PARTS), list | tuple)
    if op is EditOp.SET_TIE:
        return has_complete_tie_before(before)
    return isinstance(before.get("durations"), list | tuple)


def apply_meter_edit(score: ScoreIR, edit: EditEvent) -> ScoreIR:
    """Aplica `SetTime`, `SetTuplet`, `SetChordDuration` o `SetTie`; no muta `score`.
    `ValueError` si su `after` no se entiende, `IndexError` si no encuentra lo que fija."""

    after = edit.after
    if after is None:
        raise ValueError(f"{edit.op.value} sin 'after' no se puede aplicar")
    try:
        if edit.op is EditOp.SET_TIME:
            return _apply_time(score, edit.anchor, after)
        if edit.op in (EditOp.SET_TUPLET, EditOp.SET_CHORD_DURATION):
            return _apply_durations(score, edit.anchor, after)
        if edit.op is EditOp.SET_TIE:
            return apply_tie(score, edit.anchor, after)
    except (KeyError, TypeError, InvalidEditPayload) as exc:
        raise ValueError(f"'after' de {edit.op.value} no válido: {exc!r}") from exc
    raise ValueError(f"operación que no es de compás ni de tresillos: {edit.op.value}")
