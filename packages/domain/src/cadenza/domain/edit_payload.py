"""Contenido de las ediciones: validación de `after` y estado previo `before` (ADR-0017, #117).

Dos reglas puras que la capa de aplicación aplica antes de persistir una edición:

- `validate_after`: el `after` debe ser coherente con su operación y expresarse en el
  vocabulario canónico del dominio (alturas como ``C#4``/``Bb3``, duraciones positivas,
  claves G/F/C, armaduras de -7 a 7). Un `after` incoherente se rechaza en lugar de
  persistirse.
- `snapshot_before`: el servidor fija `before` con una instantánea del estado sobre el
  que se aplica la edición, de modo que el evento inverso (`create_inverse_edit`)
  restaure siempre el estado exacto, sin depender de lo que envíe el cliente.

Las operaciones de las marcas de notación (ADR-0039) tienen sus reglas en `mark_edits`, y las del
compás y los tresillos (ADR-0044), en `meter_edits` (la ligadura de prolongación, ADR-0055, en
`tie_edits`). Los acordes (ADR-0055): una nota con `is_chord` se inserta justo tras otra nota y un
evento sin él no parte un acorde; la primera nota de un acorde se borra con
``{"keep_chord": true}``, y la siguiente pasa a ser la primera.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import replace
from typing import Any, Final

from .anchor import Anchor, EventKind
from .chords import is_chord_head, joins_previous
from .clef import Clef
from .duration_rules import check_duration
from .edit import MARK_EDIT_OPS, METER_EDIT_OPS, EditEvent, EditOp
from .edit_errors import InvalidEditPayload
from .key_signature import KeySignature
from .mark_edits import has_complete_mark_before, snapshot_mark_before, validate_mark_after
from .meter_edits import has_complete_meter_before, snapshot_meter_before, validate_meter_after
from .notation_marks import Articulation, SlurType
from .projection import _ACCIDENTAL_MAP, _PITCH_RE, _apply_accidental
from .score import Event, Measure, ScoreIR
from .tie import Tie

_CANONICAL_PITCH_RE: Final[re.Pattern[str]] = re.compile(r"^([A-G])(#{1,2}|b{1,2})?([0-9])$")
_STEP_SEMITONES: Final[dict[str, int]] = {
    "C": 0,
    "D": 2,
    "E": 4,
    "F": 5,
    "G": 7,
    "A": 9,
    "B": 11,
}
_ALTER_SEMITONES: Final[dict[str, int]] = {"": 0, "#": 1, "##": 2, "b": -1, "bb": -2}
_MIDI_MAX: Final[int] = 127

# Alteraciones de `SetAccidental`: las que la proyección y el plano offline
# (`DatasetBuilder`) interpretan igual.
_EDIT_ACCIDENTALS: Final[frozenset[str]] = frozenset(
    {"", "natural", "#", "##", "x", "b", "-", "bb", "--"}
)

_CLEF_SIGNS: Final[frozenset[str]] = frozenset({"G", "F", "C"})
_CLEF_NAMES: Final[frozenset[str]] = frozenset(
    {"treble", "sol", "g", "bass", "fa", "f", "alto", "do3", "c3", "tenor", "do4", "c4"}
)
_KEY_MODES: Final[frozenset[str | None]] = frozenset({None, "major", "minor"})

# Marcas de la nota (ADR-0031): las admite `InsertEvent` y las guarda la instantánea de
# `DeleteEvent`, para que deshacer un borrado devuelva la nota con ellas.
_EVENT_MARK_KEYS: Final[tuple[str, ...]] = ("articulations", "fermata", "slurs")
# Un silencio invisible (ADR-0032) también: deshacer el borrado del hueco de una voz lo
# devuelve invisible. Si el silencio se ve, la instantánea no lo lleva.
_HIDDEN_KEY: Final[str] = "hidden"
_INSERT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "kind",
        "pitch",
        "duration_beats",
        "tie",
        "is_chord",
        "bbox",
        "confidence",
        "voice",
        *_EVENT_MARK_KEYS,
        _HIDDEN_KEY,
    }
)
# Sin marcas, la instantánea no las lleva: su ausencia es «sin marcas», como en las
# instantáneas guardadas antes de ADR-0031.
_DELETE_SNAPSHOT_KEYS: Final[frozenset[str]] = frozenset({"kind", "pitch", "duration_beats"})
# Lo que es un evento para `SetEventKind` (ADR-0058): su clase, su altura y si es un hueco.
_KIND_KEYS: Final[frozenset[str]] = frozenset({"kind", "pitch", _HIDDEN_KEY})
# Borrar la primera nota de un acorde conservando el acorde (ADR-0055): el `after` del borrado, y
# lo que tenía la nota siguiente como nota del acorde, en su instantánea y en la compensatoria.
KEEP_CHORD: Final[str] = "keep_chord"
NEXT_IN_CHORD: Final[str] = "next_in_chord"
_ARTICULATIONS: Final[frozenset[str]] = frozenset(a.value for a in Articulation)
_SLUR_TYPES: Final[frozenset[str]] = frozenset(t.value for t in SlurType)


__all__ = [
    "InvalidEditPayload",
    "has_complete_before",
    "is_canonical_pitch",
    "normalize_accidental",
    "snapshot_before",
    "validate_after",
]


def is_canonical_pitch(value: object) -> bool:
    """Indica si `value` es una altura del vocabulario canónico representable en MIDI.

    Forma: letra mayúscula de la A a la G, alteración opcional (``#``, ``##``, ``b``,
    ``bb``) y octava de un dígito; la nota resultante debe caber en el rango MIDI
    (de 0 a 127).
    """

    if not isinstance(value, str):
        return False
    match = _CANONICAL_PITCH_RE.match(value)
    if match is None:
        return False
    step, alter, octave = match.group(1), match.group(2) or "", int(match.group(3))
    midi = (octave + 1) * 12 + _STEP_SEMITONES[step] + _ALTER_SEMITONES[alter]
    return 0 <= midi <= _MIDI_MAX


def _locate_measure(score: ScoreIR, anchor: Anchor) -> Measure:
    if anchor.part >= len(score.parts):
        raise IndexError(f"parte fuera de rango: {anchor.part}")
    part = score.parts[anchor.part]
    if anchor.staff >= len(part.staves):
        raise IndexError(f"pentagrama fuera de rango: {anchor.staff}")
    for measure in part.staves[anchor.staff].measures:
        if measure.number == anchor.measure:
            return measure
    raise IndexError(f"compás inexistente: {anchor.measure}")


def _locate_event(score: ScoreIR, anchor: Anchor) -> Event:
    measure = _locate_measure(score, anchor)
    voice_events = [event for event in measure.events if event.voice == anchor.voice]
    if anchor.event_index >= len(voice_events):
        raise IndexError(
            f"anchor {anchor.sort_key()} apunta a un evento inexistente del compás "
            f"{measure.number}"
        )
    return voice_events[anchor.event_index]


def _require_mapping(op: EditOp, after: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if after is None or not isinstance(after, Mapping):
        raise InvalidEditPayload(f"{op.value} requiere un objeto 'after'")
    return after


def _require_keys(
    op: EditOp,
    after: Mapping[str, Any],
    *,
    required: frozenset[str],
    allowed: frozenset[str],
) -> None:
    missing = sorted(required.difference(after.keys()))
    if missing:
        raise InvalidEditPayload(f"{op.value} requiere {', '.join(missing)} en 'after'")
    unknown = sorted(set(after.keys()).difference(allowed))
    if unknown:
        raise InvalidEditPayload(
            f"{op.value} no admite {', '.join(unknown)} en 'after' "
            f"(campos admitidos: {', '.join(sorted(allowed))})"
        )


def _check_pitch(value: object) -> None:
    if not is_canonical_pitch(value):
        raise InvalidEditPayload(
            f"altura no válida: {value!r} (forma esperada: letra mayúscula de la A a la G, "
            "alteración opcional #, ##, b o bb y octava de 0 a 9 dentro del rango MIDI, "
            "p. ej. 'C#4' o 'Bb3')"
        )


def _check_duration(value: object) -> None:
    check_duration(value)


def _check_int(name: str, value: object, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise InvalidEditPayload(f"{name} debe ser un entero entre {low} y {high}: {value!r}")
    return value


def _check_clef_fields(fields: Mapping[str, Any]) -> None:
    unknown = sorted(set(fields.keys()).difference({"sign", "line", "octave_change"}))
    if unknown:
        raise InvalidEditPayload(f"la clave no admite {', '.join(unknown)}")
    if "sign" not in fields:
        raise InvalidEditPayload("la clave requiere 'sign'")
    if not isinstance(fields["sign"], str) or fields["sign"] not in _CLEF_SIGNS:
        raise InvalidEditPayload(f"signo de clave no válido: {fields['sign']!r} (G, F o C)")
    _check_int("line", fields.get("line", 2), 1, 5)
    _check_int("octave_change", fields.get("octave_change", 0), -2, 2)


def _check_clef(op: EditOp, after: Mapping[str, Any]) -> None:
    if "clef" in after:
        _require_keys(op, after, required=frozenset({"clef"}), allowed=frozenset({"clef"}))
        raw = after["clef"]
        if raw is None:
            return
        if isinstance(raw, str):
            if raw.strip().lower() not in _CLEF_NAMES:
                raise InvalidEditPayload(f"nombre de clave no válido: {raw!r}")
            return
        if isinstance(raw, Mapping):
            _check_clef_fields(raw)
            return
        raise InvalidEditPayload(f"clave no válida: {raw!r}")
    _require_keys(
        op,
        after,
        required=frozenset({"sign"}),
        allowed=frozenset({"sign", "line", "octave_change"}),
    )
    _check_clef_fields(after)


def _check_key_fields(fields: Mapping[str, Any]) -> None:
    unknown = sorted(set(fields.keys()).difference({"fifths", "mode"}))
    if unknown:
        raise InvalidEditPayload(f"la armadura no admite {', '.join(unknown)}")
    if "fifths" not in fields:
        raise InvalidEditPayload("la armadura requiere 'fifths'")
    _check_int("fifths", fields["fifths"], -7, 7)
    mode = fields.get("mode")
    if mode is not None and (not isinstance(mode, str) or mode not in _KEY_MODES):
        raise InvalidEditPayload(f"modo no válido: {mode!r} (major o minor)")


def _check_key(op: EditOp, after: Mapping[str, Any]) -> None:
    for wrapper in ("key_signature", "key"):
        if wrapper in after:
            _require_keys(op, after, required=frozenset({wrapper}), allowed=frozenset({wrapper}))
            raw = after[wrapper]
            if raw is None:
                return
            if isinstance(raw, Mapping):
                _check_key_fields(raw)
                return
            _check_int("fifths", raw, -7, 7)
            return
    _check_key_fields(after)


def _check_insert(op: EditOp, anchor: Anchor, after: Mapping[str, Any]) -> None:
    if NEXT_IN_CHORD in after:
        raise InvalidEditPayload(
            f"'{NEXT_IN_CHORD}' solo lo escribe la compensatoria de borrar la primera nota de un "
            "acorde: para añadir una nota a un acorde, insértala con 'is_chord' tras otra nota"
        )
    _require_keys(op, after, required=frozenset({"kind", "duration_beats"}), allowed=_INSERT_KEYS)
    # La voz la fija el ancla; se admite repetirla en `after` solo si coincide.
    if "voice" in after and (isinstance(after["voice"], bool) or after["voice"] != anchor.voice):
        raise InvalidEditPayload(
            f"'voice' en 'after' ({after['voice']!r}) no coincide con la del ancla "
            f"({anchor.voice})"
        )
    kind = after["kind"]
    if kind == EventKind.NOTE.value:
        if "pitch" not in after:
            raise InvalidEditPayload("InsertEvent de una nota requiere 'pitch'")
        _check_pitch(after["pitch"])
    elif kind == EventKind.REST.value:
        if after.get("pitch") is not None:
            raise InvalidEditPayload("un silencio no lleva 'pitch'")
        if after.get("tie") is not None or after.get("is_chord"):
            raise InvalidEditPayload("un silencio no lleva 'tie' ni 'is_chord'")
    else:
        raise InvalidEditPayload(f"InsertEvent solo admite kind 'note' o 'rest': {kind!r}")
    hidden = after.get(_HIDDEN_KEY)
    if hidden is not None and not isinstance(hidden, bool):
        raise InvalidEditPayload(f"'hidden' debe ser booleano: {hidden!r}")
    if hidden and kind != EventKind.REST.value:
        raise InvalidEditPayload("solo un silencio puede ser invisible ('hidden')")
    _check_duration(after["duration_beats"])
    tie = after.get("tie")
    if tie is not None and (
        not isinstance(tie, str) or tie not in {member.value for member in Tie}
    ):
        raise InvalidEditPayload(f"'tie' no válido: {tie!r} (start, continue o stop)")
    if "is_chord" in after and not isinstance(after["is_chord"], bool):
        raise InvalidEditPayload(f"'is_chord' debe ser booleano: {after['is_chord']!r}")
    bbox = after.get("bbox")
    if bbox is not None and not (
        isinstance(bbox, list | tuple) and len(bbox) == 4 and all(map(_is_finite_number, bbox))
    ):
        raise InvalidEditPayload(f"'bbox' debe ser [x0, y0, x1, y1] numérico: {bbox!r}")
    confidence = after.get("confidence")
    if confidence is not None and (
        not _is_finite_number(confidence) or not 0.0 <= confidence <= 1.0
    ):
        raise InvalidEditPayload(f"'confidence' debe estar entre 0 y 1: {confidence!r}")
    _check_event_marks(after)


def _check_event_marks(after: Mapping[str, Any]) -> None:
    """Marcas de la nota de un `InsertEvent` (ADR-0031), en la forma de la instantánea."""

    articulations = after.get("articulations")
    if articulations is not None and not (
        isinstance(articulations, list | tuple)
        and all(isinstance(a, str) and a in _ARTICULATIONS for a in articulations)
    ):
        raise InvalidEditPayload(
            f"'articulations' debe ser una lista de {', '.join(sorted(_ARTICULATIONS))}: "
            f"{articulations!r}"
        )
    fermata = after.get("fermata")
    if fermata is not None and not isinstance(fermata, bool):
        raise InvalidEditPayload(f"'fermata' debe ser booleano: {fermata!r}")
    slurs = after.get("slurs")
    if slurs is None:
        return
    if not isinstance(slurs, list | tuple):
        raise InvalidEditPayload(f"'slurs' debe ser una lista: {slurs!r}")
    for slur in slurs:
        if not (
            isinstance(slur, Mapping)
            and set(slur.keys()) == {"type", "number"}
            and isinstance(slur["type"], str)
            and slur["type"] in _SLUR_TYPES
            and not isinstance(slur["number"], bool)
            and isinstance(slur["number"], int)
            and slur["number"] >= 1
        ):
            raise InvalidEditPayload(
                "cada extremo de 'slurs' es {'type': 'start' o 'stop', 'number': entero >= 1}: "
                f"{slur!r}"
            )


def _check_insert_place(score: ScoreIR, anchor: Anchor, after: Mapping[str, Any]) -> None:
    """Una nota con `is_chord` va justo tras otra nota de su voz, y un evento sin él no se
    inserta entre las notas de un acorde: el exportador y el mapa de tiempos lo leerían distinto
    (ADR-0055 §2)."""

    events = [e for e in _locate_measure(score, anchor).events if e.voice == anchor.voice]
    index = anchor.event_index
    if after.get("is_chord") is True:
        if index == 0 or index > len(events) or events[index - 1].kind is not EventKind.NOTE:
            raise InvalidEditPayload(
                "una nota con 'is_chord' va justo tras otra nota de su voz: es una nota más de "
                "su acorde"
            )
        if events[index - 1].duration_beats is None:
            # El exportador dibujaría el acorde entero como adorno con la duración de la nueva.
            raise InvalidEditPayload("una nota con duración no se añade a una nota de adorno")
        if any(after.get(key) for key in _EVENT_MARK_KEYS):
            raise InvalidEditPayload(
                "las marcas de un acorde van en su primera nota: una nota con 'is_chord' no "
                "lleva 'articulations', 'fermata' ni 'slurs'"
            )
    elif index < len(events) and joins_previous(events, index):
        raise InvalidEditPayload(
            "un evento sin 'is_chord' entre dos notas de un acorde partiría el acorde: "
            "insértalo antes de su primera nota o, con 'is_chord', como una nota más"
        )


def _check_delete(score: ScoreIR, anchor: Anchor, after: Mapping[str, Any] | None) -> None:
    """`after: null`, o `{"keep_chord": true}` en la primera nota de un acorde, que lo necesita:
    sin él, la nota siguiente se pegaría a lo que precede al acorde (ADR-0055 §3)."""

    _locate_event(score, anchor)
    events = [e for e in _locate_measure(score, anchor).events if e.voice == anchor.voice]
    head = is_chord_head(events, anchor.event_index)
    if after is None:
        if head:
            raise InvalidEditPayload(
                "es la primera nota de un acorde: se borra con after {'keep_chord': true}, y la "
                "nota siguiente pasa a ser la primera, con la figura y las marcas del acorde"
            )
        return
    # `is True`: un 1 no vale como booleano (ADR-0017).
    if (
        not isinstance(after, Mapping)
        or set(after) != {KEEP_CHORD}
        or after[KEEP_CHORD] is not True
    ):
        raise InvalidEditPayload(
            "DeleteEvent lleva after null o, en la primera nota de un acorde, "
            "{'keep_chord': true}"
        )
    if not head:
        raise InvalidEditPayload(
            "'keep_chord' solo se usa en la primera nota de un acorde de dos o más notas"
        )


def _kind_state(event: Event) -> dict[str, Any]:
    """Lo que es un evento, en la forma del `after` de `SetEventKind` (ADR-0058)."""

    return {"kind": event.kind.value, "pitch": event.pitch, _HIDDEN_KEY: event.hidden}


def _check_event_kind(score: ScoreIR, anchor: Anchor, after: Mapping[str, Any] | None) -> None:
    """`SetEventKind` convierte un hueco (un silencio invisible, ADR-0032) en un silencio que se
    ve o en una nota en su lugar, con la misma figura (ADR-0058). Solo la compensatoria lo
    devuelve a hueco, y no pasa por aquí."""

    target = _locate_event(score, anchor)
    op = EditOp.SET_EVENT_KIND
    payload = _require_mapping(op, after)
    _require_keys(op, payload, required=_KIND_KEYS, allowed=_KIND_KEYS)
    kind, pitch, hidden = payload["kind"], payload["pitch"], payload[_HIDDEN_KEY]
    if not isinstance(hidden, bool):
        raise InvalidEditPayload(f"'hidden' debe ser booleano: {hidden!r}")
    if kind == EventKind.NOTE.value:
        _check_pitch(pitch)
        if hidden:
            raise InvalidEditPayload("solo un silencio puede ser invisible ('hidden')")
    elif kind == EventKind.REST.value:
        if pitch is not None:
            raise InvalidEditPayload("un silencio no lleva 'pitch'")
    else:
        raise InvalidEditPayload(f"SetEventKind solo admite kind 'note' o 'rest': {kind!r}")
    if not (target.kind is EventKind.REST and target.hidden):
        raise InvalidEditPayload(
            "SetEventKind solo se aplica a un hueco (un silencio invisible): una nota o un "
            "silencio que se ve se corrigen con las demás operaciones"
        )
    if hidden:
        raise InvalidEditPayload("SetEventKind no cambia nada: el evento ya es un hueco")
    # Lo que se escribe en el hueco lleva su figura: ha de ser una que admiten las ediciones
    # (ADR-0017), como la de una nota insertada. Un hueco importado puede no serlo.
    try:
        _check_duration(None if target.duration_beats is None else str(target.duration_beats))
    except InvalidEditPayload as exc:
        raise InvalidEditPayload(
            f"la figura del hueco no se admite en una edición ({exc}): cámbiala antes"
        ) from exc
    events = [e for e in _locate_measure(score, anchor).events if e.voice == anchor.voice]
    following = anchor.event_index + 1
    if (
        kind == EventKind.NOTE.value
        and following < len(events)
        and events[following].kind is EventKind.NOTE
        and events[following].is_chord
    ):
        raise InvalidEditPayload(
            "la nota que sigue al hueco es de un acorde ('is_chord'): una nota en el hueco se "
            "uniría a su acorde"
        )


def _check_slur_ends_free(score: ScoreIR, anchor: Anchor, after: Mapping[str, Any]) -> None:
    """Un extremo de ligadura insertado no puede repetir uno de la parte: el `number` identifica
    la ligadura dentro de su parte (ADR-0031), y dos inicios iguales no se sabría emparejarlos."""

    wanted = {(slur["type"], slur["number"]) for slur in after.get("slurs") or ()}
    if not wanted:
        return
    taken = {
        (slur.type.value, slur.number)
        for staff in score.parts[anchor.part].staves
        for measure in staff.measures
        for event in measure.events
        for slur in event.slurs
    }
    repeated = sorted(wanted & taken)
    if repeated:
        ends = ", ".join(f"{kind} {number}" for kind, number in repeated)
        raise InvalidEditPayload(f"la parte ya tiene esos extremos de ligadura: {ends}")


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate_after(
    score: ScoreIR,
    anchor: Anchor,
    op: EditOp,
    after: Mapping[str, Any] | None,
) -> None:
    """Comprueba que `after` sea coherente con `op` sobre el estado `score`.

    Lanza `InvalidEditPayload` si el contenido no es válido e `IndexError` si el ancla
    no apunta a un compás o evento existente.
    """

    if op in MARK_EDIT_OPS:
        validate_mark_after(score, anchor, op, after)
        return
    if op in METER_EDIT_OPS:
        validate_meter_after(score, anchor, op, after)
        return

    if op is EditOp.DELETE_EVENT:
        _check_delete(score, anchor, after)
        return
    if op is EditOp.SET_EVENT_KIND:
        _check_event_kind(score, anchor, after)
        return

    if op in (EditOp.SET_CLEF, EditOp.SET_KEY, EditOp.INSERT_EVENT):
        _locate_measure(score, anchor)
        payload = _require_mapping(op, after)
        if op is EditOp.SET_CLEF:
            _check_clef(op, payload)
        elif op is EditOp.SET_KEY:
            _check_key(op, payload)
        else:
            _check_insert(op, anchor, payload)
            _check_insert_place(score, anchor, payload)
            _check_slur_ends_free(score, anchor, payload)
        return

    target = _locate_event(score, anchor)
    payload = _require_mapping(op, after)
    if op is EditOp.SET_DURATION:
        _require_keys(
            op,
            payload,
            required=frozenset({"duration_beats"}),
            allowed=frozenset({"duration_beats"}),
        )
        _check_duration(payload["duration_beats"])
        return

    if target.kind is not EventKind.NOTE:
        raise InvalidEditPayload(f"{op.value} solo se aplica a notas, no a '{target.kind.value}'")

    if op is EditOp.SET_PITCH:
        _require_keys(op, payload, required=frozenset({"pitch"}), allowed=frozenset({"pitch"}))
        _check_pitch(payload["pitch"])
        return

    if op is EditOp.SET_ACCIDENTAL:
        _require_keys(
            op, payload, required=frozenset({"accidental"}), allowed=frozenset({"accidental"})
        )
        raw = payload["accidental"]
        if raw is not None and (not isinstance(raw, str) or raw not in _EDIT_ACCIDENTALS):
            raise InvalidEditPayload(
                f"alteración no válida: {raw!r} "
                f"(admitidas: null, {', '.join(repr(key) for key in sorted(_EDIT_ACCIDENTALS))})"
            )
        try:
            result = _apply_accidental(target.pitch, payload)
        except ValueError as exc:
            raise InvalidEditPayload(str(exc)) from exc
        if not is_canonical_pitch(result):
            raise InvalidEditPayload(f"la altura resultante no es válida: {result!r}")
        return

    raise InvalidEditPayload(f"operación no admitida: {op.value}")


def normalize_accidental(value: object) -> str | None:
    """Forma canónica (``""``, ``#``, ``##``, ``b``, ``bb``) de una alteración, o None.

    Acepta los alias que interpreta la proyección (``"natural"``, ``"sharp"``, ``"x"``…);
    ``None`` equivale a sin alteración. Devuelve None si el valor no es una alteración.
    """

    if value is None:
        return ""
    if not isinstance(value, str):
        return None
    return _ACCIDENTAL_MAP.get(value.strip().lower())


def _accidental_of(pitch: str | None) -> str | None:
    if pitch is None:
        return None
    match = _PITCH_RE.match(pitch.strip())
    if match is None:
        return None
    raw = match.group(2) or ""
    return _ACCIDENTAL_MAP.get(raw.lower(), raw)


def _event_snapshot(event: Event) -> dict[str, Any]:
    primitive = event.to_primitive()
    snapshot = {
        key: primitive[key]
        for key in ("kind", "pitch", "duration_beats", "tie", "is_chord", "bbox", "confidence")
    }
    snapshot.update(
        {key: primitive[key] for key in (*_EVENT_MARK_KEYS, _HIDDEN_KEY) if key in primitive}
    )
    return snapshot


def _next_in_chord(score: ScoreIR, anchor: Anchor) -> dict[str, Any]:
    """Lo que tiene como nota del acorde la que sigue a la primera (ADR-0055 §3): lo que cambia
    al pasar a ser la primera, para que la compensatoria lo devuelva."""

    following = _locate_event(score, replace(anchor, event_index=anchor.event_index + 1))
    return {
        "duration_beats": (
            None if following.duration_beats is None else str(following.duration_beats)
        ),
        "articulations": [a.value for a in following.articulations],
        "fermata": following.fermata,
        "slurs": [slur.to_primitive() for slur in following.slurs],
    }


def snapshot_before(
    score: ScoreIR,
    anchor: Anchor,
    op: EditOp,
    after: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Instantánea del estado que la edición va a modificar (el `before` del servidor).

    Es exactamente lo que necesita `create_inverse_edit` para restaurar el estado previo.
    `InsertEvent` no modifica nada existente y devuelve None. Las operaciones de marcas
    (ADR-0039) necesitan además el `after` ya validado: dice qué posición o qué marca fijan.
    Borrar la primera nota de un acorde con `keep_chord` guarda también lo que tenía la nota
    siguiente (`next_in_chord`, ADR-0055).
    """

    if op in MARK_EDIT_OPS:
        return snapshot_mark_before(score, anchor, op, after)
    if op in METER_EDIT_OPS:
        return snapshot_meter_before(score, anchor, op, after)
    if op is EditOp.INSERT_EVENT:
        return None
    if op is EditOp.SET_CLEF:
        clef: Clef | None = _locate_measure(score, anchor).clef
        return {"clef": None if clef is None else clef.to_primitive()}
    if op is EditOp.SET_KEY:
        key: KeySignature | None = _locate_measure(score, anchor).key_signature
        return {"key_signature": None if key is None else key.to_primitive()}

    target = _locate_event(score, anchor)
    if op is EditOp.SET_PITCH:
        return {"pitch": target.pitch}
    if op is EditOp.SET_DURATION:
        duration = target.duration_beats
        return {"duration_beats": None if duration is None else str(duration)}
    if op is EditOp.SET_ACCIDENTAL:
        return {"accidental": _accidental_of(target.pitch)}
    if op is EditOp.SET_EVENT_KIND:
        return _kind_state(target)
    snapshot = _event_snapshot(target)
    if op is EditOp.DELETE_EVENT and after is not None and after.get(KEEP_CHORD) is True:
        snapshot[NEXT_IN_CHORD] = _next_in_chord(score, anchor)
    return snapshot


def has_complete_before(edit: EditEvent) -> bool:
    """Indica si `edit.before` basta para que su evento inverso restaure el estado exacto.

    Las ediciones guardadas antes de ADR-0017 pueden carecer de él (el cliente podía
    enviar `before: null`); deshacerlas corrompería la sesión.
    """

    before = edit.before
    if edit.op is EditOp.INSERT_EVENT:
        return True
    if before is None:
        return False
    keys = before.keys()
    if edit.op is EditOp.SET_PITCH:
        return "pitch" in keys
    if edit.op is EditOp.SET_DURATION:
        return "duration_beats" in keys
    if edit.op is EditOp.SET_ACCIDENTAL:
        return "accidental" in keys or "pitch" in keys
    if edit.op is EditOp.DELETE_EVENT:
        keeps_chord = edit.after is not None and edit.after.get(KEEP_CHORD) is True
        return _DELETE_SNAPSHOT_KEYS.issubset(keys) and (
            not keeps_chord or isinstance(before.get(NEXT_IN_CHORD), Mapping)
        )
    if edit.op is EditOp.SET_EVENT_KIND:
        return _KIND_KEYS.issubset(keys)
    if edit.op is EditOp.SET_CLEF:
        return "clef" in keys or "sign" in keys
    if edit.op is EditOp.SET_KEY:
        return not {"key_signature", "key", "fifths"}.isdisjoint(keys)
    if edit.op in MARK_EDIT_OPS:
        return has_complete_mark_before(edit.op, before)
    if edit.op in METER_EDIT_OPS:
        return has_complete_meter_before(edit.op, before)
    return False
