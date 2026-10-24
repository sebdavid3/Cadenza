"""Marcas de notación en la ida y vuelta MusicXML ↔ `ScoreIR` (ADR-0031, #213).

Las fixtures `marks_piano.musicxml` (dos pentagramas, dos voces en el primero) y
`marks_melody.musicxml` (una voz) llevan todas las marcas del alcance: articulaciones,
calderones (también en un silencio y en la segunda voz), ligaduras de expresión dentro del
compás, entre compases, entre sistemas, entre pentagramas y desde una nota de adorno, las doce
dinámicas (una desplazada con `<offset>`) y reguladores que acaban antes de un acorde, a mitad
de compás y en el compás siguiente.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from cadenza.domain import (
    Articulation,
    Dynamic,
    DynamicMark,
    Event,
    EventKind,
    Measure,
    Part,
    ScoreIR,
    Slur,
    SlurType,
    Staff,
    TimeSignature,
    Wedge,
    WedgeType,
)
from cadenza.interchange import (
    musicxml_to_score_ir,
    read_score,
    score_ir_to_midi,
    score_ir_to_musicxml,
)

FIXTURES = Path(__file__).parent / "fixtures"
PIANO = FIXTURES / "marks_piano.musicxml"
MELODY = FIXTURES / "marks_melody.musicxml"

Key = tuple[int, int, int, int]  # pentagrama, compás, voz, índice en la voz


def _read(path: Path) -> ScoreIR:
    return musicxml_to_score_ir(path.read_text(encoding="utf-8"))


def _staves(score: ScoreIR) -> tuple[Staff, ...]:
    assert len(score.parts) == 1
    return score.parts[0].staves


def _event_marks(
    score: ScoreIR,
) -> dict[Key, tuple[str | None, tuple[str, ...], bool, tuple[str, ...]]]:
    """Marcas de cada evento que tiene alguna, por su ruta lógica."""

    found = {}
    for staff_index, staff in enumerate(_staves(score)):
        for measure in staff.measures:
            counters: dict[int, int] = {}
            for event in measure.events:
                index = counters.get(event.voice, 0)
                counters[event.voice] = index + 1
                if event.articulations or event.fermata or event.slurs:
                    found[(staff_index, measure.number, event.voice, index)] = (
                        event.pitch,
                        tuple(a.value for a in event.articulations),
                        event.fermata,
                        tuple(f"{s.type.value} {s.number}" for s in event.slurs),
                    )
    return found


def _positioned_marks(score: ScoreIR) -> dict[tuple[int, int], tuple[list[str], list[str]]]:
    """Dinámicas y reguladores de cada compás que tiene alguno."""

    found = {}
    for staff_index, staff in enumerate(_staves(score)):
        for measure in staff.measures:
            if measure.dynamics or measure.wedges:
                found[(staff_index, measure.number)] = (
                    [f"{d.mark.value}@{d.offset_beats}" for d in measure.dynamics],
                    [f"{w.type.value} {w.number}@{w.offset_beats}" for w in measure.wedges],
                )
    return found


def _without_marks(score: ScoreIR) -> ScoreIR:
    return replace(
        score,
        parts=tuple(
            replace(
                part,
                staves=tuple(
                    replace(
                        staff,
                        measures=tuple(
                            replace(
                                measure,
                                dynamics=(),
                                wedges=(),
                                events=tuple(
                                    replace(event, articulations=(), fermata=False, slurs=())
                                    for event in measure.events
                                ),
                            )
                            for measure in staff.measures
                        ),
                    )
                    for staff in part.staves
                ),
            )
            for part in score.parts
        ),
    )


def _strip_marks_from_musicxml(xml_text: str) -> str:
    """El mismo MusicXML sin ninguna marca: ni en las notas ni en las indicaciones."""

    root = ET.fromstring(xml_text.encode("utf-8"))
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag == "notations":
                for mark in list(child):
                    if mark.tag in ("slur", "articulations", "fermata"):
                        child.remove(mark)
                if len(child) == 0:
                    parent.remove(child)
            elif child.tag == "direction" and (
                child.find("direction-type/dynamics") is not None
                or child.find("direction-type/wedge") is not None
            ):
                parent.remove(child)
    return ET.tostring(root, encoding="unicode")


def test_piano_marks_are_read_by_staff_and_voice() -> None:
    score = _read(PIANO)

    assert _event_marks(score) == {
        (0, 1, 0, 0): ("C5", ("staccato",), False, ("start 1",)),
        (0, 1, 0, 1): ("D5", ("accent",), False, ()),
        (0, 1, 0, 2): ("E5", ("staccato", "tenuto"), False, ()),
        (0, 1, 0, 3): ("F5", (), True, ("stop 1", "start 2")),
        (0, 1, 1, 0): ("E4", (), True, ()),
        (0, 2, 0, 0): ("G5", (), False, ("stop 2",)),
        (0, 2, 0, 2): (None, (), True, ()),
        (0, 3, 0, 0): ("C5", (), False, ("start 3",)),
        (1, 1, 0, 0): ("C3", ("marcato",), False, ()),
        # Las marcas de un acorde van en su primera nota.
        (1, 1, 0, 1): ("C3", ("staccatissimo",), False, ()),
        # Ligadura entre pentagramas.
        (1, 3, 0, 1): ("G2", (), False, ("stop 3",)),
    }
    assert _positioned_marks(score) == {
        (0, 1): (["p@0"], []),
        (0, 2): (["mf@0", "sfz@2"], []),
        # El crescendo acaba antes del acorde, no en la nota anterior.
        (1, 1): ([], ["crescendo 1@0", "stop 1@2"]),
        (1, 2): (["ff@0"], ["diminuendo 2@1"]),
        (1, 3): (["pp@0"], ["stop 2@0"]),
    }


def test_single_voice_marks_are_read() -> None:
    score = _read(MELODY)

    assert _event_marks(score) == {
        (0, 1, 0, 0): ("C5", ("staccato",), False, ()),
        (0, 1, 0, 1): ("D5", ("staccatissimo",), False, ()),
        (0, 1, 0, 2): ("E5", ("accent",), False, ("start 1",)),
        (0, 1, 0, 3): ("F5", ("marcato",), False, ()),
        (0, 2, 0, 0): ("G5", ("tenuto",), False, ("stop 1",)),
        # Nota de adorno (sin duración) ligada a la nota real.
        (0, 2, 0, 1): ("A5", (), False, ("start 2",)),
        (0, 2, 0, 2): ("B5", (), False, ("stop 2",)),
        (0, 2, 0, 3): (None, (), True, ()),
        (0, 3, 0, 0): ("C5", (), True, ()),
        (0, 3, 0, 1): ("B4", ("staccato",), False, ("start 3",)),
        (0, 3, 0, 2): ("C5", ("accent",), False, ()),
        # Ligadura que cruza el salto de sistema.
        (0, 4, 0, 0): ("C6", (), True, ("stop 3",)),
    }
    assert _positioned_marks(score) == {
        (0, 1): (["mf@0"], ["crescendo 1@1", "stop 1@3"]),
        (0, 2): (["fp@0", "sf@2"], ["diminuendo 2@3"]),
        # `f` lleva <offset> de una negra: cae a mitad de la blanca.
        (0, 3): (["ppp@0", "f@1", "mp@2", "fz@3"], ["stop 2@2"]),
        (0, 4): (["fff@0"], []),
    }


def test_the_twelve_dynamics_of_the_scope_are_covered_by_the_fixtures() -> None:
    marks = {
        d.mark
        for path in (PIANO, MELODY)
        for staff in _staves(_read(path))
        for measure in staff.measures
        for d in measure.dynamics
    }
    assert marks == set(DynamicMark)


@pytest.mark.parametrize("path", [PIANO, MELODY], ids=["piano", "melodia"])
def test_musicxml_roundtrip_keeps_every_mark(path: Path) -> None:
    score = _read(path)
    again = musicxml_to_score_ir(score_ir_to_musicxml(score))

    assert _event_marks(again) == _event_marks(score)
    assert _positioned_marks(again) == _positioned_marks(score)
    assert again == score


@pytest.mark.parametrize("path", [PIANO, MELODY], ids=["piano", "melodia"])
def test_reading_marks_does_not_change_the_events(path: Path) -> None:
    """Con o sin marcas en el MusicXML, los eventos y los compases son los mismos."""

    xml_text = path.read_text(encoding="utf-8")
    plain = musicxml_to_score_ir(_strip_marks_from_musicxml(xml_text))
    assert _event_marks(plain) == {}
    assert _positioned_marks(plain) == {}
    assert _without_marks(musicxml_to_score_ir(xml_text)) == plain


def test_exported_musicxml_writes_every_mark() -> None:
    root = ET.fromstring(score_ir_to_musicxml(_read(PIANO)).encode("utf-8"))

    articulations = [
        a.tag
        for a in root.iter()
        if a.tag in {"staccato", "staccatissimo", "accent", "strong-accent", "tenuto"}
    ]
    assert sorted(articulations) == sorted(
        ["staccato", "accent", "tenuto", "staccato", "strong-accent", "staccatissimo"]
    )
    fermatas = list(root.iter("fermata"))
    assert len(fermatas) == 3
    # Sin tipo guardado, el calderón se dibuja sobre la nota.
    assert {f.get("type") for f in fermatas} == {"upright"}
    slurs = sorted(s.get("type") or "" for s in root.iter("slur"))
    assert slurs == ["start", "start", "start", "stop", "stop", "stop"]
    dynamics = sorted(child.tag for d in root.iter("dynamics") for child in d)
    assert dynamics == sorted(["p", "mf", "sfz", "ff", "pp"])
    wedges = sorted(w.get("type") or "" for w in root.iter("wedge"))
    assert wedges == ["crescendo", "diminuendo", "stop", "stop"]


def test_read_score_reads_the_same_marks_from_musicxml_and_mxl(tmp_path: Path) -> None:
    expected = _read(PIANO)
    assert read_score(PIANO) == expected

    archive = tmp_path / "marks_piano.mxl"
    with zipfile.ZipFile(archive, "w") as mxl:
        mxl.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<container><rootfiles>"
            '<rootfile full-path="score/marks_piano.musicxml"/>'
            "</rootfiles></container>",
        )
        mxl.write(PIANO, "score/marks_piano.musicxml")
    assert read_score(archive) == expected


def test_midi_export_ignores_the_marks() -> None:
    """El volumen según las dinámicas es otro issue (#215): el MIDI no cambia con las marcas."""

    score = _read(PIANO)
    assert score_ir_to_midi(score) == score_ir_to_midi(_without_marks(score))


def _one_voice(*measures: Measure) -> ScoreIR:
    return ScoreIR(parts=(Part(id="P1", staves=(Staff(id="part-0-staff-0", measures=measures),)),))


def _note(pitch: str, beats: str = "1", **marks: Any) -> Event:
    return Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=Fraction(beats), **marks)


def test_orphan_slur_and_wedge_ends_are_kept_but_not_drawn() -> None:
    """Un extremo sin pareja (p. ej. tras borrar su nota) se conserva y no se exporta (ADR-0031)."""

    score = _one_voice(
        Measure(
            number=1,
            time_signature=TimeSignature(4, 4),
            events=(
                _note("C5", slurs=(Slur(SlurType.START, 1),)),
                _note("D5", slurs=(Slur(SlurType.STOP, 2),)),
                _note("E5", "2"),
            ),
            wedges=(
                Wedge(WedgeType.CRESCENDO, 1, Fraction(0)),
                Wedge(WedgeType.STOP, 2, Fraction(3)),
            ),
        )
    )
    root = ET.fromstring(score_ir_to_musicxml(score).encode("utf-8"))
    assert list(root.iter("slur")) == []
    assert list(root.iter("wedge")) == []


def _unambiguous(root: ET.Element, tag: str) -> bool:
    """Si emparejando por `number` en orden de lectura, como MusicXML y OSMD, cada inicio
    encuentra libre su número y cada fin cierra uno abierto."""

    for part in root.iter("part"):
        open_numbers: set[str] = set()
        for element in part.iter(tag):
            number = element.get("number", "1")
            if element.get("type") == "stop":
                if number not in open_numbers:
                    return False
                open_numbers.remove(number)
            elif element.get("type") in ("start", "crescendo", "diminuendo"):
                if number in open_numbers:
                    return False
                open_numbers.add(number)
    return True


def test_overlapping_slurs_and_wedges_get_distinct_musicxml_numbers() -> None:
    """music21 numera del 1 al 6 en ciclo, sin mirar solapes: una ligadura larga de la mano
    izquierda compartía número con una abierta de la derecha y el MusicXML las emparejaba mal."""

    right, left = [], []
    for number in range(1, 9):
        right.append(
            Measure(
                number=number,
                time_signature=TimeSignature(2, 4),
                events=(
                    _note("C5", slurs=(Slur(SlurType.START, number),)),
                    _note("D5", slurs=(Slur(SlurType.STOP, number),)),
                ),
                wedges=(
                    Wedge(WedgeType.CRESCENDO, number, Fraction(0)),
                    Wedge(WedgeType.STOP, number, Fraction(1)),
                ),
            )
        )
        left.append(
            Measure(
                number=number,
                time_signature=TimeSignature(2, 4),
                events=(
                    _note("C3", slurs=(Slur(SlurType.START, 9),) if number == 1 else ()),
                    _note("D3", slurs=(Slur(SlurType.STOP, 9),) if number == 3 else ()),
                ),
                wedges=(
                    (Wedge(WedgeType.DIMINUENDO, 9, Fraction(0)),)
                    if number == 1
                    else (Wedge(WedgeType.STOP, 9, Fraction(2)),) if number == 3 else ()
                ),
            )
        )
    score = ScoreIR(
        parts=(
            Part(
                id="part-0",
                staves=(
                    Staff(id="part-0-staff-0", measures=tuple(right)),
                    Staff(id="part-0-staff-1", measures=tuple(left)),
                ),
            ),
        )
    )
    xml_text = score_ir_to_musicxml(score)
    root = ET.fromstring(xml_text.encode("utf-8"))
    assert len(list(root.iter("slur"))) == 18
    assert len(list(root.iter("wedge"))) == 18
    assert _unambiguous(root, "slur")
    assert _unambiguous(root, "wedge")

    # Al volver a leerlo, cada ligadura y cada regulador unen los mismos puntos.
    again = musicxml_to_score_ir(xml_text)
    assert _span_ends(again) == _span_ends(score)
    assert len(_span_ends(again)[0]) == 9
    assert len(_span_ends(again)[1]) == 9


def test_slurs_whose_start_is_written_after_their_end_are_reversed() -> None:
    """Una ligadura de la mano izquierda a la derecha, o de la segunda voz a la primera, en el
    mismo compás: music21 escribe antes el pentagrama superior y la primera voz, así que su fin
    quedaba delante de su inicio y, al leerlo, el inicio se emparejaba con el fin de otra."""

    def right(number: int, *slurs: tuple[int, SlurType, int]) -> Measure:
        marks = {(event, kind): n for event, kind, n in slurs}

        def ends(event: int) -> tuple[Slur, ...]:
            return tuple(Slur(kind, n) for (e, kind), n in marks.items() if e == event)

        return Measure(
            number=number,
            time_signature=TimeSignature(2, 4),
            events=(
                _note("C5", slurs=ends(0)),
                _note("D5", slurs=ends(1)),
                _note("E4", "2", voice=1, slurs=ends(2)),
            ),
        )

    def left(number: int, *slurs: Slur) -> Measure:
        return Measure(
            number=number,
            time_signature=TimeSignature(2, 4),
            events=(_note("C3", "2", slurs=slurs),),
        )

    score = ScoreIR(
        parts=(
            Part(
                id="part-0",
                staves=(
                    Staff(
                        id="part-0-staff-0",
                        measures=(
                            # 1: de la mano izquierda (Do3) al Re5 de la derecha.
                            right(1, (1, SlurType.STOP, 1)),
                            # 2: de la segunda voz (Mi4) al Re5 de la primera.
                            right(2, (2, SlurType.START, 2), (1, SlurType.STOP, 2)),
                            # 3 y 4: ligaduras normales que reutilizarían los números.
                            right(3, (0, SlurType.START, 3), (1, SlurType.STOP, 3)),
                            right(4, (0, SlurType.START, 4), (1, SlurType.STOP, 4)),
                        ),
                    ),
                    Staff(
                        id="part-0-staff-1",
                        measures=(
                            left(1, Slur(SlurType.START, 1)),
                            left(2),
                            left(3, Slur(SlurType.START, 5)),
                            left(4, Slur(SlurType.STOP, 5)),
                        ),
                    ),
                ),
            ),
        )
    )
    xml_text = score_ir_to_musicxml(score)
    root = ET.fromstring(xml_text.encode("utf-8"))
    assert _unambiguous(root, "slur")
    again = musicxml_to_score_ir(xml_text)
    # Une las mismas notas, aunque el inicio y el fin hayan cambiado de papel.
    assert _unordered(_span_ends(again)[0]) == _unordered(_span_ends(score)[0])
    assert len(_span_ends(again)[0]) == 5


def _unordered(pairs: list[tuple[Any, Any]]) -> list[tuple[Any, Any]]:
    return sorted(tuple(sorted(pair)) for pair in pairs)


def _span_ends(score: ScoreIR) -> tuple[list[tuple[Any, Any]], list[tuple[Any, Any]]]:
    """Pares (inicio, fin) de ligaduras y de reguladores por su posición, sin su número."""

    slur_ends: dict[tuple[int, str], list[tuple[int, int, int]]] = {}
    wedge_ends: dict[tuple[int, str], list[tuple[int, int, Fraction, str]]] = {}
    for staff_index, staff in enumerate(_staves(score)):
        for measure in staff.measures:
            for index, event in enumerate(measure.events):
                for slur in event.slurs:
                    slur_ends.setdefault((slur.number, slur.type.value), []).append(
                        (staff_index, measure.number, index)
                    )
            for wedge in measure.wedges:
                end = "stop" if wedge.type is WedgeType.STOP else "start"
                wedge_ends.setdefault((wedge.number, end), []).append(
                    (staff_index, measure.number, wedge.offset_beats, wedge.type.value)
                )
    slurs = sorted(
        (ends[0], slur_ends[(number, "stop")][0])
        for (number, kind), ends in slur_ends.items()
        if kind == "start"
    )
    wedges = sorted(
        (ends[0], wedge_ends[(number, "stop")][0])
        for (number, kind), ends in wedge_ends.items()
        if kind == "start"
    )
    return slurs, wedges


def test_marks_on_a_chord_are_written_once_on_the_chord() -> None:
    score = _one_voice(
        Measure(
            number=1,
            time_signature=TimeSignature(4, 4),
            events=(
                _note("C4", "4", articulations=(Articulation.ACCENT,), fermata=True),
                _note("E4", "4", is_chord=True, articulations=(Articulation.TENUTO,)),
            ),
            dynamics=(Dynamic(DynamicMark.MP, Fraction(1, 2)),),
        )
    )
    root = ET.fromstring(score_ir_to_musicxml(score).encode("utf-8"))
    assert sorted(a.tag for a in root.iter() if a.tag in {"accent", "tenuto"}) == [
        "accent",
        "tenuto",
    ]
    assert len(list(root.iter("fermata"))) == 1

    again = musicxml_to_score_ir(score_ir_to_musicxml(score))
    head = again.parts[0].staves[0].measures[0].events[0]
    assert head.articulations == (Articulation.ACCENT, Articulation.TENUTO)
    assert head.fermata is True
    assert again.parts[0].staves[0].measures[0].dynamics == (
        Dynamic(DynamicMark.MP, Fraction(1, 2)),
    )


def test_marks_outside_the_scope_are_ignored() -> None:
    """Ornamentos, texto, pedal y otras dinámicas quedan fuera (ADR-0031)."""

    xml_text = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>x</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>1</divisions><time><beats>2</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef></attributes>
      <direction><direction-type><dynamics><sfp/></dynamics></direction-type></direction>
      <direction><direction-type><words>dolce</words></direction-type></direction>
      <direction><direction-type><pedal type="start"/></direction-type></direction>
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration><type>quarter</type>
        <notations><ornaments><trill-mark/></ornaments><articulations><detached-legato/></articulations></notations></note>
      <direction><direction-type><pedal type="stop"/></direction-type></direction>
      <note><pitch><step>D</step><octave>5</octave></pitch><duration>1</duration><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>
"""
    score = musicxml_to_score_ir(xml_text)
    assert _event_marks(score) == {}
    assert _positioned_marks(score) == {}
    assert [e.pitch for e in score.parts[0].staves[0].measures[0].events] == ["C5", "D5"]
