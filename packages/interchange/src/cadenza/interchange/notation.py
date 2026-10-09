"""Puente canónico de notación: MusicXML/MEI/**kern ↔ `ScoreIR` (music21).

Esta es la única frontera de parseo/serialización simbólica del sistema. El
dominio permanece puro: `music21` solo vive aquí. El alcance cubierto es el
corpus objetivo (monofónico y piano simple); la notación muy densa (orquesta,
manuscritos históricos) queda fuera.
"""

from __future__ import annotations

import re
from fractions import Fraction
from pathlib import Path
from typing import Any

from cadenza.domain import (
    Clef,
    Event,
    EventKind,
    KeySignature,
    Measure,
    Part,
    ScoreIR,
    Staff,
    Tie,
    TimeSignature,
)
from music21 import chord, clef, converter, key, layout, meter, midi, musicxml, note, stream, tie

_MAX_DENOMINATOR = 1000


class InterchangeError(ValueError):
    """No se pudo interpretar o serializar una partitura."""


def _register_converters() -> None:
    """Registra los importadores de MEI/**kern de converter21 si está instalado."""

    try:
        import converter21
    except ImportError:  # pragma: no cover - depende del extra opcional
        return
    import music21.metadata

    if not hasattr(music21.metadata.Metadata, "_convertValue"):
        music21.metadata.Metadata._convertValue = staticmethod(
            music21.metadata.Metadata.convertValue
        )
    converter21.register()  # pragma: no cover - depende del extra opcional


def _pitch_name(element: Any) -> str | None:
    """Nombre de altura normalizado al vocabulario del dominio (``Eb4``)."""

    pitch = getattr(element, "pitch", None)
    if pitch is None:
        return None
    return str(pitch.nameWithOctave).replace("-", "b")


def _duration(element: Any) -> Fraction | None:
    quarter_length = getattr(element, "quarterLength", None)
    if quarter_length is None:
        return None
    return Fraction(quarter_length).limit_denominator(_MAX_DENOMINATOR)


def _event_tie(pitch_source: Any) -> Tie | None:
    tie_obj = getattr(pitch_source, "tie", None)
    if tie_obj is None:
        return None
    tie_type = getattr(tie_obj, "type", None)
    if not tie_type:
        return None
    try:
        return Tie(str(tie_type))
    except ValueError:
        return None


def _events_from_measure(measure: Any) -> list[Event]:
    events: list[Event] = []
    voices = list(getattr(measure, "voices", ()))
    if voices:
        for voice_index, voice in enumerate(voices):
            events.extend(_events_from_elements(voice.notesAndRests, voice_index))
    else:
        events.extend(_events_from_elements(measure.notesAndRests, 0))
    return events


def _events_from_elements(elements: Any, voice: int) -> list[Event]:
    events: list[Event] = []
    for element in elements:
        if isinstance(element, chord.Chord):
            for i, chord_note in enumerate(element.notes):
                events.append(_note_event(chord_note, element, voice, is_chord=(i > 0)))
        else:
            events.append(_note_event(element, element, voice, is_chord=False))
    return events


def _note_event(
    pitch_source: Any,
    duration_source: Any,
    voice: int,
    is_chord: bool = False,
) -> Event:
    is_rest = isinstance(pitch_source, note.Rest)
    return Event(
        kind=EventKind.REST if is_rest else EventKind.NOTE,
        voice=voice,
        pitch=None if is_rest else _pitch_name(pitch_source),
        duration_beats=_duration(duration_source),
        tie=None if is_rest else _event_tie(pitch_source),
        is_chord=is_chord,
    )


def _measure_signature(measure: Any) -> TimeSignature | None:
    signature = measure.timeSignature
    if signature is None:
        signature = measure.getContextByClass(meter.TimeSignature)
    if signature is None:
        return None
    return TimeSignature(int(signature.numerator), int(signature.denominator))


def _measure_clef(measure: Any, is_first: bool = False) -> Clef | None:
    clef_obj = measure.clef
    if clef_obj is None:
        clefs = list(measure.getElementsByClass(clef.Clef))
        if clefs:
            clef_obj = clefs[0]
    if clef_obj is None and is_first:
        clef_obj = measure.getContextByClass(clef.Clef)
    if clef_obj is None:
        return None
    sign = getattr(clef_obj, "sign", None)
    if not sign:
        return None
    line = getattr(clef_obj, "line", 2)
    octave_change = getattr(clef_obj, "octaveChange", 0)
    return Clef(sign=str(sign), line=int(line), octave_change=int(octave_change or 0))


def _measure_key_signature(measure: Any, is_first: bool = False) -> KeySignature | None:
    key_obj = measure.keySignature
    if key_obj is None:
        keys = list(measure.getElementsByClass(key.KeySignature))
        if keys:
            key_obj = keys[0]
    if key_obj is None and is_first:
        key_obj = measure.getContextByClass(key.KeySignature)
    if key_obj is None:
        return None
    fifths = getattr(key_obj, "sharps", None)
    if fifths is None:
        return None
    mode = getattr(key_obj, "mode", None)
    return KeySignature(fifths=int(fifths), mode=str(mode) if mode is not None else None)


def _measures(part: Any) -> tuple[Measure, ...]:
    found = list(part.getElementsByClass(stream.Measure))
    measures: list[Measure] = []
    zero_count = sum(1 for m in found if getattr(m, "number", None) == 0)
    has_unassigned_measure_numbers = zero_count > 1

    for position, measure in enumerate(found, start=1):
        if has_unassigned_measure_numbers:
            number = position
        else:
            number = measure.number if isinstance(measure.number, int) else position
        is_first = position == 1
        measures.append(
            Measure(
                number=number,
                events=tuple(_events_from_measure(measure)),
                time_signature=_measure_signature(measure),
                clef=_measure_clef(measure, is_first=is_first),
                key_signature=_measure_key_signature(measure, is_first=is_first),
            )
        )
    return tuple(measures)


def _group_parts(parsed: stream.Score) -> list[list[stream.Part]]:
    raw_parts = list(parsed.parts)
    if not raw_parts:
        return []

    staff_groups = list(parsed.getElementsByClass(layout.StaffGroup))
    grouped: list[list[stream.Part]] = []
    assigned: set[int] = set()

    for sg in staff_groups:
        sg_parts = [p for p in sg if isinstance(p, stream.Part) and p in raw_parts]
        if sg_parts:
            grouped.append(sg_parts)
            for p in sg_parts:
                assigned.add(id(p))

    remaining = [p for p in raw_parts if id(p) not in assigned]
    idx = 0
    while idx < len(remaining):
        curr = remaining[idx]
        if isinstance(curr, stream.PartStaff):
            m = re.match(r"^(.*?)-Staff\d+$", str(curr.id))
            prefix = m.group(1) if m else str(curr.id)
            cluster = [curr]
            j = idx + 1
            while j < len(remaining):
                next_p = remaining[j]
                if isinstance(next_p, stream.PartStaff):
                    m_next = re.match(r"^(.*?)-Staff\d+$", str(next_p.id))
                    next_prefix = m_next.group(1) if m_next else str(next_p.id)
                    if next_prefix == prefix:
                        cluster.append(next_p)
                        j += 1
                        continue
                break
            grouped.append(cluster)
            idx = j
        else:
            grouped.append([curr])
            idx += 1
    return grouped


def music21_stream_to_score_ir(parsed: Any) -> ScoreIR:
    """Convierte un `music21` `Stream`/`Score`/`Part` en un `ScoreIR` neutral."""

    if isinstance(parsed, stream.Opus):
        if not parsed.scores:
            return ScoreIR(parts=())
        parsed = parsed.scores[0]

    if not isinstance(parsed, stream.Score):
        raw_part = parsed
        staff = Staff(id="part-0-staff-0", measures=_measures(raw_part))
        return ScoreIR(parts=(Part(id="part-0", staves=(staff,)),))

    part_groups = _group_parts(parsed)
    parts: list[Part] = []
    for part_index, p_group in enumerate(part_groups):
        staves: list[Staff] = []
        for staff_index, raw_staff in enumerate(p_group):
            staff_id = f"part-{part_index}-staff-{staff_index}"
            staves.append(Staff(id=staff_id, measures=_measures(raw_staff)))
        parts.append(Part(id=f"part-{part_index}", staves=tuple(staves)))
    return ScoreIR(parts=tuple(parts))


def musicxml_to_score_ir(xml_text: str) -> ScoreIR:
    """Convierte un documento MusicXML en un `ScoreIR` neutral."""

    try:
        parsed = converter.parseData(xml_text, format="musicxml")
    except Exception as exc:  # pragma: no cover - mensaje accionable
        raise InterchangeError(f"MusicXML no interpretable: {exc}") from exc
    return music21_stream_to_score_ir(parsed)


def read_score(path: Path) -> ScoreIR:
    """Lee cualquier formato soportado por music21 (MusicXML, MEI, **kern)."""

    _register_converters()
    if not path.is_file():
        raise FileNotFoundError(f"score not found: {path}")
    try:
        parsed = converter.parse(str(path))
    except Exception as exc:  # pragma: no cover - mensaje accionable
        raise InterchangeError(f"partitura no interpretable: {path}: {exc}") from exc
    return music21_stream_to_score_ir(parsed)


def _to_music21_pitch(pitch: str) -> str:
    """Traduce la altura del dominio (``Eb4``) al vocabulario de music21 (``E-4``)."""

    return pitch.replace("b", "-")


def _build_voice_elements(events: list[Event]) -> list[tuple[float, Any]]:
    elements: list[tuple[float, Any]] = []
    offset = 0.0
    i = 0
    while i < len(events):
        ev = events[i]
        dur = float(ev.duration_beats) if ev.duration_beats is not None else 1.0
        if ev.kind is EventKind.REST or ev.pitch is None:
            r = note.Rest(quarterLength=dur)
            elements.append((offset, r))
            offset += dur
            i += 1
        else:
            chord_notes = [ev]
            j = i + 1
            while j < len(events) and events[j].is_chord and events[j].kind is EventKind.NOTE:
                chord_notes.append(events[j])
                j += 1
            if len(chord_notes) > 1:
                m21_notes = []
                for cn in chord_notes:
                    n = note.Note(_to_music21_pitch(cn.pitch or "C4"))
                    if cn.tie is not None:
                        n.tie = tie.Tie(cn.tie.value)
                    m21_notes.append(n)
                ch = chord.Chord(m21_notes, quarterLength=dur)
                elements.append((offset, ch))
            else:
                n = note.Note(_to_music21_pitch(ev.pitch), quarterLength=dur)
                if ev.tie is not None:
                    n.tie = tie.Tie(ev.tie.value)
                elements.append((offset, n))
            offset += dur
            i = j
    return elements


def _build_measure(measure: Measure) -> Any:
    built = stream.Measure(number=measure.number)
    if measure.clef is not None:
        try:
            built.insert(
                0,
                clef.clefFromString(
                    f"{measure.clef.sign}{measure.clef.line}",
                    octaveShift=measure.clef.octave_change,
                ),
            )
        except Exception:
            c = clef.Clef()
            c.sign = measure.clef.sign
            c.line = measure.clef.line
            c.octaveChange = measure.clef.octave_change
            built.insert(0, c)
    if measure.key_signature is not None:
        k = key.KeySignature(measure.key_signature.fifths)
        if measure.key_signature.mode is not None:
            k.mode = measure.key_signature.mode
        built.insert(0, k)
    if measure.time_signature is not None:
        signature = measure.time_signature
        built.insert(0, meter.TimeSignature(f"{signature.beats}/{signature.beat_type}"))

    by_voice: dict[int, list[Event]] = {}
    for event in measure.events:
        by_voice.setdefault(event.voice, []).append(event)

    if len(by_voice) <= 1:
        for off, el in _build_voice_elements(list(measure.events)):
            built.insert(off, el)
    else:
        for voice_key, v_events in sorted(by_voice.items()):
            v = stream.Voice(id=str(voice_key + 1))
            for off, el in _build_voice_elements(v_events):
                v.insert(off, el)
            built.insert(0.0, v)
    return built


def score_ir_to_music21(score: ScoreIR) -> stream.Score:
    """Convierte un `ScoreIR` a un objeto `music21.stream.Score` estructurado."""

    out = stream.Score()
    for part_index, part in enumerate(score.parts):
        if len(part.staves) > 1:
            part_staffs: list[stream.PartStaff] = []
            for staff_index, staff in enumerate(part.staves):
                p_staff = stream.PartStaff(
                    id=f"{part.id or f'P{part_index + 1}'}-Staff{staff_index + 1}"
                )
                p_staff.partName = part.id
                for measure in staff.measures:
                    p_staff.append(_build_measure(measure))
                part_staffs.append(p_staff)
                out.insert(0, p_staff)
            sg = layout.StaffGroup(part_staffs, name=part.id, symbol="brace")
            out.insert(0, sg)
        else:
            built_part = stream.Part(id=part.id or f"P{part_index + 1}")
            for staff in part.staves:
                for measure in staff.measures:
                    built_part.append(_build_measure(measure))
            out.insert(0, built_part)
    return out


def score_ir_to_musicxml(score: ScoreIR) -> str:
    """Serializa un `ScoreIR` a MusicXML 4.0 (base para la exportación, D11)."""

    out = score_ir_to_music21(score)
    exported: bytes = musicxml.m21ToXml.GeneralObjectExporter(out).parse()
    return exported.decode("utf-8")


def score_ir_to_midi(score: ScoreIR) -> bytes:
    """Serializa un `ScoreIR` a bytes en formato MIDI 1.0 (Issue #12, ADR-0010)."""

    out = score_ir_to_music21(score)
    mf = midi.translate.streamToMidiFile(out)
    return bytes(mf.writestr())
