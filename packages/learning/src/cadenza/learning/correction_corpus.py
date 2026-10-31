"""Corpus de correcciones por nota para la capa de sugerencias (#255, #256).

Para cada evento que leyó el OMR, el corpus guarda lo que leyó, su corrección (o
ninguna) y su contexto: armadura, compás y clave vigentes, posición en el compás, lo que
le sobra o le falta al compás y las notas vecinas. Las correcciones salen de la misma
alineación que `derive_edit_events`, de modo que cada edición derivada está en un
registro y solo en uno:

- `event`: un evento leído, con su corrección (alteración, altura, duración o borrado).
- `insertion`: un evento de la verdad que falta, delante del evento leído de su ancla.
- `measure`: la clave o la armadura de un compás, si hay que corregirlas.

El ancla de cada registro es relativa al estado leído (`seq` 0, ADR-0011). El contexto
solo usa lo leído, porque es lo que la capa verá; la verdad solo está en `correction`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Any, Final

from cadenza.domain import (
    Anchor,
    Clef,
    EditOp,
    Event,
    EventKind,
    KeySignature,
    Measure,
    ScoreIR,
    TimeSignature,
)

from .alignment import align_voice_events, classify_pitch_change, split_pitch

CORPUS_FORMAT_VERSION: Final[int] = 1
DEFAULT_TEST_FRACTION: Final[float] = 0.2

_SHARPS_ORDER: Final[str] = "FCGDAEB"
_FLATS_ORDER: Final[str] = "BEADGCF"


def assign_split(
    incipit_id: str, *, seed: int, test_fraction: float = DEFAULT_TEST_FRACTION
) -> str:
    """Partición fija de un incipit: `test` o `train`.

    Depende solo del identificador y de la semilla, no del resto de la muestra: un incipit
    cae siempre del mismo lado, también si la muestra crece o si se reentrena con otras.
    """
    if not 0.0 < test_fraction < 1.0:
        raise ValueError(f"test_fraction debe estar entre 0 y 1, no {test_fraction}")
    digest = hashlib.sha256(f"{seed}:{incipit_id}".encode()).digest()
    position = int.from_bytes(digest[:8], "big") / 2**64
    return "test" if position < test_fraction else "train"


def key_accidental(step: str, fifths: int) -> str:
    """Alteración que la armadura impone a una letra: `#`, `b` o ninguna."""
    if fifths > 0 and step in _SHARPS_ORDER[:fifths]:
        return "#"
    if fifths < 0 and step in _FLATS_ORDER[: abs(fifths)]:
        return "b"
    return ""


def _clef_name(clef: Clef | None) -> str | None:
    if clef is None:
        return None
    octave = f"{clef.octave_change:+d}" if clef.octave_change else ""
    return f"{clef.sign}{clef.line}{octave}"


def _beats(value: Fraction | None) -> str | None:
    return None if value is None else str(value)


def _read_event(event: Event) -> dict[str, Any]:
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
    """Lo que avanza el tiempo de su voz: una nota de acorde suena con la anterior."""
    if event.is_chord or event.duration_beats is None:
        return Fraction(0)
    return event.duration_beats


def _event_correction(read: Event, truth: Event) -> dict[str, Any] | None:
    """La corrección de un evento alineado, en el orden de `derive_edit_events`."""
    ops: list[str] = []
    correction: dict[str, Any] = {}
    pitch_op = classify_pitch_change(read.pitch, truth.pitch)
    if pitch_op is not None:
        ops.append(pitch_op.value)
        correction["pitch"] = truth.pitch
        if pitch_op is EditOp.SET_ACCIDENTAL:
            correction["accidental"] = {
                "before": split_pitch(read.pitch)[1],
                "after": split_pitch(truth.pitch)[1],
            }
    if read.duration_beats != truth.duration_beats:
        ops.append(EditOp.SET_DURATION.value)
        correction["duration_beats"] = _beats(truth.duration_beats)
    if not ops:
        return None
    return {"ops": ops, **correction}


def _accidental_context(
    event: Event | None, fifths: int, earlier: Sequence[Event]
) -> dict[str, Any]:
    """La alteración leída frente a la armadura y a la última de su altura en el compás."""
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


def _measure_correction(read: Measure, truth: Measure) -> dict[str, Any] | None:
    """La clave y la armadura de un compás, como las corrige `derive_edit_events`."""
    ops: list[str] = []
    correction: dict[str, Any] = {}
    if read.clef != truth.clef and truth.clef is not None:
        ops.append(EditOp.SET_CLEF.value)
        correction["clef"] = truth.clef.to_primitive()
    if read.key_signature != truth.key_signature and truth.key_signature is not None:
        ops.append(EditOp.SET_KEY.value)
        correction["key_fifths"] = truth.key_signature.fifths
    if not ops:
        return None
    return {"ops": ops, **correction}


@dataclass(frozen=True, slots=True)
class _VoiceInMeasure:
    """Lo leído de una voz en un compás, con lo vigente y su lugar en el pentagrama."""

    events: tuple[Event, ...]
    sequence: tuple[Event, ...]  # la voz entera a lo largo del pentagrama
    first: int  # posición en `sequence` del primer evento de este compás
    key_fifths: int
    measure_context: dict[str, Any]

    def context(self, index: int, onset: Fraction, event: Event | None) -> dict[str, Any]:
        """Contexto del evento leído `index`, o del hueco delante de él si `event` es None."""
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


def _record(
    *,
    kind: str,
    incipit_id: str,
    split: str,
    verified: bool,
    aligned: bool,
    anchor: Anchor,
    read: dict[str, Any] | None,
    correction: dict[str, Any] | None,
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "format_version": CORPUS_FORMAT_VERSION,
        "incipit_id": incipit_id,
        "split": split,
        "verified": verified,
        "record": kind,
        "aligned": aligned,
        "anchor": {
            "part": anchor.part,
            "staff": anchor.staff,
            "measure": anchor.measure,
            "voice": anchor.voice,
            "event_index": anchor.event_index,
        },
        "read": read,
        "correction": correction,
        "context": context,
    }


def build_correction_records(
    predicted: ScoreIR,
    ground_truth: ScoreIR,
    *,
    incipit_id: str,
    split: str,
    verified: bool,
) -> list[dict[str, Any]]:
    """Registros del corpus de un incipit: uno por evento leído, inserción y compás.

    `verified` dice si `materialize(predicted, derive_edit_events(...))` reproduce la
    verdad: solo en ese caso las correcciones del incipit son etiquetas de confianza. Los
    eventos de un compás leído de más no tienen verdad con que alinearse: van sin
    corrección y con `aligned` falso.
    """
    records: list[dict[str, Any]] = []

    for part_idx, part in enumerate(predicted.parts):
        truth_staves = (
            ground_truth.parts[part_idx].staves if part_idx < len(ground_truth.parts) else ()
        )
        for staff_idx, staff in enumerate(part.staves):
            truth_measures = (
                truth_staves[staff_idx].measures if staff_idx < len(truth_staves) else ()
            )
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
                truth = truth_measures[m_idx] if m_idx < len(truth_measures) else None
                capacity = time.quarter_length if time is not None else None
                base = Anchor(
                    part=part_idx,
                    staff=staff_idx,
                    measure=measure.number,
                    voice=0,
                    event_index=0,
                    staff_id=staff.id,
                )

                measure_fix = None if truth is None else _measure_correction(measure, truth)
                if measure_fix is not None:
                    records.append(
                        _record(
                            kind="measure",
                            aligned=True,
                            anchor=base,
                            read={
                                "clef": _clef_name(measure.clef),
                                "key_fifths": (
                                    None
                                    if measure.key_signature is None
                                    else measure.key_signature.fifths
                                ),
                            },
                            correction=measure_fix,
                            context=None,
                            incipit_id=incipit_id,
                            split=split,
                            verified=verified,
                        )
                    )

                truth_voices = {e.voice for e in truth.events} if truth is not None else set()
                voices = sorted({e.voice for e in measure.events} | truth_voices) or [0]
                for voice in voices:
                    events = tuple(e for e in measure.events if e.voice == voice)
                    filled = sum((_advances(e) for e in events), Fraction(0))
                    first = consumed.get(voice, 0)
                    consumed[voice] = first + len(events)
                    voice_view = _VoiceInMeasure(
                        events=events,
                        sequence=sequences.get(voice, ()),
                        first=first,
                        key_fifths=key.fifths,
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
                    pairs: list[tuple[Event | None, Event | None]] = (
                        [(event, None) for event in events]
                        if truth is None
                        else align_voice_events(
                            events, [e for e in truth.events if e.voice == voice]
                        )
                    )
                    index = 0
                    onset = Fraction(0)
                    for read, wanted in pairs:
                        anchor = replace(base, voice=voice, event_index=index)
                        if read is None:
                            assert wanted is not None
                            records.append(
                                _record(
                                    kind="insertion",
                                    aligned=True,
                                    anchor=anchor,
                                    read=None,
                                    correction={
                                        "ops": [EditOp.INSERT_EVENT.value],
                                        "event": _read_event(wanted),
                                    },
                                    context=voice_view.context(index, onset, None),
                                    incipit_id=incipit_id,
                                    split=split,
                                    verified=verified,
                                )
                            )
                            continue
                        if truth is None:
                            correction = None
                        elif wanted is None:
                            correction = {"ops": [EditOp.DELETE_EVENT.value]}
                        else:
                            correction = _event_correction(read, wanted)
                        records.append(
                            _record(
                                kind="event",
                                aligned=truth is not None,
                                anchor=anchor,
                                read=_read_event(read),
                                correction=correction,
                                context=voice_view.context(index, onset, read),
                                incipit_id=incipit_id,
                                split=split,
                                verified=verified,
                            )
                        )
                        onset += _advances(read)
                        index += 1
    return records
