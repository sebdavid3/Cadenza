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
from collections import Counter
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
    Staff,
    TimeSignature,
)

from .alignment import align_incipit_voice, classify_pitch_change, split_pitch

CORPUS_FORMAT_VERSION: Final[int] = 2
"""La 2 alinea cada voz en todo el pentagrama y añade los registros `barline` (#466)."""
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
    """Registros del corpus de un incipit: uno por evento leído, inserción, compás y barra.

    `verified` dice si `replay_edits(predicted, derive_edit_events(...))` reproduce la
    verdad (cada edición, válida para la API, #456): solo en ese caso las correcciones del
    incipit son etiquetas de confianza.

    Los eventos de cada voz se alinean con la verdad en todo el pentagrama, no compás a compás
    (#466, ADR-0075): una barra de compás que HOMR no leyó (o leyó de más) es un registro
    `barline`, y las notas que quedaron al otro lado de ella están bien leídas. Las anclas siguen
    en lo leído. Sin pentagrama en la verdad, lo leído va sin corrección y con `aligned` falso.
    """
    records: list[dict[str, Any]] = []

    for part_idx, part in enumerate(predicted.parts):
        truth_staves = (
            ground_truth.parts[part_idx].staves if part_idx < len(ground_truth.parts) else ()
        )
        for staff_idx, staff in enumerate(part.staves):
            truth_staff = truth_staves[staff_idx] if staff_idx < len(truth_staves) else None
            records.extend(
                _staff_records(
                    staff,
                    truth_staff,
                    part_idx=part_idx,
                    staff_idx=staff_idx,
                    incipit_id=incipit_id,
                    split=split,
                    verified=verified,
                )
            )
    return records


def _staff_records(
    staff: Staff,
    truth_staff: Staff | None,
    *,
    part_idx: int,
    staff_idx: int,
    incipit_id: str,
    split: str,
    verified: bool,
) -> list[dict[str, Any]]:
    """Los registros de un pentagrama, agrupados por compás leído: primero el de la clave y la
    armadura y después los de cada voz en orden (eventos, inserciones y barras)."""

    def record(kind: str, **fields: Any) -> dict[str, Any]:
        return _record(kind=kind, incipit_id=incipit_id, split=split, verified=verified, **fields)

    measures = staff.measures
    if not measures:
        return []
    truth_measures = truth_staff.measures if truth_staff is not None else ()
    by_measure: list[list[dict[str, Any]]] = [[] for _ in measures]
    bases = [
        Anchor(
            part=part_idx,
            staff=staff_idx,
            measure=measure.number,
            voice=0,
            event_index=0,
            staff_id=staff.id,
        )
        for measure in measures
    ]
    sequences: dict[int, tuple[Event, ...]] = {}
    for measure in measures:
        for event in measure.events:
            sequences[event.voice] = (*sequences.get(event.voice, ()), event)
    voices = sorted(
        {e.voice for m in measures for e in m.events}
        | {e.voice for m in truth_measures for e in m.events}
    ) or [0]
    events_per_voice = Counter(e.voice for m in (*measures, *truth_measures) for e in m.events)
    barline_voice = max(voices, key=lambda v: (events_per_voice[v], -v))

    # Lo vigente en cada compás leído y la clave y la armadura, compás a compás.
    in_force: list[tuple[Clef | None, KeySignature, TimeSignature | None]] = []
    clef: Clef | None = None
    key = KeySignature(fifths=0)
    time: TimeSignature | None = None
    for m_idx, measure in enumerate(measures):
        clef = measure.clef or clef
        key = measure.key_signature or key
        time = measure.time_signature or time
        in_force.append((clef, key, time))
        truth = truth_measures[m_idx] if m_idx < len(truth_measures) else None
        measure_fix = None if truth is None else _measure_correction(measure, truth)
        if measure_fix is not None:
            by_measure[m_idx].append(
                record(
                    "measure",
                    aligned=True,
                    anchor=bases[m_idx],
                    read={
                        "clef": _clef_name(measure.clef),
                        "key_fifths": (
                            None if measure.key_signature is None else measure.key_signature.fifths
                        ),
                    },
                    correction=measure_fix,
                    context=None,
                )
            )

    for voice in voices:
        read_measures = [tuple(e for e in m.events if e.voice == voice) for m in measures]
        views: list[_VoiceInMeasure] = []
        first = 0
        for m_idx, events in enumerate(read_measures):
            m_clef, m_key, m_time = in_force[m_idx]
            capacity = m_time.quarter_length if m_time is not None else None
            filled = sum((_advances(e) for e in events), Fraction(0))
            views.append(
                _VoiceInMeasure(
                    events=events,
                    sequence=sequences.get(voice, ()),
                    first=first,
                    key_fifths=m_key.fifths,
                    measure_context={
                        "clef": _clef_name(m_clef),
                        "key_fifths": m_key.fifths,
                        "time_signature": None if m_time is None else str(m_time),
                        "measure_index": m_idx,
                        "measures_in_staff": len(measures),
                        "events_in_voice": len(events),
                        "measure_beats_read": str(filled),
                        "measure_capacity_beats": _beats(capacity),
                        "measure_balance_beats": (
                            None if capacity is None else str(filled - capacity)
                        ),
                    },
                )
            )
            first += len(events)

        def onset(
            m_idx: int, index: int, voice_measures: list[tuple[Event, ...]] = read_measures
        ) -> Fraction:
            return sum((_advances(e) for e in voice_measures[m_idx][:index]), Fraction(0))

        def at(m_idx: int, index: int, voice: int = voice) -> Anchor:
            return replace(bases[m_idx], voice=voice, event_index=index)

        if truth_staff is None:
            for m_idx, events in enumerate(read_measures):
                for index, event in enumerate(events):
                    by_measure[m_idx].append(
                        record(
                            "event",
                            aligned=False,
                            anchor=at(m_idx, index),
                            read=_read_event(event),
                            correction=None,
                            context=views[m_idx].context(index, onset(m_idx, index), event),
                        )
                    )
            continue

        truth_voice = [tuple(e for e in m.events if e.voice == voice) for m in truth_measures]
        alignment = align_incipit_voice(read_measures, truth_voice)
        # Cada registro con su compás y su orden en la alineación: el par `k`, 2k + 1; una barra
        # con `p` pares delante, 2p (va delante del par que la sigue).
        placed: list[tuple[int, int, dict[str, Any]]] = []
        correction: dict[str, Any] | None
        read_fields: dict[str, Any] | None
        for k, ((read, wanted), (m_idx, index)) in enumerate(
            zip(alignment.pairs, alignment.slots, strict=True)
        ):
            if read is None:
                assert wanted is not None
                kind, read_fields, correction = (
                    "insertion",
                    None,
                    {"ops": [EditOp.INSERT_EVENT.value], "event": _read_event(wanted)},
                )
            else:
                kind, read_fields = "event", _read_event(read)
                correction = (
                    {"ops": [EditOp.DELETE_EVENT.value]}
                    if wanted is None
                    else _event_correction(read, wanted)
                )
            placed.append(
                (
                    m_idx,
                    2 * k + 1,
                    record(
                        kind,
                        aligned=True,
                        anchor=at(m_idx, index),
                        read=read_fields,
                        correction=correction,
                        context=views[m_idx].context(index, onset(m_idx, index), read),
                    ),
                )
            )
        # Las barras, una vez por pentagrama, en la voz con más eventos (en las demás serían las
        # mismas, y una voz con compases vacíos no sabe entre cuáles falta la barra).
        if voice == barline_voice:
            barlines = [
                ("missing", m, i, before)
                for (m, i), before in zip(
                    alignment.missing_barlines, alignment.missing_before, strict=True
                )
            ]
            barlines += [
                ("extra", m, 0, before)
                for m, before in zip(alignment.extra_barlines, alignment.extra_before, strict=True)
            ]
            for what, m_idx, index, before in barlines:
                placed.append(
                    (
                        m_idx,
                        2 * before,
                        record(
                            "barline",
                            aligned=True,
                            anchor=at(m_idx, index),
                            read={"barline": what == "extra"},
                            correction={"barline": what},
                            context=views[m_idx].context(index, onset(m_idx, index), None),
                        ),
                    )
                )
        for m_idx, _, voice_record in sorted(placed, key=lambda p: (p[0], p[1])):
            by_measure[m_idx].append(voice_record)

    return [r for measure_records in by_measure for r in measure_records]
