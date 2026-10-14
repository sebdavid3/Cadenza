"""Contenido de las ediciones: validación de `after` y estado previo `before` (ADR-0017, #117).

Dos reglas puras que la capa de aplicación aplica antes de persistir una edición:

- `validate_after`: el `after` debe ser coherente con su operación y expresarse en el
  vocabulario canónico del dominio (alturas como ``C#4``/``Bb3``, duraciones positivas,
  claves G/F/C, armaduras de -7 a 7). Un `after` incoherente se rechaza en lugar de
  persistirse.
- `snapshot_before`: el servidor fija `before` con una instantánea del estado sobre el
  que se aplica la edición, de modo que el evento inverso (`create_inverse_edit`)
  restaure siempre el estado exacto, sin depender de lo que envíe el cliente.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from fractions import Fraction
from typing import Any, Final

from .anchor import Anchor, EventKind
from .clef import Clef
from .edit import EditEvent, EditOp
from .key_signature import KeySignature
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

# Duraciones: hasta una longa (16 pulsos de negra) y denominadores 2^a·t con t en
# {1, 3, 5, 7} hasta 128 (fusas de tresillo, quintillo y septillo). Con ese vocabulario el
# exportador escribe MusicXML y MIDI; fuera de él, music21 rechaza duraciones como 1/17 o
# 3/1000 y tarda sin límite con duraciones enormes.
_MAX_DURATION_BEATS: Final[Fraction] = Fraction(16)
_MAX_DURATION_DENOMINATOR: Final[int] = 128
_TUPLET_FACTORS: Final[frozenset[int]] = frozenset({1, 3, 5, 7})

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

_INSERT_KEYS: Final[frozenset[str]] = frozenset(
    {"kind", "pitch", "duration_beats", "tie", "is_chord", "bbox", "confidence", "voice"}
)
_DELETE_SNAPSHOT_KEYS: Final[frozenset[str]] = frozenset({"kind", "pitch", "duration_beats"})


class InvalidEditPayload(ValueError):
    """El `after` de una edición no es coherente con su operación (ADR-0017)."""


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
    if isinstance(value, bool) or not isinstance(value, int | float | str | Fraction):
        raise InvalidEditPayload(f"duración no válida: {value!r}")
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidEditPayload(f"duración no válida: {value!r}")
    try:
        duration = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as exc:
        raise InvalidEditPayload(f"duración no válida: {value!r}") from exc
    if not 0 < duration <= _MAX_DURATION_BEATS:
        raise InvalidEditPayload(
            f"la duración debe estar entre 0 (excluido) y {_MAX_DURATION_BEATS} pulsos: "
            f"{value!r}"
        )
    tuplet = duration.denominator
    while tuplet % 2 == 0:
        tuplet //= 2
    if duration.denominator > _MAX_DURATION_DENOMINATOR or tuplet not in _TUPLET_FACTORS:
        raise InvalidEditPayload(
            f"duración no representable: {value!r} (el denominador debe ser 2^a·t con t "
            f"1, 3, 5 o 7 y como mucho {_MAX_DURATION_DENOMINATOR}, p. ej. '1/2', '1/3', "
            "'3/4')"
        )


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

    if op is EditOp.DELETE_EVENT:
        _locate_event(score, anchor)
        if after is not None:
            raise InvalidEditPayload("DeleteEvent no lleva 'after' (debe ser null)")
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
    return {
        key: primitive[key]
        for key in ("kind", "pitch", "duration_beats", "tie", "is_chord", "bbox", "confidence")
    }


def snapshot_before(score: ScoreIR, anchor: Anchor, op: EditOp) -> dict[str, Any] | None:
    """Instantánea del estado que la edición va a modificar (el `before` del servidor).

    Es exactamente lo que necesita `create_inverse_edit` para restaurar el estado previo.
    `InsertEvent` no modifica nada existente y devuelve None.
    """

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
    return _event_snapshot(target)


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
        return _DELETE_SNAPSHOT_KEYS.issubset(keys)
    if edit.op is EditOp.SET_CLEF:
        return "clef" in keys or "sign" in keys
    if edit.op is EditOp.SET_KEY:
        return not {"key_signature", "key", "fifths"}.isdisjoint(keys)
    return False
