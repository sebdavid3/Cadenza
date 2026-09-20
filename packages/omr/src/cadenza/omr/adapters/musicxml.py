"""Puente provisional MusicXML → `ScoreIR`.

La Fase 1 mapea la salida MusicXML de HOMR al `ScoreIR` del dominio usando solo
la librería estándar (`xml.etree`), sin `music21` y con `bbox=None` (las
coordenadas espaciales quedan como enriquecimiento futuro). El parseo canónico
con `music21` y la frontera de validación llegan en la Fase 2.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction

from cadenza.domain import Event, EventKind, Measure, Part, ScoreIR, Staff

PITCH_STEPS = {"C", "D", "E", "F", "G", "A", "B"}
ACCIDENTAL_SUFFIX = {"-1": "b", "0": "", "1": "#"}


def _local(tag: str) -> str:
    """Devuelve el nombre local de una etiqueta, ignorando el namespace XML."""

    return tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if _local(child.tag) == name]


def _first_text(element: ET.Element, name: str) -> str | None:
    for child in element:
        if _local(child.tag) == name:
            return child.text
    return None


def _pitch_text(note: ET.Element) -> str | None:
    pitches = _children(note, "pitch")
    if not pitches:
        return None
    pitch = pitches[0]
    step = _first_text(pitch, "step") or ""
    octave = _first_text(pitch, "octave") or ""
    alter = _first_text(pitch, "alter")
    accidental = ACCIDENTAL_SUFFIX.get(alter or "0", "") if alter is not None else ""
    return f"{step}{accidental}{octave}"


def _event_from_note(note: ET.Element, divisions: int) -> Event:
    voice_text = _first_text(note, "voice")
    voice = int(voice_text) if voice_text is not None else 0
    duration_text = _first_text(note, "duration")
    duration_beats = Fraction(int(duration_text), divisions) if duration_text is not None else None
    pitch = _pitch_text(note)
    kind = EventKind.REST if _children(note, "rest") else EventKind.NOTE
    return Event(
        kind=kind,
        voice=voice,
        pitch=pitch,
        duration_beats=duration_beats,
    )


def _parse_part(part: ET.Element, part_index: int) -> Part:
    divisions = 1
    staff_measures: dict[int, list[Measure]] = {}

    for measure in _children(part, "measure"):
        number_text = measure.get("number")
        number = int(number_text) if number_text is not None else 1
        by_staff: dict[int, list[Event]] = {}

        for child in measure:
            tag = _local(child.tag)
            if tag == "attributes":
                divisions_text = _first_text(child, "divisions")
                if divisions_text is not None:
                    divisions = int(divisions_text) or 1
            elif tag == "note":
                staff_text = _first_text(child, "staff")
                staff_index = int(staff_text) - 1 if staff_text is not None else 0
                by_staff.setdefault(staff_index, []).append(_event_from_note(child, divisions))

        for staff_index, events in by_staff.items():
            staff_measures.setdefault(staff_index, []).append(
                Measure(number=number, events=tuple(events))
            )

    staves = tuple(
        Staff(id=f"part-{part_index}-staff-{staff_index}", measures=tuple(measures))
        for staff_index, measures in sorted(staff_measures.items())
    )
    return Part(id=f"part-{part_index}", staves=staves)


def musicxml_to_score_ir(xml_text: str) -> ScoreIR:
    """Convierte un documento MusicXML (`score-partwise`) en un `ScoreIR` neutral."""

    root = ET.fromstring(xml_text)
    parts = tuple(_parse_part(part, index) for index, part in enumerate(_children(root, "part")))
    return ScoreIR(parts=parts)
