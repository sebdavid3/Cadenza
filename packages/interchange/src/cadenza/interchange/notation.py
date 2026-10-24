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
from music21 import (
    chord,
    clef,
    converter,
    defaults,
    key,
    layout,
    meter,
    midi,
    musicxml,
    note,
    stream,
    tie,
)

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


def _is_untimed_note(event: Event) -> bool:
    """Nota sin duración (cero o nula): así da HOMR una nota de adorno (D60, #199)."""

    return event.kind is not EventKind.REST and event.pitch is not None and not event.duration_beats


def _build_voice_elements(events: list[Event]) -> list[tuple[float, Any]]:
    """Elementos de music21 de una voz, cada uno con su instante dentro del compás.

    Una nota o un acorde sin duración se escribe como nota de adorno, que no ocupa tiempo: así
    lo dibujado suma lo mismo que el `ScoreIR`, el mapa de tiempos y el validador (D60, #199).
    Antes salía como negra, porque music21 cambia `quarterLength=0` por su duración por defecto.
    Un silencio no tiene versión de adorno en MusicXML: con duración cero sigue saliendo como
    silencio de negra.
    """

    elements: list[tuple[float, Any]] = []
    offset = 0.0
    i = 0
    while i < len(events):
        ev = events[i]
        dur = float(ev.duration_beats) if ev.duration_beats is not None else 1.0
        if ev.kind is EventKind.REST or ev.pitch is None:
            r = note.Rest(quarterLength=dur)
            elements.append((offset, r))
            # Lo que ocupa de verdad: music21 escribe como negra un silencio de duración cero,
            # y la nota de adorno que lo siga no debe caer en su mismo instante.
            offset += float(r.quarterLength)
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
                element: Any = chord.Chord(m21_notes, quarterLength=dur)
            else:
                element = note.Note(_to_music21_pitch(ev.pitch), quarterLength=dur)
                if ev.tie is not None:
                    element.tie = tie.Tie(ev.tie.value)
            if _is_untimed_note(ev):
                elements.append((offset, element.getGrace()))
            else:
                elements.append((offset, element))
                offset += dur
            i = j
    return elements


def _build_measure(measure: Measure, previous_signature: TimeSignature | None = None) -> Any:
    """Construye el compás de music21.

    La importación da a cada compás su métrica efectiva; aquí solo se escribe donde cambia
    respecto a ``previous_signature``, para no repetirla en cada compás de la partitura (#152).
    """
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
    if measure.time_signature is not None and measure.time_signature != previous_signature:
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


def _build_staff_measures(measures: tuple[Measure, ...]) -> list[Any]:
    built: list[Any] = []
    previous_signature: TimeSignature | None = None
    for index, measure in enumerate(measures):
        built_measure = _build_measure(measure, previous_signature)
        signature = measure.time_signature
        if signature is not None:
            previous_signature = signature
            # Sin silencios de relleno, music21 trata un compás incompleto como una anacrusa y
            # agrupa las barras desde el final. Solo el primero puede serlo: en los demás, lo
            # que falta va a la derecha, como al importar MusicXML (#152).
            missing = signature.quarter_length - Fraction(built_measure.highestTime)
            if index > 0 and missing > 0:
                built_measure.paddingRight = missing
        built.append(built_measure)
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
                for built_measure in _build_staff_measures(staff.measures):
                    p_staff.append(built_measure)
                part_staffs.append(p_staff)
                out.insert(0, p_staff)
            sg = layout.StaffGroup(part_staffs, name=part.id, symbol="brace")
            out.insert(0, sg)
        else:
            built_part = stream.Part(id=part.id or f"P{part_index + 1}")
            for staff in part.staves:
                for built_measure in _build_staff_measures(staff.measures):
                    built_part.append(built_measure)
            out.insert(0, built_part)
    return out


def _drop_placeholder_metadata(root: Any) -> None:
    """Quita el título y el compositor que music21 escribe si la partitura no tiene metadatos.

    El `ScoreIR` no tiene título ni autor: «Music21 Fragment» y «Music21» serían inventados (#152).
    """

    for title in root.findall("movement-title"):
        if title.text == defaults.title:
            root.remove(title)
    identification = root.find("identification")
    if identification is not None:
        for creator in identification.findall("creator"):
            if creator.text == defaults.author:
                identification.remove(creator)


def score_ir_to_musicxml(score: ScoreIR) -> str:
    """Serializa un `ScoreIR` a MusicXML 4.0 tal como está (base para la exportación, D11).

    No pasa por `GeneralObjectExporter`, que rellena los compases incompletos con silencios
    ocultos y, con `makeNotation`, reparte entre compases las notas que cruzan la barra de un
    compás sobrellenado: la partitura exportada dejaría de ser la transcrita justo donde el
    validador señala un posible error (#152). El exportador de partes sigue haciendo las
    alteraciones visibles, los corchetes de los tresillos y las barras de agrupación (salvo en
    los compases sobrellenados, que music21 no agrupa), y divide en notas ligadas dentro del
    mismo compás las duraciones que MusicXML no puede escribir con una sola figura. Los
    tresillos incompletos no se completan: se escriben con las duraciones del `ScoreIR`. Una nota
    de duración cero o nula sale como nota de adorno (D60, #199).
    """

    if not score.parts:
        raise InterchangeError("La partitura no tiene partes que exportar")
    out = score_ir_to_music21(score)
    exporter = musicxml.m21ToXml.ScoreExporter(out, makeNotation=True)
    _drop_placeholder_metadata(exporter.parse())
    exported: bytes = exporter.asBytes()
    return exported.decode("utf-8")


def score_ir_to_midi(score: ScoreIR) -> bytes:
    """Serializa un `ScoreIR` a bytes en formato MIDI 1.0 (Issue #12, ADR-0010).

    Las notas de adorno (duración cero o nula, ADR-0028) no entran: music21 escribiría su
    note-off antes que su note-on y quedarían sonando sin fin. No ocupan tiempo, y la vista
    tampoco las reproduce (ADR-0026).
    """

    out = score_ir_to_music21(score)
    for element in list(out.recurse().notes):
        site = element.activeSite
        if element.duration.isGrace and site is not None:
            site.remove(element)
    mf = midi.translate.streamToMidiFile(out)
    return bytes(mf.writestr())
