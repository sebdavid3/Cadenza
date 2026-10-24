"""Puente canónico de notación: MusicXML/MEI/**kern ↔ `ScoreIR` (music21).

Esta es la única frontera de parseo/serialización simbólica del sistema. El
dominio permanece puro: `music21` solo vive aquí. El alcance cubierto es el
corpus objetivo (monofónico y piano simple); la notación muy densa (orquesta,
manuscritos históricos) queda fuera.
"""

from __future__ import annotations

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
    KeySignature,
    Measure,
    Part,
    ScoreIR,
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
    key,
    layout,
    meter,
    midi,
    musicxml,
    note,
    spanner,
    stream,
    tie,
)

_MAX_DENOMINATOR = 1000

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


# Un evento leído y los objetos de music21 de los que sale: un acorde y su primera nota dan el
# primer evento del acorde. Sirven para situar las ligaduras de expresión (ADR-0031).
_SourcedEvent = tuple[Event, tuple[Any, ...]]


def _events_from_measure(measure: Any) -> list[_SourcedEvent]:
    events: list[_SourcedEvent] = []
    voices = list(getattr(measure, "voices", ()))
    if voices:
        for voice_index, voice in enumerate(voices):
            events.extend(_events_from_elements(voice.notesAndRests, voice_index))
    else:
        events.extend(_events_from_elements(measure.notesAndRests, 0))
    return events


def _events_from_elements(elements: Any, voice: int) -> list[_SourcedEvent]:
    events: list[_SourcedEvent] = []
    for element in elements:
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
            event = _note_event(element, element, voice, is_chord=False, marks=(element,))
            events.append((event, (element,)))
    return events


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


def _measures(part: Any) -> list[tuple[Measure, list[tuple[Any, ...]]]]:
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
        sourced = _events_from_measure(measure)
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

    def __init__(self, raw_staves: Sequence[Any]) -> None:
        self._measures: list[list[Measure]] = []
        self._places: dict[int, _EventPlace] = {}
        self._slurs: dict[_EventPlace, list[Slur]] = {}
        self._wedges: dict[tuple[int, int], list[Wedge]] = {}
        for staff_index, raw_staff in enumerate(raw_staves):
            staff_measures: list[Measure] = []
            for measure_index, (measure, sources) in enumerate(_measures(raw_staff)):
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
    `read_score`): music21 pierde su posición.
    """

    return _to_score_ir(parsed, None)


def _to_score_ir(parsed: Any, musicxml_source: str | bytes | None) -> ScoreIR:
    if isinstance(parsed, stream.Opus):
        if not parsed.scores:
            return ScoreIR(parts=())
        parsed = parsed.scores[0]
        musicxml_source = None

    is_score = isinstance(parsed, stream.Score)
    groups: list[list[Any]] = _group_parts(parsed) if is_score else [[parsed]]
    readers = [_PartReader(group) for group in groups]
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
    silencio de negra.

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
        for voice_key, indices in sorted(by_voice.items()):
            v = stream.Voice(id=str(voice_key + 1))
            elements, voice_owners = _build_voice_elements(
                [measure.events[i] for i in indices], marks=marks
            )
            for off, el in elements:
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


def _musicxml_numbers(spans: Sequence[tuple[int, int]]) -> list[int]:
    """Número de MusicXML (del 1 al 16) para cada marca que abarca los compases dados.

    En MusicXML, y en OSMD, los extremos de una ligadura o de un regulador se emparejan por
    `number` en orden de lectura: dos marcas abiertas a la vez no pueden compartirlo. Dentro de
    un compás ese orden depende de cómo music21 escribe las voces y los pentagramas, así que
    dos marcas que tocan algún compás en común llevan números distintos. Por orden de inicio,
    cada una toma el número libre más bajo; si los 16 están ocupados, el que antes se libera.
    """

    busy_until: dict[int, int] = {}
    numbers = [0] * len(spans)
    for index in sorted(range(len(spans)), key=lambda i: (min(spans[i]), max(spans[i]))):
        first, last = min(spans[index]), max(spans[index])
        free = [n for n in _MUSICXML_NUMBERS if busy_until.get(n, -1) < first]
        number = free[0] if free else min(_MUSICXML_NUMBERS, key=busy_until.__getitem__)
        busy_until[number] = last
        numbers[index] = number
    return numbers


def _attach_slurs(out: stream.Score, part: Part, built_staves: Sequence[Sequence[Any]]) -> None:
    """Ligaduras de expresión completas de la parte (ADR-0031): un extremo huérfano no se dibuja."""

    starts: dict[int, tuple[Any, int]] = {}
    stops: dict[int, tuple[Any, int]] = {}
    for staff, built in zip(part.staves, built_staves, strict=True):
        for measure_index, (measure, (_built_measure, owners)) in enumerate(
            zip(staff.measures, built, strict=True)
        ):
            for event, owner in zip(measure.events, owners, strict=True):
                for slur in event.slurs:
                    ends = starts if slur.type is SlurType.START else stops
                    ends.setdefault(slur.number, (owner, measure_index))
    pairs = [
        (first, stops[number])
        for number, first in starts.items()
        if number in stops and stops[number][0] is not first[0]
    ]
    numbers = _musicxml_numbers([(first[1], last[1]) for first, last in pairs])
    for ((first, _), (last, _)), number in zip(pairs, numbers, strict=True):
        slur = spanner.Slur(first, last)
        slur.idLocal = number
        out.insert(0, slur)


def _attach_wedges(out: stream.Score, part: Part, built_staves: Sequence[Sequence[Any]]) -> None:
    """Reguladores completos de la parte (ADR-0031), entre dos anclas en su posición exacta del
    compás, que el exportador sitúa con `<forward>`. Un extremo huérfano no se dibuja."""

    starts: dict[int, tuple[WedgeType, Any, Fraction, int]] = {}
    stops: dict[int, tuple[Any, Fraction, int]] = {}
    for staff, built in zip(part.staves, built_staves, strict=True):
        for measure_index, (measure, (built_measure, _owners)) in enumerate(
            zip(staff.measures, built, strict=True)
        ):
            for wedge in measure.wedges:
                if wedge.type is WedgeType.STOP:
                    stops.setdefault(
                        wedge.number, (built_measure, wedge.offset_beats, measure_index)
                    )
                else:
                    starts.setdefault(
                        wedge.number, (wedge.type, built_measure, wedge.offset_beats, measure_index)
                    )
    pairs = [(start, stops[number]) for number, start in starts.items() if number in stops]
    numbers = _musicxml_numbers([(start[3], stop[2]) for start, stop in pairs])
    for (start, stop), number in zip(pairs, numbers, strict=True):
        wedge_type, start_measure, start_offset, _ = start
        stop_measure, stop_offset, _ = stop
        first = spanner.SpannerAnchor()
        start_measure.insert(start_offset, first)
        last = spanner.SpannerAnchor()
        stop_measure.insert(stop_offset, last)
        wedge_class = (
            dynamics.Crescendo if wedge_type is WedgeType.CRESCENDO else dynamics.Diminuendo
        )
        built_wedge = wedge_class(first, last)
        built_wedge.idLocal = number
        out.insert(0, built_wedge)


def score_ir_to_music21(score: ScoreIR, *, marks: bool = True) -> stream.Score:
    """Convierte un `ScoreIR` a un objeto `music21.stream.Score` estructurado.

    Con ``marks`` (por defecto) lleva las marcas de notación (ADR-0031); sin ellas, solo las
    notas, los silencios y los atributos de compás.
    """

    out = stream.Score()
    for part_index, part in enumerate(score.parts):
        built_staves = [_build_staff_measures(staff.measures, marks=marks) for staff in part.staves]
        if len(part.staves) > 1:
            part_staffs: list[stream.PartStaff] = []
            for staff_index, built in enumerate(built_staves):
                p_staff = stream.PartStaff(
                    id=f"{part.id or f'P{part_index + 1}'}-Staff{staff_index + 1}"
                )
                p_staff.partName = part.id
                for built_measure, _owners in built:
                    p_staff.append(built_measure)
                part_staffs.append(p_staff)
                out.insert(0, p_staff)
            sg = layout.StaffGroup(part_staffs, name=part.id, symbol="brace")
            out.insert(0, sg)
        else:
            built_part = stream.Part(id=part.id or f"P{part_index + 1}")
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

    Lleva las marcas de notación (ADR-0031): articulaciones, calderones, dinámicas y las
    ligaduras de expresión y los reguladores completos; un extremo sin pareja no se dibuja.
    """

    if not score.parts:
        raise InterchangeError("La partitura no tiene partes que exportar")
    out = score_ir_to_music21(score)
    exporter = musicxml.m21ToXml.ScoreExporter(out, makeNotation=True)
    with _keeping_spanner_numbers():
        root = exporter.parse()
    _drop_placeholder_metadata(root)
    exported: bytes = exporter.asBytes()
    return exported.decode("utf-8")


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


def score_ir_to_midi(score: ScoreIR) -> bytes:
    """Serializa un `ScoreIR` a bytes en formato MIDI 1.0 (Issue #12, ADR-0010).

    Las notas de adorno (duración cero o nula, ADR-0028) no entran: music21 escribiría su
    note-off antes que su note-on y quedarían sonando sin fin. No ocupan tiempo, y la vista
    tampoco las reproduce (ADR-0026).

    Tampoco las marcas de notación (ADR-0031): las dinámicas cambiarían las velocidades, y el
    volumen según las dinámicas es otro issue (#215).
    """

    out = score_ir_to_music21(score, marks=False)
    for element in list(out.recurse().notes):
        site = element.activeSite
        if element.duration.isGrace and site is not None:
            site.remove(element)
    mf = midi.translate.streamToMidiFile(out)
    return bytes(mf.writestr())
