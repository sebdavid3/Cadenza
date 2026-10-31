"""Rasgos de la capa de sugerencias: una sola función para el corpus, el entrenamiento y la
inferencia (ADR-0036 §2).

El contexto de cada evento leído es el mismo que guarda el corpus de correcciones de #255
(`cadenza.learning.build_correction_records`), calculado solo con lo leído: armadura,
compás y clave vigentes, posición en el compás, lo que le sobra o le falta al compás de su
voz, la alteración frente a la armadura y a la última de su altura en el compás, y las
notas vecinas. `discretize` lo convierte en los valores discretos con que se cuentan las
frecuencias, y las funciones `*_label` dan la etiqueta de cada corrección en cada familia.

Cambiar cualquiera de estas funciones cambia lo que se aprende: sube `FEATURE_VERSION`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Final

from cadenza.domain import Clef, EditOp, Event, EventKind, KeySignature, ScoreIR, TimeSignature

FEATURE_VERSION: Final[int] = 1

# Familias de correcciones de un evento leído (ADR-0036 §1) y la de las inserciones, que
# solo ordena candidatos de las reglas (no hay `learned.insert`).
FAMILIES: Final[tuple[str, ...]] = ("accidental", "duration", "pitch", "delete")
INSERTION: Final[str] = "insertion"
NONE_LABEL: Final[str] = "none"

_SHARPS_ORDER: Final[str] = "FCGDAEB"
_FLATS_ORDER: Final[str] = "BEADGCF"
_LETTERS: Final[str] = "CDEFGAB"
_PITCH_RE: Final[re.Pattern[str]] = re.compile(r"^([A-Ga-g])(#{1,2}|b{1,2}|-{1,2}|x)?(-?\d+)$")
_DOT_FACTORS: Final[tuple[tuple[int, Fraction], ...]] = (
    (0, Fraction(1)),
    (1, Fraction(3, 2)),
    (2, Fraction(7, 4)),
)
_MISSING: Final[str] = "-"


def split_pitch(pitch: str | None) -> tuple[str, str, str]:
    """(letra, alteración normalizada, octava) de una altura, o ``("", "", "")``.

    La misma normalización que `cadenza.learning.split_pitch`: ``-``/``b`` es bemol,
    ``x``/``##`` doble sostenido.
    """
    if pitch is None:
        return ("", "", "")
    match = _PITCH_RE.match(pitch.strip())
    if not match:
        return ("", "", "")
    accidental = match.group(2) or ""
    if accidental in ("-", "b"):
        accidental = "b"
    elif accidental in ("--", "bb"):
        accidental = "bb"
    elif accidental in ("x", "##"):
        accidental = "##"
    return (match.group(1).upper(), accidental, match.group(3))


def key_accidental(step: str, fifths: int) -> str:
    """Alteración que la armadura impone a una letra: `#`, `b` o ninguna."""
    if fifths > 0 and step in _SHARPS_ORDER[:fifths]:
        return "#"
    if fifths < 0 and step in _FLATS_ORDER[: abs(fifths)]:
        return "b"
    return ""


def diatonic_index(pitch: str | None) -> int | None:
    """Posición diatónica absoluta (letra y octava) de una altura, sin su alteración."""
    letter, _, octave = split_pitch(pitch)
    if not letter:
        return None
    return int(octave) * 7 + _LETTERS.index(letter)


def figure_of(duration: Fraction | None) -> tuple[Fraction, int] | None:
    """Figura base (potencia de dos, en negras) y puntillos de una duración, o None."""
    if duration is None or duration <= 0:
        return None
    for dots, factor in _DOT_FACTORS:
        base = duration / factor
        if base.numerator == 1 or base.denominator == 1:
            value = base.numerator if base.denominator == 1 else base.denominator
            if value & (value - 1) == 0 and Fraction(1, 64) <= base <= 8:
                return base, dots
    return None


def _clef_name(clef: Clef | None) -> str | None:
    if clef is None:
        return None
    octave = f"{clef.octave_change:+d}" if clef.octave_change else ""
    return f"{clef.sign}{clef.line}{octave}"


def _beats(value: Fraction | None) -> str | None:
    return None if value is None else str(value)


def read_event(event: Event) -> dict[str, Any]:
    """Lo leído de un evento, en la forma del campo `read` del corpus."""
    return {
        "kind": event.kind.value,
        "pitch": event.pitch,
        "duration_beats": _beats(event.duration_beats),
        "tie": None if event.tie is None else event.tie.value,
        "is_chord": event.is_chord,
        "hidden": event.hidden,
    }


def _neighbour(event: Event | None) -> dict[str, Any] | None:
    if event is None:
        return None
    return {
        "kind": event.kind.value,
        "pitch": event.pitch,
        "duration_beats": _beats(event.duration_beats),
    }


def _advances(event: Event) -> Fraction:
    if event.is_chord or event.duration_beats is None:
        return Fraction(0)
    return event.duration_beats


def _accidental_context(
    event: Event | None, fifths: int, earlier: tuple[Event, ...]
) -> dict[str, Any]:
    if event is None or event.kind is not EventKind.NOTE:
        return {
            "accidental": None,
            "key_accidental": None,
            "accidental_vs_key": None,
            "previous_accidental_same_step": None,
        }
    letter, accidental, octave = split_pitch(event.pitch)
    implied = key_accidental(letter, fifths)
    previous: str | None = None
    for other in reversed(earlier):
        other_letter, other_accidental, other_octave = split_pitch(other.pitch)
        if other.kind is EventKind.NOTE and (other_letter, other_octave) == (letter, octave):
            previous = other_accidental
            break
    return {
        "accidental": accidental,
        "key_accidental": implied,
        "accidental_vs_key": "in_key" if accidental == implied else "against_key",
        "previous_accidental_same_step": previous,
    }


Position = tuple[int, int, int, int, int]
"""(parte, pentagrama, número de compás, voz, índice del evento en la voz)."""


@dataclass(frozen=True, slots=True)
class _Voice:
    events: tuple[Event, ...]
    sequence: tuple[Event, ...]
    first: int
    key_fifths: int
    measure_context: Mapping[str, Any]
    staff_id: str

    def context(self, index: int, event: Event | None) -> dict[str, Any]:
        onset = sum((_advances(e) for e in self.events[:index]), Fraction(0))
        position = self.first + index
        prev = self.sequence[position - 1] if position > 0 else None
        after = position + 1 if event is not None else position
        nxt = self.sequence[after] if after < len(self.sequence) else None
        return {
            **self.measure_context,
            "event_index": index,
            "onset_beats": str(onset),
            **_accidental_context(event, self.key_fifths, self.events[:index]),
            "prev": _neighbour(prev),
            "next": _neighbour(nxt),
        }


@dataclass(frozen=True, slots=True)
class EventView:
    """Un evento leído con su contexto y sus rasgos discretos."""

    position: Position
    staff_id: str
    event: Event
    read: Mapping[str, Any]
    context: Mapping[str, Any]
    features: Mapping[str, str]


@dataclass(slots=True)
class ScoreFeatures:
    """Contexto y rasgos de cada evento leído de un `ScoreIR`, y de los huecos de sus voces."""

    events: dict[Position, EventView] = field(default_factory=dict)
    _voices: dict[tuple[int, int, int, int], _Voice] = field(default_factory=dict)
    _gaps: dict[Position, Mapping[str, str]] = field(default_factory=dict)

    @classmethod
    def of(cls, score: ScoreIR) -> ScoreFeatures:
        built = cls()
        for part_idx, part in enumerate(score.parts):
            for staff_idx, staff in enumerate(part.staves):
                sequences: dict[int, tuple[Event, ...]] = {}
                for measure in staff.measures:
                    for event in measure.events:
                        sequences[event.voice] = (*sequences.get(event.voice, ()), event)
                consumed: dict[int, int] = {}
                clef: Clef | None = None
                key = KeySignature(fifths=0)
                time: TimeSignature | None = None
                for m_idx, measure in enumerate(staff.measures):
                    clef = measure.clef or clef
                    key = measure.key_signature or key
                    time = measure.time_signature or time
                    capacity = time.quarter_length if time is not None else None
                    for voice in sorted({e.voice for e in measure.events}):
                        events = tuple(e for e in measure.events if e.voice == voice)
                        filled = sum((_advances(e) for e in events), Fraction(0))
                        first = consumed.get(voice, 0)
                        consumed[voice] = first + len(events)
                        view = _Voice(
                            events=events,
                            sequence=sequences.get(voice, ()),
                            first=first,
                            key_fifths=key.fifths,
                            staff_id=staff.id,
                            measure_context={
                                "clef": _clef_name(clef),
                                "key_fifths": key.fifths,
                                "time_signature": None if time is None else str(time),
                                "measure_index": m_idx,
                                "measures_in_staff": len(staff.measures),
                                "events_in_voice": len(events),
                                "measure_beats_read": str(filled),
                                "measure_capacity_beats": _beats(capacity),
                                "measure_balance_beats": (
                                    None if capacity is None else str(filled - capacity)
                                ),
                            },
                        )
                        built._voices[(part_idx, staff_idx, measure.number, voice)] = view
                        for index, event in enumerate(events):
                            position = (part_idx, staff_idx, measure.number, voice, index)
                            read = read_event(event)
                            context = view.context(index, event)
                            built.events[position] = EventView(
                                position=position,
                                staff_id=staff.id,
                                event=event,
                                read=read,
                                context=context,
                                features=discretize(read, context),
                            )
        return built

    def gap(self, position: Position) -> Mapping[str, str] | None:
        """Rasgos del hueco delante del evento `position` (o al final de su voz)."""
        cached = self._gaps.get(position)
        if cached is not None:
            return cached
        voice = self._voices.get(position[:4])
        if voice is None or not 0 <= position[4] <= len(voice.events):
            return None
        features = discretize(None, voice.context(position[4], None))
        self._gaps[position] = features
        return features

    def voice_length(self, part: int, staff: int, measure: int, voice: int) -> int | None:
        view = self._voices.get((part, staff, measure, voice))
        return None if view is None else len(view.events)


def _fraction(value: object) -> Fraction | None:
    if value is None:
        return None
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        return None


def _figure_feature(duration: object) -> tuple[str, str]:
    parsed = figure_of(_fraction(duration))
    if parsed is None:
        return (_MISSING if duration is None else f"other:{duration}", _MISSING)
    base, dots = parsed
    return (str(base), str(dots))


def _step(a: str | None, b: str | None) -> str:
    first, second = diatonic_index(a), diatonic_index(b)
    if first is None or second is None:
        return _MISSING
    return str(max(-8, min(8, second - first)))


def _text(value: object) -> str:
    if value is None:
        return _MISSING
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def discretize(read: Mapping[str, Any] | None, context: Mapping[str, Any]) -> dict[str, str]:
    """Los rasgos discretos de un evento leído (o del hueco delante de él si `read` es None).

    Solo usa lo leído (`read` y `context`, en la forma del corpus). Los metadatos del corpus
    (`aligned`, `verified`, `split`, `incipit_id`) nunca son rasgos.
    """
    pitch = None if read is None else read.get("pitch")
    letter, _, octave = split_pitch(pitch)
    figure, dots = _figure_feature(None if read is None else read.get("duration_beats"))
    onset = _fraction(context.get("onset_beats"))
    balance = _fraction(context.get("measure_balance_beats"))
    if balance is None:
        balance_sign = _MISSING
    elif balance > 0:
        balance_sign = "over"
    elif balance < 0:
        balance_sign = "under"
    else:
        balance_sign = "exact"
    prev = context.get("prev") or {}
    nxt = context.get("next") or {}
    index = int(context.get("event_index") or 0)
    count = int(context.get("events_in_voice") or 0)
    if read is None:
        place = "end" if index >= count else "gap"
    elif count <= 1:
        place = "only"
    elif index == 0:
        place = "first"
    elif index == count - 1:
        place = "last"
    else:
        place = "middle"
    prev_figure, _ = _figure_feature(prev.get("duration_beats"))
    next_figure, _ = _figure_feature(nxt.get("duration_beats"))
    return {
        "kind": "gap" if read is None else _text(read.get("kind")),
        "figure": figure,
        "dots": dots,
        "letter": letter or _MISSING,
        "octave": octave or _MISSING,
        "accidental": _text(context.get("accidental")),
        "key_accidental": _text(context.get("key_accidental")),
        "acc_vs_key": _text(context.get("accidental_vs_key")),
        "prev_acc": _text(context.get("previous_accidental_same_step")),
        "key_fifths": _text(context.get("key_fifths")),
        "time": _text(context.get("time_signature")),
        "clef": _text(context.get("clef")),
        "on_beat": _MISSING if onset is None else ("1" if onset.denominator == 1 else "0"),
        "downbeat": _MISSING if onset is None else ("1" if onset == 0 else "0"),
        "balance_sign": balance_sign,
        "balance": _text(context.get("measure_balance_beats")),
        "place": place,
        "prev_kind": _text(prev.get("kind")),
        "prev_figure": prev_figure,
        "prev_step": _step(prev.get("pitch"), pitch),
        "next_kind": _text(nxt.get("kind")),
        "next_figure": next_figure,
        "next_step": _step(pitch, nxt.get("pitch")),
        "is_chord": _text(None if read is None else read.get("is_chord")),
        "tie": _text(None if read is None else read.get("tie")),
    }


# --- Etiquetas: la misma corrección se etiqueta igual al contar y al puntuar -----------------


def accidental_label(target: str, context: Mapping[str, Any]) -> str:
    """Etiqueta de «poner la alteración `target`», relativa a la armadura y al compás.

    `=key` es la que pide la armadura, `=prev` la última de la misma nota en el compás y,
    si no es ninguna de las dos, la alteración absoluta (`abs:#`, `abs:` para natural).
    """
    if target == context.get("key_accidental"):
        return "=key"
    previous = context.get("previous_accidental_same_step")
    if previous is not None and target == previous:
        return "=prev"
    return f"abs:{target}"


def decode_accidental(label: str, context: Mapping[str, Any]) -> str | None:
    if label == "=key":
        value = context.get("key_accidental")
        return None if value is None else str(value)
    if label == "=prev":
        value = context.get("previous_accidental_same_step")
        return None if value is None else str(value)
    if label.startswith("abs:"):
        return label[4:]
    return None


def duration_label(read_duration: object, target: object) -> str | None:
    """Etiqueta de «cambiar la duración a `target`»: la razón frente a la leída (`x2`, `x1/2`)."""
    read, wanted = _fraction(read_duration), _fraction(target)
    if read is None or wanted is None or read <= 0:
        return None
    return f"x{wanted / read}"


def decode_duration(label: str, read_duration: object) -> Fraction | None:
    read = _fraction(read_duration)
    ratio = _fraction(label[1:]) if label.startswith("x") else None
    if read is None or ratio is None:
        return None
    return read * ratio


def pitch_label(read_pitch: str | None, target: str | None) -> str | None:
    """Etiqueta de «cambiar la altura a `target`»: la distancia diatónica (`+1`, `-2`)."""
    first, second = diatonic_index(read_pitch), diatonic_index(target)
    if first is None or second is None or first == second:
        return None
    return f"{second - first:+d}"


def decode_pitch(label: str, read_pitch: str | None, fifths: int) -> str | None:
    """La altura a `label` pasos diatónicos, con la alteración que pide la armadura."""
    origin = diatonic_index(read_pitch)
    try:
        distance = int(label)
    except ValueError:
        return None
    if origin is None:
        return None
    target = origin + distance
    octave, step = divmod(target, 7)
    if not 0 <= octave <= 9:
        return None
    letter = _LETTERS[step]
    return f"{letter}{key_accidental(letter, fifths)}{octave}"


def insertion_label(kind: object, duration: object) -> str | None:
    wanted = _fraction(duration)
    if kind not in ("note", "rest") or wanted is None:
        return None
    return f"{kind}:{wanted}"


def labels_from_correction(
    read: Mapping[str, Any], context: Mapping[str, Any], correction: Mapping[str, Any] | None
) -> dict[str, str]:
    """La etiqueta de cada familia aplicable a un registro `event` del corpus.

    Sin corrección, todas son `none`. Una familia que no se aplica al evento (la alteración
    de un silencio) o cuya corrección no se puede etiquetar (la razón de una duración nula)
    no aparece.
    """
    ops = set(correction.get("ops") or ()) if correction is not None else set()
    is_note = read.get("kind") == EventKind.NOTE.value
    labels: dict[str, str] = {
        "delete": "delete" if EditOp.DELETE_EVENT.value in ops else NONE_LABEL
    }
    if is_note:
        labels["accidental"] = NONE_LABEL
        labels["pitch"] = NONE_LABEL
    if _fraction(read.get("duration_beats")) not in (None, Fraction(0)):
        labels["duration"] = NONE_LABEL
    if correction is None:
        return labels
    if is_note and EditOp.SET_ACCIDENTAL.value in ops:
        accidental = correction.get("accidental") or {}
        labels["accidental"] = accidental_label(str(accidental.get("after") or ""), context)
    if is_note and EditOp.SET_PITCH.value in ops:
        label = pitch_label(read.get("pitch"), correction.get("pitch"))
        if label is None:
            del labels["pitch"]
        else:
            labels["pitch"] = label
    if "duration" in labels and EditOp.SET_DURATION.value in ops:
        label = duration_label(read.get("duration_beats"), correction.get("duration_beats"))
        if label is None:
            del labels["duration"]
        else:
            labels["duration"] = label
    return labels


def label_of_edit(
    op: EditOp, after: Mapping[str, Any] | None, view: EventView | None
) -> tuple[str, str] | None:
    """(familia, etiqueta) de una edición propuesta sobre un evento leído, o None.

    Las inserciones no son de un evento leído: se etiquetan con `insertion_label`.
    """
    if view is None:
        return None
    if op is EditOp.DELETE_EVENT:
        return ("delete", "delete")
    if after is None:
        return None
    if op is EditOp.SET_DURATION:
        label = duration_label(view.read.get("duration_beats"), after.get("duration_beats"))
        return None if label is None else ("duration", label)
    if view.event.kind is not EventKind.NOTE:
        return None
    if op is EditOp.SET_ACCIDENTAL:
        raw = after.get("accidental")
        accidental = split_pitch(f"C{'' if raw in (None, 'natural') else raw}4")[1]
        return ("accidental", accidental_label(accidental, view.context))
    if op is EditOp.SET_PITCH:
        target = after.get("pitch")
        read_letter, _, read_octave = split_pitch(view.event.pitch)
        letter, accidental, octave = split_pitch(None if target is None else str(target))
        if letter and (letter, octave) == (read_letter, read_octave):
            return ("accidental", accidental_label(accidental, view.context))
        label = pitch_label(view.event.pitch, None if target is None else str(target))
        return None if label is None else ("pitch", label)
    return None
