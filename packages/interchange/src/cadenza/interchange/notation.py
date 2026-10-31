"""Puente canónico de notación: MusicXML/MEI/**kern ↔ `ScoreIR` (music21).

Esta es la única frontera de parseo/serialización simbólica del sistema. El
dominio permanece puro: `music21` solo vive aquí. El alcance cubierto es el
corpus objetivo (monofónico y piano simple); la notación muy densa (orquesta,
manuscritos históricos) queda fuera.
"""

from __future__ import annotations

import copy
import re
import threading
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path
from typing import Any, Final

from cadenza.domain import (
    Articulation,
    Clef,
    Dynamic,
    DynamicMark,
    Event,
    EventKind,
    Instrument,
    KeySignature,
    Measure,
    Part,
    PartMetadata,
    ScoreIR,
    ScoreMetadata,
    Slur,
    SlurType,
    Staff,
    Tie,
    TimeSignature,
    Wedge,
    WedgeType,
)
from music21 import (
    articulations,
    chord,
    clef,
    converter,
    defaults,
    dynamics,
    expressions,
    instrument,
    key,
    layout,
    meter,
    midi,
    musicxml,
    note,
    pitch,
    spanner,
    stream,
    tie,
)

_MAX_DENOMINATOR = 1000
# Hueco más breve que cuenta como hueco de una voz (ADR-0032): una semigarrapatea (1/64 de negra).
_MIN_GAP: Final[Fraction] = Fraction(1, 64)

# Articulaciones del alcance (ADR-0031). Se busca la clase exacta: en music21, `Staccatissimo`
# deriva de `Staccato` y `StrongAccent` de `Accent`, y `Spiccato` (fuera del alcance), de
# `Staccato`.
_ARTICULATIONS_FROM_MUSIC21: Final[dict[type, Articulation]] = {
    articulations.Staccato: Articulation.STACCATO,
    articulations.Staccatissimo: Articulation.STACCATISSIMO,
    articulations.Accent: Articulation.ACCENT,
    articulations.StrongAccent: Articulation.MARCATO,
    articulations.Tenuto: Articulation.TENUTO,
}
_ARTICULATIONS_TO_MUSIC21: Final[dict[Articulation, type]] = {
    value: cls for cls, value in _ARTICULATIONS_FROM_MUSIC21.items()
}
_DYNAMIC_MARKS: Final[frozenset[str]] = frozenset(mark.value for mark in DynamicMark)
# MusicXML numera las ligaduras y los reguladores del 1 al 16 (`number-level`).
_MUSICXML_NUMBERS: Final[range] = range(1, 17)
_SPANNER_NUMBERS_LOCK: Final[threading.Lock] = threading.Lock()
# Lugar de un extremo de ligadura o de regulador en el orden en que music21 escribe la parte.
_WriteKey = tuple[int | Fraction, ...]
# La de un ancla de regulador: (compás, pentagrama, posición en negras).
_AnchorKey = tuple[int, int, Fraction]


class InterchangeError(ValueError):
    """No se pudo interpretar o serializar una partitura."""


@dataclass(frozen=True, slots=True)
class _InstrumentSound:
    """Cómo se escribe un instrumento de la lista cerrada (ADR-0041 §2).

    `label` es el nombre de la parte si no se da otro; `program`, el programa General MIDI
    numerado desde 1, como `midi-program` en MusicXML (el MIDI lo numera desde 0); `sound`, el
    `instrument-sound` de MusicXML.
    """

    label: str
    program: int
    sound: str | None


_INSTRUMENT_SOUNDS: Final[dict[Instrument, _InstrumentSound]] = {
    Instrument.PIANO: _InstrumentSound("Piano", 1, "keyboard.piano"),
    Instrument.VOICE: _InstrumentSound("Voz", 53, "voice.vocals"),
    Instrument.VIOLIN: _InstrumentSound("Violín", 41, "strings.violin"),
    Instrument.CELLO: _InstrumentSound("Violonchelo", 43, "strings.cello"),
    Instrument.FLUTE: _InstrumentSound("Flauta", 74, "wind.flutes.flute"),
    Instrument.CLARINET: _InstrumentSound("Clarinete", 72, "wind.reed.clarinet"),
    Instrument.GUITAR: _InstrumentSound("Guitarra", 25, "pluck.guitar.nylon-string"),
    # «Otro» suena como el piano y su nombre es el que se dé (#240).
    Instrument.OTHER: _InstrumentSound("Otro", 1, None),
}
# Canales MIDI de las partes en MusicXML (1-16), sin el 10, el de percusión en General MIDI.
_MIDI_CHANNELS: Final[tuple[int, ...]] = tuple(c for c in range(1, 17) if c != 10)
# Lo que precede a `score-instrument` en un `score-part` (MusicXML 4.0).
_SCORE_PART_HEAD: Final[frozenset[str]] = frozenset(
    {
        "identification",
        "part-link",
        "part-name",
        "part-name-display",
        "part-abbreviation",
        "part-abbreviation-display",
        "group",
    }
)


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


# Un evento leído y los objetos de music21 de los que sale: un acorde y su primera nota dan el
# primer evento del acorde. Sirven para situar las ligaduras de expresión (ADR-0031).
_SourcedEvent = tuple[Event, tuple[Any, ...]]


def _ordered_voices(measure: Any) -> list[Any]:
    """Voces de un compás en orden (ADR-0032): por su número si todas lo tienen (MusicXML, como
    texto: music21 las ordenaba como texto, y «10» iba antes que «2»); si no, en el orden del
    compás. converter21 crea sin número las voces de MEI y **kern, y music21 les da su dirección
    de memoria, que no es un orden."""

    voices = list(getattr(measure, "voices", ()))
    if all(isinstance(voice.id, str) and voice.id.isdigit() for voice in voices):
        return sorted(voices, key=lambda voice: int(voice.id))
    return voices


def _events_from_measure(measure: Any, musicxml: bool) -> list[_SourcedEvent]:
    """Eventos de un compás de un pentagrama.

    Las voces se numeran desde 0 en cada compás, en el orden de su número de MusicXML (ADR-0032):
    HOMR numera 1-3 las del pentagrama superior y 5-7 las del inferior, y las dos quedan 0-2.
    """

    events: list[_SourcedEvent] = []
    voices = _ordered_voices(measure)
    if voices:
        for voice_index, voice in enumerate(voices):
            events.extend(_events_from_elements(voice.notesAndRests, voice_index, musicxml))
    else:
        events.extend(_events_from_elements(measure.notesAndRests, 0, musicxml))
    return events


def _events_from_elements(elements: Any, voice: int, musicxml: bool) -> list[_SourcedEvent]:
    """Eventos de una voz en orden (ADR-0032).

    Un hueco antes de una nota (en MusicXML, un `<forward>` o un `<backup>` que no vuelve al
    principio: la voz entra a mitad del compás o calla entre dos notas) es un silencio invisible,
    para que cada nota conserve dónde empieza. Lo que falta tras la última nota no es un evento.

    Con ``musicxml``, un silencio que music21 da oculto (`print-object="no"`) es también un
    silencio invisible. De MEI no: converter21 oculta el silencio con que sustituye un
    `<multiRest>`, que en la partitura se ve (32 de las 100 verdades de PrIMuS de `data/`).

    Un hueco más breve que `_MIN_GAP` no es musical (un `<backup>` que se queda corto en una
    división) y se ignora, como antes. Los silencios invisibles seguidos son uno: music21
    escribe en dos figuras el que no cabe en una, y la ida y vuelta lo devuelve igual.
    """

    events: list[_SourcedEvent] = []
    cursor = Fraction(0)
    for element in elements:
        start = Fraction(element.offset)
        if start - cursor >= _MIN_GAP:
            gap = Event(
                kind=EventKind.REST,
                voice=voice,
                duration_beats=(start - cursor).limit_denominator(_MAX_DENOMINATOR),
                hidden=True,
            )
            _append_event(events, gap, ())
        cursor = max(cursor, start + Fraction(element.quarterLength))
        if isinstance(element, chord.Chord):
            chord_notes = list(element.notes)
            for i, chord_note in enumerate(chord_notes):
                # Las marcas de un acorde van en su primera nota: music21 ya junta en el acorde
                # las de cada nota del MusicXML.
                marks = (element, *chord_notes) if i == 0 else ()
                sources = (element, chord_note) if i == 0 else (chord_note,)
                event = _note_event(chord_note, element, voice, is_chord=(i > 0), marks=marks)
                events.append((event, sources))
        else:
            hidden = (
                musicxml
                and isinstance(element, note.Rest)
                and bool(element.style.hideObjectOnPrint)
            )
            event = _note_event(
                element, element, voice, is_chord=False, marks=(element,), hidden=hidden
            )
            _append_event(events, event, (element,))
    return events


def _append_event(events: list[_SourcedEvent], event: Event, sources: tuple[Any, ...]) -> None:
    """Añade un evento a su voz; un silencio invisible sin marcas tras otro se suma a él."""

    if events and event.hidden and not _has_marks(event):
        last, last_sources = events[-1]
        if (
            last.hidden
            and not _has_marks(last)
            and last.duration_beats is not None
            and event.duration_beats is not None
        ):
            merged = replace(last, duration_beats=last.duration_beats + event.duration_beats)
            events[-1] = (merged, last_sources + sources)
            return
    events.append((event, sources))


def _has_marks(event: Event) -> bool:
    return bool(event.articulations or event.fermata or event.slurs)


def _note_marks(sources: Iterable[Any]) -> tuple[tuple[Articulation, ...], bool]:
    """Articulaciones del alcance y calderón de los objetos de music21 de un evento."""

    found: list[Articulation] = []
    fermata = False
    for source in sources:
        for articulation in getattr(source, "articulations", ()):
            mapped = _ARTICULATIONS_FROM_MUSIC21.get(type(articulation))
            if mapped is not None:
                found.append(mapped)
        fermata = fermata or any(
            isinstance(expression, expressions.Fermata)
            for expression in getattr(source, "expressions", ())
        )
    return tuple(found), fermata


def _note_event(
    pitch_source: Any,
    duration_source: Any,
    voice: int,
    is_chord: bool = False,
    marks: Iterable[Any] = (),
    hidden: bool = False,
) -> Event:
    is_rest = isinstance(pitch_source, note.Rest)
    note_articulations, fermata = _note_marks(marks)
    return Event(
        kind=EventKind.REST if is_rest else EventKind.NOTE,
        voice=voice,
        pitch=None if is_rest else _pitch_name(pitch_source),
        duration_beats=_duration(duration_source),
        tie=None if is_rest else _event_tie(pitch_source),
        is_chord=is_chord,
        articulations=note_articulations,
        fermata=fermata,
        hidden=hidden,
    )


def _measure_dynamics(measure: Any) -> tuple[Dynamic, ...]:
    """Dinámicas del alcance con su ataque en negras desde el inicio del compás (ADR-0031).

    music21 las sitúa bien (con el `<offset>` de la indicación) y en el pentagrama de su
    `<staff>`; la voz de la indicación no la guarda, y una dinámica rige su pentagrama.
    """

    found: list[Dynamic] = []
    for dynamic in measure.recurse().getElementsByClass(dynamics.Dynamic):
        if dynamic.value not in _DYNAMIC_MARKS:
            continue
        offset = Fraction(dynamic.getOffsetInHierarchy(measure)).limit_denominator(_MAX_DENOMINATOR)
        found.append(Dynamic(DynamicMark(dynamic.value), max(offset, Fraction(0))))
    return tuple(found)


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


def _measures(part: Any, musicxml: bool) -> list[tuple[Measure, list[tuple[Any, ...]]]]:
    """Compases de un pentagrama, cada uno con los objetos de music21 de cada evento."""

    found = list(part.getElementsByClass(stream.Measure))
    measures: list[tuple[Measure, list[tuple[Any, ...]]]] = []
    zero_count = sum(1 for m in found if getattr(m, "number", None) == 0)
    has_unassigned_measure_numbers = zero_count > 1

    for position, measure in enumerate(found, start=1):
        if has_unassigned_measure_numbers:
            number = position
        else:
            number = measure.number if isinstance(measure.number, int) else position
        is_first = position == 1
        sourced = _events_from_measure(measure, musicxml)
        measures.append(
            (
                Measure(
                    number=number,
                    events=tuple(event for event, _sources in sourced),
                    time_signature=_measure_signature(measure),
                    clef=_measure_clef(measure, is_first=is_first),
                    key_signature=_measure_key_signature(measure, is_first=is_first),
                    dynamics=_measure_dynamics(measure),
                ),
                [sources for _event, sources in sourced],
            )
        )
    return measures


# Posición de un evento o de un extremo de regulador dentro de una parte, en orden de lectura:
# (compás, pentagrama, evento) o (compás, pentagrama, negras desde el inicio del compás).
_EventPlace = tuple[int, int, int]
_WedgePlace = tuple[int, int, Fraction]


class _PartReader:
    """Pentagramas de una parte del `ScoreIR` con sus marcas (ADR-0031).

    Lee los compases de cada pentagrama y recuerda de qué objeto de music21 sale cada evento,
    para añadir después las marcas que abarcan varias notas: las ligaduras de expresión (de los
    spanners de music21, que cruzan compases y pentagramas) y los reguladores (del MusicXML,
    `_musicxml_wedges`). Los extremos de cada una se numeran en la parte por orden de lectura
    de su inicio, de modo que la ida y vuelta por MusicXML da los mismos números.
    """

    def __init__(self, raw_staves: Sequence[Any], musicxml: bool) -> None:
        self._measures: list[list[Measure]] = []
        self._places: dict[int, _EventPlace] = {}
        self._slurs: dict[_EventPlace, list[Slur]] = {}
        self._wedges: dict[tuple[int, int], list[Wedge]] = {}
        for staff_index, raw_staff in enumerate(raw_staves):
            staff_measures: list[Measure] = []
            for measure_index, (measure, sources) in enumerate(_measures(raw_staff, musicxml)):
                for event_index, event_sources in enumerate(sources):
                    for source in event_sources:
                        self._places.setdefault(
                            id(source), (measure_index, staff_index, event_index)
                        )
                staff_measures.append(measure)
            self._measures.append(staff_measures)

    def add_slurs(self, slurs: Iterable[Any]) -> None:
        """Ligaduras de expresión con sus dos extremos en esta parte; las demás se ignoran."""

        spans: list[tuple[_EventPlace, _EventPlace]] = []
        for slur in slurs:
            start = self._places.get(id(slur.getFirst()))
            stop = self._places.get(id(slur.getLast()))
            if start is not None and stop is not None and start != stop:
                spans.append((start, stop))
        for number, (start, stop) in enumerate(sorted(spans), start=1):
            self._slurs.setdefault(start, []).append(Slur(SlurType.START, number))
            self._slurs.setdefault(stop, []).append(Slur(SlurType.STOP, number))

    def has_measure(self, staff_index: int, measure_index: int) -> bool:
        return staff_index < len(self._measures) and measure_index < len(
            self._measures[staff_index]
        )

    def add_wedges(self, spans: Iterable[tuple[WedgeType, _WedgePlace, _WedgePlace]]) -> None:
        for number, (wedge_type, start, stop) in enumerate(
            sorted(spans, key=lambda span: (span[1], span[2])), start=1
        ):
            for place, kind in ((start, wedge_type), (stop, WedgeType.STOP)):
                measure_index, staff_index, offset = place
                self._wedges.setdefault((measure_index, staff_index), []).append(
                    Wedge(kind, number, offset)
                )

    def staves(self, part_index: int) -> tuple[Staff, ...]:
        staves: list[Staff] = []
        for staff_index, measures in enumerate(self._measures):
            built: list[Measure] = []
            for measure_index, measure in enumerate(measures):
                events = tuple(
                    (
                        replace(event, slurs=tuple(self._slurs[place]))
                        if (place := (measure_index, staff_index, event_index)) in self._slurs
                        else event
                    )
                    for event_index, event in enumerate(measure.events)
                )
                wedges = tuple(self._wedges.get((measure_index, staff_index), ()))
                built.append(replace(measure, events=events, wedges=wedges))
            staves.append(Staff(id=f"part-{part_index}-staff-{staff_index}", measures=tuple(built)))
        return tuple(staves)


@dataclass(frozen=True, slots=True)
class _WedgePoint:
    """Extremo de un regulador leído del MusicXML.

    `staff` es el índice del pentagrama entre todos los de la partitura, en el orden en que
    music21 los saca (`Score.parts`): las partes del MusicXML en orden y, dentro de cada una,
    sus pentagramas. `measure` es el ordinal del compás dentro de la parte.
    """

    staff: int
    measure: int
    offset: Fraction


def _xml_fraction(text: str | None) -> Fraction:
    return Fraction(text.strip()) if text and text.strip() else Fraction(0)


def _musicxml_wedges(
    musicxml_source: str | bytes,
) -> tuple[int, list[tuple[WedgeType, _WedgePoint, _WedgePoint]]]:
    """Reguladores completos del MusicXML, con la posición exacta de sus dos extremos (ADR-0031).

    music21 ata el inicio de un regulador a la nota siguiente y el fin a la anterior, a veces de
    otro pentagrama, y la posición se pierde. Aquí se recorre el MusicXML como music21 sitúa las
    dinámicas: el cursor del compás (las notas que no son de acorde ni de adorno avanzan su
    `<duration>`; `<backup>` y `<forward>`, la suya) más el `<offset>` de la indicación. Los
    extremos se emparejan por `number` en orden de lectura, como en MusicXML.

    Devuelve cuántos pentagramas tiene la partitura, para comprobar que coinciden con los de
    music21, y los reguladores. Un MusicXML que no se entiende no tiene reguladores: esto nunca
    impide leer la partitura.
    """

    spans: list[tuple[WedgeType, _WedgePoint, _WedgePoint]] = []
    first_staff = 0
    try:
        root = ET.fromstring(musicxml_source)
        if root.tag != "score-partwise":
            return 0, []
        for part in root.findall("part"):
            declared = [int(s.text) for s in part.iter("staves") if s.text and s.text.isdigit()]
            staves = max(declared, default=1)
            open_wedges: dict[str, tuple[WedgeType, _WedgePoint]] = {}
            divisions = Fraction(1)
            for ordinal, measure in enumerate(part.findall("measure")):
                position = Fraction(0)
                for child in measure:
                    if child.tag == "attributes" and child.findtext("divisions"):
                        divisions = _xml_fraction(child.findtext("divisions"))
                    elif child.tag == "note":
                        if child.find("chord") is None and child.find("grace") is None:
                            position += _xml_fraction(child.findtext("duration"))
                    elif child.tag == "backup":
                        position -= _xml_fraction(child.findtext("duration"))
                    elif child.tag == "forward":
                        position += _xml_fraction(child.findtext("duration"))
                    elif child.tag == "direction":
                        wedges = child.findall("direction-type/wedge")
                        if not wedges:
                            continue
                        staff = int(child.findtext("staff") or 1)
                        if not 1 <= staff <= staves:
                            continue
                        offset = (position + _xml_fraction(child.findtext("offset"))) / divisions
                        point = _WedgePoint(
                            first_staff + staff - 1, ordinal, max(offset, Fraction(0))
                        )
                        for wedge in wedges:
                            number = wedge.get("number", "1")
                            wedge_type = wedge.get("type")
                            if wedge_type in (WedgeType.CRESCENDO, WedgeType.DIMINUENDO):
                                open_wedges[number] = (WedgeType(wedge_type), point)
                            elif wedge_type == WedgeType.STOP and number in open_wedges:
                                start_type, start = open_wedges.pop(number)
                                spans.append((start_type, start, point))
            first_staff += staves
    except (ET.ParseError, ValueError, ZeroDivisionError):
        return 0, []
    return first_staff, spans


def _add_wedges(
    readers: Sequence[_PartReader],
    groups: Sequence[Sequence[Any]],
    raw_parts: Sequence[Any],
    musicxml_source: str | bytes,
) -> None:
    """Sitúa en las partes del `ScoreIR` los reguladores leídos del MusicXML."""

    staff_count, spans = _musicxml_wedges(musicxml_source)
    if staff_count != len(raw_parts):
        return
    located: dict[int, tuple[int, int]] = {}
    for part_index, group in enumerate(groups):
        for staff_index, raw_staff in enumerate(group):
            located[id(raw_staff)] = (part_index, staff_index)
    by_part: dict[int, list[tuple[WedgeType, _WedgePlace, _WedgePlace]]] = {}
    for wedge_type, start, stop in spans:
        start_part, start_staff = located.get(id(raw_parts[start.staff]), (-1, -1))
        stop_part, stop_staff = located.get(id(raw_parts[stop.staff]), (-1, -1))
        reader = readers[start_part] if start_part >= 0 else None
        if (
            reader is None
            or stop_part != start_part
            or not reader.has_measure(start_staff, start.measure)
            or not reader.has_measure(stop_staff, stop.measure)
        ):
            continue
        by_part.setdefault(start_part, []).append(
            (
                wedge_type,
                (start.measure, start_staff, start.offset),
                (stop.measure, stop_staff, stop.offset),
            )
        )
    for part_index, part_spans in by_part.items():
        readers[part_index].add_wedges(part_spans)


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
    """Convierte un `music21` `Stream`/`Score`/`Part` en un `ScoreIR` neutral.

    Lleva las articulaciones, los calderones, las ligaduras de expresión y las dinámicas
    (ADR-0031). Los reguladores solo se leen con el MusicXML a mano (`musicxml_to_score_ir`,
    `read_score`): music21 pierde su posición. Sin saber de qué formato viene, un silencio que
    music21 da oculto se lee como un silencio que se ve (ADR-0032); los huecos de una voz sí son
    silencios invisibles.
    """

    return _to_score_ir(parsed, None)


def _to_score_ir(parsed: Any, musicxml_source: str | bytes | None) -> ScoreIR:
    # Solo en MusicXML un silencio oculto es invisible (ADR-0032, `_events_from_elements`).
    musicxml = musicxml_source is not None
    if isinstance(parsed, stream.Opus):
        if not parsed.scores:
            return ScoreIR(parts=())
        parsed = parsed.scores[0]
        musicxml_source = None

    is_score = isinstance(parsed, stream.Score)
    groups: list[list[Any]] = _group_parts(parsed) if is_score else [[parsed]]
    readers = [_PartReader(group, musicxml) for group in groups]
    slurs = list(parsed.spannerBundle.getByClass(spanner.Slur))
    for reader in readers:
        reader.add_slurs(slurs)
    if is_score and musicxml_source is not None:
        _add_wedges(readers, groups, list(parsed.parts), musicxml_source)
    return ScoreIR(
        parts=tuple(
            Part(id=f"part-{part_index}", staves=reader.staves(part_index))
            for part_index, reader in enumerate(readers)
        )
    )


def musicxml_to_score_ir(xml_text: str) -> ScoreIR:
    """Convierte un documento MusicXML en un `ScoreIR` neutral, con sus marcas (ADR-0031)."""

    try:
        parsed = converter.parseData(xml_text, format="musicxml")
    except Exception as exc:  # pragma: no cover - mensaje accionable
        raise InterchangeError(f"MusicXML no interpretable: {exc}") from exc
    return _to_score_ir(parsed, xml_text)


def _musicxml_source(path: Path) -> str | bytes | None:
    """El MusicXML de un archivo `.musicxml`/`.xml` o de un `.mxl` comprimido, para los
    reguladores; None si no lo es o no se puede leer (la partitura se lee igual sin ellos)."""

    suffix = path.suffix.lower()
    try:
        if suffix in (".musicxml", ".xml"):
            return path.read_bytes()
        if suffix == ".mxl":
            # El mismo documento del archivo que lee music21, no el que declare `container.xml`.
            archive = converter.ArchiveManager(path)
            data = archive.getData() if archive.isArchive() else None
            return data if isinstance(data, str | bytes) else None
    except (OSError, KeyError, ValueError, converter.ArchiveManagerException):
        return None
    return None


def read_score(path: Path) -> ScoreIR:
    """Lee cualquier formato soportado por music21 (MusicXML, MEI, **kern)."""

    _register_converters()
    if not path.is_file():
        raise FileNotFoundError(f"score not found: {path}")
    try:
        parsed = converter.parse(str(path))
    except Exception as exc:  # pragma: no cover - mensaje accionable
        raise InterchangeError(f"partitura no interpretable: {path}: {exc}") from exc
    return _to_score_ir(parsed, _musicxml_source(path))


def _to_music21_pitch(pitch: str) -> str:
    """Traduce la altura del dominio (``Eb4``) al vocabulario de music21 (``E-4``)."""

    return pitch.replace("b", "-")


def _is_untimed_note(event: Event) -> bool:
    """Nota sin duración (cero o nula): así da HOMR una nota de adorno (D60, #199)."""

    return event.kind is not EventKind.REST and event.pitch is not None and not event.duration_beats


def _apply_note_marks(element: Any, events: Sequence[Event]) -> None:
    """Escribe en una nota, un acorde o un silencio de music21 las articulaciones y el calderón
    de sus eventos (ADR-0031). En un acorde, los de todas sus notas, una sola vez."""

    present = {a for event in events for a in event.articulations}
    element.articulations = [_ARTICULATIONS_TO_MUSIC21[a]() for a in Articulation if a in present]
    if any(event.fermata for event in events):
        fermata = expressions.Fermata()
        # music21 escribe por defecto `inverted` (bajo la nota); sin tipo guardado, va encima.
        fermata.type = "upright"
        element.expressions.append(fermata)


def _build_voice_elements(
    events: list[Event], *, marks: bool = True
) -> tuple[list[tuple[float, Any]], list[Any]]:
    """Elementos de music21 de una voz, cada uno con su instante dentro del compás.

    Una nota o un acorde sin duración se escribe como nota de adorno, que no ocupa tiempo: así
    lo dibujado suma lo mismo que el `ScoreIR`, el mapa de tiempos y el validador (D60, #199).
    Antes salía como negra, porque music21 cambia `quarterLength=0` por su duración por defecto.
    Un silencio no tiene versión de adorno en MusicXML: con duración cero sigue saliendo como
    silencio de negra. Un silencio invisible sale con `print-object="no"` (ADR-0032).

    Devuelve también, para cada evento, el elemento que lo dibuja (el acorde, en sus notas),
    donde se atan las ligaduras de expresión. Con ``marks``, las notas llevan sus marcas.
    """

    elements: list[tuple[float, Any]] = []
    owners: list[Any] = []
    offset = 0.0
    i = 0
    while i < len(events):
        ev = events[i]
        dur = float(ev.duration_beats) if ev.duration_beats is not None else 1.0
        if ev.kind is EventKind.REST or ev.pitch is None:
            r = note.Rest(quarterLength=dur)
            r.style.hideObjectOnPrint = ev.hidden
            if marks:
                _apply_note_marks(r, [ev])
            elements.append((offset, r))
            owners.append(r)
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
            if marks:
                _apply_note_marks(element, chord_notes)
            if _is_untimed_note(ev):
                # `getGrace` devuelve una copia: es la que se dibuja y la que lleva las ligaduras.
                element = element.getGrace()
                elements.append((offset, element))
            else:
                elements.append((offset, element))
                offset += dur
            owners.extend([element] * len(chord_notes))
            i = j
    return elements, owners


def _stem_directions(measure: Measure) -> dict[int, str]:
    """Dirección de plica de cada voz con notas de un compás con varias voces (ADR-0032).

    El `ScoreIR` no la guarda (HOMR no la da): se decide al exportar con la convención clásica,
    la voz de arriba hacia arriba y las demás hacia abajo. La de arriba es la de mayor altura
    media, no la de número menor: HOMR no numera las voces por su altura (en el piano de prueba
    da la voz 1 a las negras graves y la 2 a las blancas agudas). Sin plicas, OSMD solo fuerza la
    primera voz hacia arriba donde otra ataca a la vez, y en el resto podía pisar a la segunda.
    Con menos de dos voces con notas, decide quien dibuja.
    """

    heights: dict[int, list[int]] = {}
    for event in measure.events:
        if event.kind is EventKind.NOTE and event.pitch is not None:
            try:
                midi = pitch.Pitch(_to_music21_pitch(event.pitch)).midi
            except (ValueError, pitch.PitchException):
                continue
            heights.setdefault(event.voice, []).append(midi)
    if len(heights) < 2:
        return {}
    ranked = sorted(heights, key=lambda voice: (-sum(heights[voice]) / len(heights[voice]), voice))
    return {voice: "up" if position == 0 else "down" for position, voice in enumerate(ranked)}


def _build_measure(
    measure: Measure, previous_signature: TimeSignature | None = None, *, marks: bool = True
) -> tuple[Any, list[Any]]:
    """Construye el compás de music21 y da, para cada evento del compás, su elemento.

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

    by_voice: dict[int, list[int]] = {}
    for index, event in enumerate(measure.events):
        by_voice.setdefault(event.voice, []).append(index)

    owners: list[Any] = [None] * len(measure.events)
    if len(by_voice) <= 1:
        elements, owners = _build_voice_elements(list(measure.events), marks=marks)
        for off, el in elements:
            built.insert(off, el)
    else:
        stems = _stem_directions(measure)
        for voice_key, indices in sorted(by_voice.items()):
            v = stream.Voice(id=str(voice_key + 1))
            elements, voice_owners = _build_voice_elements(
                [measure.events[i] for i in indices], marks=marks
            )
            for off, el in elements:
                if voice_key in stems and not isinstance(el, note.Rest):
                    el.stemDirection = stems[voice_key]
                v.insert(off, el)
            for i, owner in zip(indices, voice_owners, strict=True):
                owners[i] = owner
            built.insert(0.0, v)
    return built, owners


def _build_staff_measures(
    measures: tuple[Measure, ...], *, marks: bool = True
) -> list[tuple[Any, list[Any]]]:
    built: list[tuple[Any, list[Any]]] = []
    previous_signature: TimeSignature | None = None
    for index, measure in enumerate(measures):
        built_measure, owners = _build_measure(measure, previous_signature, marks=marks)
        signature = measure.time_signature
        if signature is not None:
            previous_signature = signature
            # Sin silencios de relleno, music21 trata un compás incompleto como una anacrusa y
            # agrupa las barras desde el final. Solo el primero puede serlo: en los demás, lo
            # que falta va a la derecha, como al importar MusicXML (#152).
            missing = signature.quarter_length - Fraction(built_measure.highestTime)
            if index > 0 and missing > 0:
                built_measure.paddingRight = missing
        if marks:
            # Después del relleno: una dinámica no ocupa tiempo ni completa el compás.
            for dynamic in measure.dynamics:
                built_measure.insert(dynamic.offset_beats, dynamics.Dynamic(dynamic.mark.value))
        built.append((built_measure, owners))
    return built


def _musicxml_numbers(spans: Sequence[tuple[_WriteKey, _WriteKey]]) -> list[int]:
    """Número de MusicXML (del 1 al 16) para cada marca, dada la clave de escritura de sus
    extremos: su lugar en el orden en que music21 escribe la parte.

    En MusicXML, y en OSMD, los extremos de una ligadura o de un regulador se emparejan por
    `number` en orden de lectura: dos marcas abiertas a la vez no pueden compartirlo. Por orden
    de inicio, cada marca toma el número libre más bajo, y un número se libera cuando ya se ha
    escrito el fin de su marca (con clave igual, no: no se sabe cuál de los dos va antes). Si
    los 16 están abiertos, se toma el que antes se libera.
    """

    busy_until: dict[int, _WriteKey] = {}
    numbers = [0] * len(spans)
    for index in sorted(range(len(spans)), key=lambda i: spans[i]):
        first, last = spans[index]
        free = [n for n in _MUSICXML_NUMBERS if n not in busy_until or busy_until[n] < first]
        number = free[0] if free else min(_MUSICXML_NUMBERS, key=busy_until.__getitem__)
        busy_until[number] = last
        numbers[index] = number
    return numbers


def _attach_slurs(out: stream.Score, part: Part, built_staves: Sequence[Sequence[Any]]) -> None:
    """Ligaduras de expresión completas de la parte (ADR-0031): un extremo huérfano no se dibuja."""

    # Cada extremo con su elemento y su clave de escritura: music21 escribe la parte compás a
    # compás, cada compás pentagrama a pentagrama y cada pentagrama voz a voz.
    starts: dict[int, tuple[Any, _WriteKey]] = {}
    stops: dict[int, tuple[Any, _WriteKey]] = {}
    for staff_index, (staff, built) in enumerate(zip(part.staves, built_staves, strict=True)):
        for measure_index, (measure, (_built_measure, owners)) in enumerate(
            zip(staff.measures, built, strict=True)
        ):
            voices = sorted({event.voice for event in measure.events})
            seen: dict[int, int] = {}
            for event, owner in zip(measure.events, owners, strict=True):
                position = seen.get(event.voice, 0)
                seen[event.voice] = position + 1
                written = (measure_index, staff_index, voices.index(event.voice), position)
                for slur in event.slurs:
                    ends = starts if slur.type is SlurType.START else stops
                    ends.setdefault(slur.number, (owner, written))
    pairs = []
    for number, first in starts.items():
        last = stops.get(number)
        if last is None or last[0] is first[0]:
            continue
        # Si el inicio se escribiría detrás del fin (de un pentagrama o una voz posterior a otra
        # anterior del mismo compás), al leerlo se emparejaría con el fin de otra ligadura: se
        # intercambian sus papeles, y la ligadura une las mismas notas.
        pairs.append((first, last) if first[1] <= last[1] else (last, first))
    numbers = _musicxml_numbers([(first[1], last[1]) for first, last in pairs])
    for (first, last), number in zip(pairs, numbers, strict=True):
        slur = spanner.Slur(first[0], last[0])
        slur.idLocal = number
        out.insert(0, slur)


def _attach_wedges(out: stream.Score, part: Part, built_staves: Sequence[Sequence[Any]]) -> None:
    """Reguladores completos de la parte (ADR-0031), entre dos anclas en su posición exacta del
    compás, que el exportador sitúa con `<forward>`. Un extremo huérfano no se dibuja.

    Las anclas van en el compás, fuera de las voces, y music21 las escribe por compás, por
    pentagrama y por posición: esa es su clave de escritura (compás, pentagrama, posición).
    """

    starts: dict[int, tuple[WedgeType, _AnchorKey]] = {}
    stops: dict[int, _AnchorKey] = {}
    for staff_index, staff in enumerate(part.staves):
        for measure_index, measure in enumerate(staff.measures):
            for wedge in measure.wedges:
                written = (measure_index, staff_index, wedge.offset_beats)
                if wedge.type is WedgeType.STOP:
                    stops.setdefault(wedge.number, written)
                else:
                    starts.setdefault(wedge.number, (wedge.type, written))
    pairs: list[tuple[WedgeType, _AnchorKey, _AnchorKey]] = []
    for number, (wedge_type, start) in starts.items():
        stop = stops.get(number)
        if stop is None:
            continue
        if stop[0] == start[0] and stop[1] < start[1]:
            # De un pentagrama inferior a uno superior en el mismo compás: music21 escribiría el
            # fin delante del inicio. Se escribe en el pentagrama del inicio, en su posición.
            stop = (stop[0], start[1], stop[2])
        pairs.append((wedge_type, start, stop))
    numbers = _musicxml_numbers([(start, stop) for _wedge_type, start, stop in pairs])
    for (wedge_type, start, stop), number in zip(pairs, numbers, strict=True):
        anchors = []
        for measure_index, staff_index, offset in (start, stop):
            anchor = spanner.SpannerAnchor()
            built_staves[staff_index][measure_index][0].insert(offset, anchor)
            anchors.append(anchor)
        wedge_class = (
            dynamics.Crescendo if wedge_type is WedgeType.CRESCENDO else dynamics.Diminuendo
        )
        built_wedge = wedge_class(*anchors)
        built_wedge.idLocal = number
        out.insert(0, built_wedge)


def score_ir_to_music21(score: ScoreIR, *, marks: bool = True) -> stream.Score:
    """Convierte un `ScoreIR` a un objeto `music21.stream.Score` estructurado.

    Con ``marks`` (por defecto) lleva las marcas de notación (ADR-0031); sin ellas, solo las
    notas, los silencios y los atributos de compás. Los números de las ligaduras y de los
    reguladores solo los respeta `score_ir_to_musicxml`: otro exportador de music21 los vuelve a
    numerar del 1 al 6 en ciclo.
    """

    return _build_music21(score, marks=marks)


def _midi_instrument(part: PartMetadata) -> instrument.Instrument | None:
    """El instrumento de music21 que fija el programa MIDI de una parte, o None sin él."""
    if part.instrument is None:
        return None
    built = instrument.Instrument()
    built.midiProgram = _INSTRUMENT_SOUNDS[part.instrument].program - 1
    return built


def _build_music21(
    score: ScoreIR, *, marks: bool, metadata: ScoreMetadata | None = None
) -> stream.Score:
    """`score_ir_to_music21` y, con ``metadata``, el programa MIDI de cada parte (ADR-0041)."""

    out = stream.Score()
    for part_index, part in enumerate(score.parts):
        sound = None if metadata is None else _midi_instrument(metadata.part(part_index))
        built_staves = [_build_staff_measures(staff.measures, marks=marks) for staff in part.staves]
        if len(part.staves) > 1:
            part_staffs: list[stream.PartStaff] = []
            for staff_index, built in enumerate(built_staves):
                p_staff = stream.PartStaff(
                    id=f"{part.id or f'P{part_index + 1}'}-Staff{staff_index + 1}"
                )
                p_staff.partName = part.id
                if sound is not None:
                    p_staff.insert(0, copy.deepcopy(sound))
                for built_measure, _owners in built:
                    p_staff.append(built_measure)
                part_staffs.append(p_staff)
                out.insert(0, p_staff)
            sg = layout.StaffGroup(part_staffs, name=part.id, symbol="brace")
            out.insert(0, sg)
        else:
            built_part = stream.Part(id=part.id or f"P{part_index + 1}")
            if sound is not None:
                built_part.insert(0, sound)
            for built in built_staves:
                for built_measure, _owners in built:
                    built_part.append(built_measure)
            out.insert(0, built_part)
        if marks:
            _attach_slurs(out, part, built_staves)
            _attach_wedges(out, part, built_staves)
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


def _write_metadata(root: Any, metadata: ScoreMetadata) -> None:
    """Escribe el título, el compositor y el nombre y el instrumento de cada parte (ADR-0041).

    Sobre el árbol que exporta music21, que sin metadatos no escribe nada de esto: `work` va
    primero en `score-partwise`, el `creator` primero en `identification`, y en cada
    `score-part` el nombre sustituye al que había y el instrumento va en `score-instrument` y
    `midi-instrument`. Las partes sin datos quedan como estaban.
    """

    if metadata.title is not None:
        work = ET.Element("work")
        ET.SubElement(work, "work-title").text = metadata.title
        root.insert(0, work)
    if metadata.composer is not None:
        identification = root.find("identification")
        if identification is None:
            identification = ET.Element("identification")
            root.insert(1 if metadata.title is not None else 0, identification)
        creator = ET.Element("creator", {"type": "composer"})
        creator.text = metadata.composer
        identification.insert(0, creator)

    for index, score_part in enumerate(root.findall("part-list/score-part")):
        part = metadata.part(index)
        if part.is_empty:
            continue
        sound = None if part.instrument is None else _INSTRUMENT_SOUNDS[part.instrument]
        name = part.name or (None if sound is None else sound.label)
        part_name = score_part.find("part-name")
        if part_name is None:
            part_name = ET.Element("part-name")
            score_part.insert(0, part_name)
        part_name.text = name
        if sound is None:
            continue
        for stale in score_part.findall("score-instrument") + score_part.findall("midi-instrument"):
            score_part.remove(stale)
        instrument_id = f"{score_part.get('id')}-I1"
        score_instrument = ET.Element("score-instrument", {"id": instrument_id})
        ET.SubElement(score_instrument, "instrument-name").text = name
        if sound.sound is not None:
            ET.SubElement(score_instrument, "instrument-sound").text = sound.sound
        head = sum(1 for child in score_part if child.tag in _SCORE_PART_HEAD)
        score_part.insert(head, score_instrument)
        midi_instrument = ET.SubElement(score_part, "midi-instrument", {"id": instrument_id})
        channel = _MIDI_CHANNELS[index % len(_MIDI_CHANNELS)]
        ET.SubElement(midi_instrument, "midi-channel").text = str(channel)
        ET.SubElement(midi_instrument, "midi-program").text = str(sound.program)


def score_ir_to_musicxml(score: ScoreIR, metadata: ScoreMetadata | None = None) -> str:
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

    Lleva las marcas de notación (ADR-0031): articulaciones, calderones, dinámicas y las
    ligaduras de expresión y los reguladores completos; un extremo sin pareja no se dibuja.

    Con ``metadata``, el título, el compositor y el nombre y el instrumento de cada parte
    (ADR-0041); sin ellos, o vacíos, la exportación no cambia.
    """

    if not score.parts:
        raise InterchangeError("La partitura no tiene partes que exportar")
    out = score_ir_to_music21(score)
    exporter = musicxml.m21ToXml.ScoreExporter(out, makeNotation=True)
    with _keeping_spanner_numbers():
        root = exporter.parse()
    _drop_placeholder_metadata(root)
    if metadata is not None and not metadata.is_empty:
        _write_metadata(root, metadata)
    _number_voices_by_staff(root, score)
    exported: bytes = exporter.asBytes()
    return exported.decode("utf-8")


def _number_voices_by_staff(root: Any, score: ScoreIR) -> None:
    """Numera las voces de cada pentagrama aparte y igual en todos los compases (ADR-0032).

    Al unir los pentagramas de una parte, music21 no renumera las voces del inferior si el
    superior ya las numera: las dos manos compartían la voz 1, y la voz principal de abajo era la
    1 en unos compases y la 2 en otros. OSMD sitúa los silencios de varias voces por su número.
    Aquí la voz ``v`` del pentagrama ``s`` (desde 0) es la ``s * paso + v + 1``, con un paso de 4
    como HOMR y MuseScore (1-4 arriba, 5-8 abajo) o mayor si un pentagrama tiene más voces.
    Solo se renumera lo que music21 ya numeró, compás a compás y pentagrama a pentagrama, en el
    orden en que escribe las voces del `ScoreIR`; si no cuadra, el compás se deja como está.
    """

    for part, written_part in zip(score.parts, root.findall("part"), strict=False):
        highest = max(
            (e.voice for staff in part.staves for m in staff.measures for e in m.events), default=0
        )
        step = max(4, highest + 1)
        for measure_index, written_measure in enumerate(written_part.findall("measure")):
            notes = written_measure.findall("note")
            for staff_index, staff in enumerate(part.staves):
                if measure_index >= len(staff.measures):
                    continue
                voices = sorted({event.voice for event in staff.measures[measure_index].events})
                staff_notes = [
                    n for n in notes if (n.findtext("staff") or "1") == str(staff_index + 1)
                ]
                written: list[str] = []
                for n in staff_notes:
                    number = n.findtext("voice")
                    if number is not None and number not in written:
                        written.append(number)
                if len(written) != len(voices):
                    continue
                renumbered = {
                    old: str(staff_index * step + voice + 1)
                    for old, voice in zip(written, voices, strict=True)
                }
                for n in staff_notes:
                    element = n.find("voice")
                    if element is not None and element.text is not None:
                        element.text = renumbered[element.text]


def _spanner_class_name(item: Any) -> str:
    """La clase por la que music21 numera un spanner: crescendo y diminuendo comparten."""

    return str(next(name for name in item.classes if name not in ("Crescendo", "Diminuendo")))


@contextmanager
def _keeping_spanner_numbers() -> Iterator[None]:
    """Mientras se exporta, music21 respeta los números que ya llevan los spanners (ADR-0031).

    `PartExporter.parse` llama a `SpannerBundle.setIdLocals`, que numera cada clase del 1 al 6
    en ciclo, sin mirar si se solapan: una ligadura larga compartía número con otra abierta y
    el MusicXML las emparejaba mal. Las ligaduras y los reguladores ya llevan el suyo
    (`_musicxml_numbers`); music21 solo numera las clases con algún spanner sin número, como los
    grupos de pentagramas. El cerrojo impide que dos exportaciones a la vez se pisen al cambiar
    y restaurar el método.
    """

    def set_missing(bundle: spanner.SpannerBundle) -> None:
        for name in {_spanner_class_name(item) for item in bundle if item.idLocal is None}:
            bundle.setIdLocalByClass(name)

    with _SPANNER_NUMBERS_LOCK:
        original = spanner.SpannerBundle.setIdLocals
        spanner.SpannerBundle.setIdLocals = set_missing
        try:
            yield
        finally:
            spanner.SpannerBundle.setIdLocals = original


def score_ir_to_midi(score: ScoreIR, metadata: ScoreMetadata | None = None) -> bytes:
    """Serializa un `ScoreIR` a bytes en formato MIDI 1.0 (Issue #12, ADR-0010).

    Las notas de adorno (duración cero o nula, ADR-0028) no entran: music21 escribiría su
    note-off antes que su note-on y quedarían sonando sin fin. No ocupan tiempo, y la vista
    tampoco las reproduce (ADR-0026).

    Tampoco las marcas de notación (ADR-0031): las dinámicas cambiarían las velocidades, y el
    volumen según las dinámicas es otro issue (#215).

    Con ``metadata``, cada parte con instrumento fija su programa General MIDI en todas sus
    pistas (ADR-0041); sin instrumento no hay cambio de programa, como antes.
    """

    out = _build_music21(score, marks=False, metadata=metadata)
    for element in list(out.recurse().notes):
        site = element.activeSite
        if element.duration.isGrace and site is not None:
            site.remove(element)
    mf = midi.translate.streamToMidiFile(out)
    return bytes(mf.writestr())
