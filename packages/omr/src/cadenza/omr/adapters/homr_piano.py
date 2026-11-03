"""El piano de una página de voz y piano, leído de dos maneras y combinado (#325, ADR-0060).

HOMR lee el piano de un sistema de tres pentagramas de dos maneras distintas según cómo agrupe
los pentagramas (`homr_grand_staff`): como un gran pentagrama, con las dos manos en una misma
imagen (`PianoReading.PAIRED`, #239), o cada mano sola (`PianoReading.ALONE`). Ninguna gana
siempre: emparejadas, las manos comparten las barras y el ritmo de una ayuda al de la otra, pero
HOMR puede perder un cambio de clave o los tresillos; solas, lee mejor las claves y las alturas,
pero a veces se equivoca en las figuras de una mano.

Aquí se combinan las dos lecturas de la misma página, sistema a sistema y mano a mano, sin la
verdad: de cada mano se toma la lectura con menos compases cuya duración no es la habitual de esa
mano en esa lectura (la suma más repetida de sus compases; a igualdad, la mayor), y, a igualdad,
la emparejada. Una mano sola solo se toma si tiene en ese sistema los mismos compases que la
emparejada: así las dos manos de cada sistema tienen los mismos compases, y el piano, los mismos
que tenía con #239 frente a la voz. La voz sale de la lectura emparejada (en las dos se lee sola).

Los sistemas se cuentan en el MusicXML de HOMR, que empieza cada uno con
`<print new-system="yes">`. Si las dos lecturas no tienen las partes esperadas (la voz y el piano
de dos pentagramas en la emparejada, tres partes de un pentagrama en la otra) o los mismos
sistemas, se queda la emparejada.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from fractions import Fraction

from cadenza.domain import (
    Clef,
    KeySignature,
    Measure,
    Part,
    ScoreIR,
    Slur,
    SlurType,
    Staff,
    TimeSignature,
    same_time_notation,
)

from ..meter_stage import measure_sum
from .homr_grand_staff import PianoReading

_LOGGER = logging.getLogger(__name__)

RIGHT, LEFT = 0, 1
"""Las manos del piano: el pentagrama de arriba y el de abajo."""


@dataclass(frozen=True, slots=True)
class StaffReading:
    """Un pentagrama del piano según una lectura: sus compases y cuántos tiene cada sistema."""

    reading: PianoReading
    part: int
    measures: tuple[Measure, ...]
    systems: tuple[int, ...]

    def __post_init__(self) -> None:
        if sum(self.systems) != len(self.measures):
            raise ValueError("los sistemas no suman los compases del pentagrama")

    def span(self, system: int) -> range:
        start = sum(self.systems[:system])
        return range(start, start + self.systems[system])

    def irregular(self, system: int) -> int:
        """Compases con notas del sistema cuya duración no es la habitual del pentagrama."""

        usual = usual_duration(self.measures)
        return sum(
            1
            for index in self.span(system)
            if self.measures[index].events and measure_sum(self.measures[index]) != usual
        )


@dataclass(frozen=True, slots=True)
class SystemChoice:
    """De qué lectura sale cada mano de un sistema."""

    right: PianoReading
    left: PianoReading

    def to_primitive(self) -> dict[str, str]:
        return {"right": self.right.value, "left": self.left.value}


def usual_duration(measures: Sequence[Measure]) -> Fraction | None:
    """La duración más repetida de los compases con notas; a igualdad, la mayor."""

    sums = Counter(measure_sum(measure) for measure in measures if measure.events)
    if not sums:
        return None
    return max(sums, key=lambda value: (sums[value], value))


def system_sizes(xml_text: str) -> list[list[int]]:
    """Cuántos compases tiene cada sistema en cada parte del MusicXML de HOMR."""

    root = ET.fromstring(xml_text.encode("utf-8"))
    sizes: list[list[int]] = []
    for part in root.findall("part"):
        counts: list[int] = []
        for measure in part.findall("measure"):
            starts_system = any(
                element.get("new-system") == "yes" for element in measure.findall("print")
            )
            if not counts or (starts_system and counts[-1]):
                counts.append(0)
            counts[-1] += 1
        sizes.append(counts)
    return sizes


def choose_readings(
    paired: Sequence[StaffReading], alone: Sequence[StaffReading]
) -> list[SystemChoice]:
    """La lectura de cada mano en cada sistema (las dos manos, en el orden `RIGHT`, `LEFT`).

    Una mano sola se toma si tiene menos compases irregulares que la emparejada y los mismos
    compases en el sistema."""

    systems = len(paired[RIGHT].systems)
    if any(len(staff.systems) != systems for staff in (*paired, *alone)):
        raise ValueError("las dos lecturas no tienen los mismos sistemas")
    choices: list[SystemChoice] = []
    for system in range(systems):
        hands = [
            (
                PianoReading.ALONE
                if alone[hand].systems[system] == paired[hand].systems[system]
                and alone[hand].irregular(system) < paired[hand].irregular(system)
                else PianoReading.PAIRED
            )
            for hand in (RIGHT, LEFT)
        ]
        choices.append(SystemChoice(right=hands[RIGHT], left=hands[LEFT]))
    return choices


_Attributes = tuple[Clef | None, KeySignature | None, TimeSignature | None]
_Place = tuple[int, int, int]


def _in_force(measures: Sequence[Measure]) -> list[_Attributes]:
    """La clave, la armadura y el compás que rigen al principio de cada compás."""

    clef: Clef | None = None
    key: KeySignature | None = None
    time: TimeSignature | None = None
    result: list[_Attributes] = []
    for measure in measures:
        clef = measure.clef or clef
        key = measure.key_signature or key
        time = measure.time_signature or time
        result.append((clef, key, time))
    return result


def _splice(
    staves: Sequence[StaffReading], sources: Sequence[PianoReading]
) -> list[tuple[Measure, StaffReading]]:
    """Los compases de un pentagrama, sistema a sistema de la lectura elegida.

    Donde un sistema sale de otra lectura que el anterior, su primer compás lleva la clave, la
    armadura y el compás que rigen en esa lectura si no son los que regían."""

    by_reading = {staff.reading: staff for staff in staves}
    in_force = {staff.reading: _in_force(staff.measures) for staff in staves}
    spliced: list[tuple[Measure, StaffReading]] = []
    current: _Attributes = (None, None, None)
    for system, reading in enumerate(sources):
        staff = by_reading[reading]
        for position, index in enumerate(staff.span(system)):
            measure = staff.measures[index]
            if position == 0:
                clef, key, time = in_force[reading][index]
                measure = replace(
                    measure,
                    clef=measure.clef or (clef if clef != current[0] else None),
                    key_signature=measure.key_signature or (key if key != current[1] else None),
                    time_signature=measure.time_signature
                    or (
                        time
                        if time is not None and not same_time_notation(time, current[2])
                        else None
                    ),
                )
            current = (
                measure.clef or current[0],
                measure.key_signature or current[1],
                measure.time_signature or current[2],
            )
            spliced.append((measure, staff))
    return spliced


def _renumber_slurs(
    staves: Sequence[list[tuple[Measure, StaffReading]]],
) -> list[list[Measure]]:
    """Las ligaduras de expresión con sus dos extremos en la combinación, numeradas como las
    numera la importación (por el orden de lectura de su inicio); las demás se quitan.

    Un número identifica una ligadura dentro de la parte de la que sale (`_PartReader`)."""

    ends: dict[tuple[PianoReading, int, int], dict[SlurType, _Place]] = {}
    for staff_index, measures in enumerate(staves):
        for measure_index, (measure, source) in enumerate(measures):
            for event_index, event in enumerate(measure.events):
                for slur in event.slurs:
                    key = (source.reading, source.part, slur.number)
                    ends.setdefault(key, {})[slur.type] = (measure_index, staff_index, event_index)
    complete = sorted(
        (found[SlurType.START], found[SlurType.STOP])
        for found in ends.values()
        if SlurType.START in found and SlurType.STOP in found
    )
    renumbered: dict[_Place, list[Slur]] = {}
    for number, (start, stop) in enumerate(complete, start=1):
        renumbered.setdefault(start, []).append(Slur(SlurType.START, number))
        renumbered.setdefault(stop, []).append(Slur(SlurType.STOP, number))
    result: list[list[Measure]] = []
    for staff_index, measures in enumerate(staves):
        built: list[Measure] = []
        for measure_index, (measure, _source) in enumerate(measures):
            events = tuple(
                (
                    replace(
                        event,
                        slurs=tuple(renumbered.get((measure_index, staff_index, event_index), ())),
                    )
                    if event.slurs
                    else event
                )
                for event_index, event in enumerate(measure.events)
            )
            built.append(replace(measure, number=measure_index + 1, events=events))
        result.append(built)
    return result


def _layout(score: ScoreIR) -> list[int]:
    return [len(part.staves) for part in score.parts]


def combine_voice_and_piano(
    paired: ScoreIR, paired_xml: str, alone: ScoreIR, alone_xml: str
) -> tuple[ScoreIR, list[SystemChoice]] | None:
    """La voz de la lectura emparejada y el piano combinado de las dos (ver el módulo).

    None si las lecturas no son las de una página de voz y piano: la emparejada con la voz y el
    piano ([1, 2]), la otra con tres partes de un pentagrama, y los mismos sistemas."""

    if _layout(paired) != [1, 2] or _layout(alone) != [1, 1, 1]:
        return None
    paired_sizes, alone_sizes = system_sizes(paired_xml), system_sizes(alone_xml)
    if len(paired_sizes) != 2 or len(alone_sizes) != 3:
        return None
    piano = paired.parts[1]
    try:
        paired_staves = [
            StaffReading(
                PianoReading.PAIRED, 1, piano.staves[hand].measures, tuple(paired_sizes[1])
            )
            for hand in (RIGHT, LEFT)
        ]
        alone_staves = [
            StaffReading(
                PianoReading.ALONE,
                part,
                alone.parts[part].staves[0].measures,
                tuple(alone_sizes[part]),
            )
            for part in (1, 2)
        ]
        choices = choose_readings(paired_staves, alone_staves)
    except ValueError:
        return None
    spliced = [
        _splice(
            (paired_staves[hand], alone_staves[hand]),
            [choice.right if hand == RIGHT else choice.left for choice in choices],
        )
        for hand in (RIGHT, LEFT)
    ]
    hands = _renumber_slurs(spliced)
    combined = Part(
        id=piano.id,
        staves=tuple(
            Staff(id=piano.staves[hand].id, measures=tuple(hands[hand])) for hand in (RIGHT, LEFT)
        ),
    )
    return ScoreIR(parts=(paired.parts[0], combined)), choices


def combine_musicxml(paired_xml: str, alone_xml: str) -> str:
    """El MusicXML de la combinación de las dos lecturas de HOMR de una página de voz y piano.

    Sale del `ScoreIR` combinado con el exportador de Cadenza, que importado da el mismo
    `ScoreIR` (salvo, a veces, cómo se emparejan los extremos de una ligadura de expresión, como
    en toda exportación). Si las lecturas no se pueden combinar, o algo falla al hacerlo, el
    MusicXML de la emparejada tal cual: la combinación no debe hacer fallar una transcripción que
    con #239 salía."""

    from cadenza.interchange import musicxml_to_score_ir, score_ir_to_musicxml

    try:
        combined = combine_voice_and_piano(
            musicxml_to_score_ir(paired_xml),
            paired_xml,
            musicxml_to_score_ir(alone_xml),
            alone_xml,
        )
        if combined is None:
            return paired_xml
        return score_ir_to_musicxml(combined[0])
    except Exception:
        _LOGGER.exception("No se combinaron las lecturas del piano; queda la emparejada")
        return paired_xml


__all__ = [
    "LEFT",
    "RIGHT",
    "StaffReading",
    "SystemChoice",
    "choose_readings",
    "combine_musicxml",
    "combine_voice_and_piano",
    "system_sizes",
    "usual_duration",
]
