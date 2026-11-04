"""El MusicXML de unos compases de una partitura, para la verdad del banco del estudio (#247).

Un recorte que empieza a mitad de la pieza lleva al principio el compás, la armadura y la
clave que rigen allí, aunque la página recortada no los imprima; sus compases se numeran desde
1, como los de una transcripción de HOMR, y la salida no depende del día en que se escribe.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from cadenza.interchange import InterchangeError, musicxml_excerpt, read_score


def _note(step: str, octave: int, beats: int, staff: int | None = None) -> str:
    kind = {1: "quarter", 2: "half", 3: "half"}[beats]
    dot = "<dot/>" if beats == 3 else ""
    staff_tag = f"<staff>{staff}</staff>" if staff is not None else ""
    return (
        f"<note><pitch><step>{step}</step><octave>{octave}</octave></pitch>"
        f"<duration>{beats}</duration><voice>1</voice><type>{kind}</type>{dot}{staff_tag}</note>"
    )


def _voice_measure(number: int, step: str) -> str:
    attributes = (
        "<attributes><divisions>1</divisions><key><fifths>-3</fifths></key>"
        "<time><beats>3</beats><beat-type>4</beat-type></time>"
        "<clef><sign>G</sign><line>2</line></clef></attributes>"
        if number == 1
        else ""
    )
    return f'<measure number="{number}">{attributes}{_note(step, 5, 3)}</measure>'


def _piano_measure(number: int, upper: str, lower: tuple[str, str], clef_change: str) -> str:
    """Un compás del piano: una blanca con puntillo arriba y, abajo, dos notas con un cambio
    de clave entre ellas (o sin cambio si `clef_change` está vacío)."""

    attributes = (
        "<attributes><divisions>1</divisions><key><fifths>-3</fifths></key>"
        "<time><beats>3</beats><beat-type>4</beat-type></time><staves>2</staves>"
        '<clef number="1"><sign>G</sign><line>2</line></clef>'
        '<clef number="2"><sign>F</sign><line>4</line></clef></attributes>'
        if number == 1
        else ""
    )
    change = (
        f'<attributes><clef number="2"><sign>{clef_change[0]}</sign>'
        f"<line>{clef_change[1]}</line></clef></attributes>"
        if clef_change
        else ""
    )
    return (
        f'<measure number="{number}">{attributes}{_note(upper, 5, 3, 1)}'
        f"<backup><duration>3</duration></backup>"
        f"{_note(lower[0], 3, 1, 2)}{change}{_note(lower[1], 4, 2, 2)}</measure>"
    )


def _song(tmp_path: Path) -> Path:
    """Voz y piano en 3/4 con tres bemoles y cuatro compases; el pentagrama inferior del piano
    pasa a clave de sol a mitad del compás 2 y vuelve a la de fa a mitad del 3."""

    voice = "".join(_voice_measure(n, s) for n, s in ((1, "C"), (2, "D"), (3, "E"), (4, "F")))
    piano = "".join(
        (
            _piano_measure(1, "G", ("C", "D"), ""),
            _piano_measure(2, "A", ("E", "F"), "G2"),
            _piano_measure(3, "B", ("G", "A"), "F4"),
            _piano_measure(4, "C", ("B", "C"), ""),
        )
    )
    path = tmp_path / "song.musicxml"
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="Pvoz"><part-name>Voice</part-name>
      <score-instrument id="Pvoz-I7"><instrument-name>Voice</instrument-name></score-instrument>
    </score-part>
    <score-part id="Ppiano"><part-name>Piano</part-name>
      <score-instrument id="Ppiano-I3"><instrument-name>Piano</instrument-name></score-instrument>
    </score-part>
  </part-list>
  <part id="Pvoz">{voice}</part>
  <part id="Ppiano">{piano}</part>
</score-partwise>""",
        encoding="utf-8",
    )
    return path


def _parts(xml: str) -> list[ET.Element]:
    return ET.fromstring(xml.encode("utf-8")).findall("part")


def _start_attributes(measure: ET.Element) -> ET.Element:
    """Los atributos del principio del compás (antes de la primera nota)."""

    for child in measure:
        if child.tag == "attributes":
            return child
        if child.tag == "note":
            break
    raise AssertionError("el compás no empieza con atributos")


def test_the_excerpt_keeps_only_its_measures_numbered_from_one(tmp_path: Path) -> None:
    xml = musicxml_excerpt(_song(tmp_path), 3, 4)

    for part in _parts(xml):
        assert [m.get("number") for m in part.findall("measure")] == ["1", "2"]
    score = read_score(_written(tmp_path, xml))
    staves = {len(part.staves): part.staves for part in score.parts}
    voice = staves[1][0].measures
    assert [[e.pitch for e in m.events] for m in voice] == [["E5"], ["F5"]]
    lower = staves[2][1].measures
    assert [[e.pitch for e in m.events] for m in lower] == [["G3", "A4"], ["B3", "C4"]]


def test_the_first_measure_carries_the_meter_key_and_clef_in_force(tmp_path: Path) -> None:
    xml = musicxml_excerpt(_song(tmp_path), 3, 4)

    voice, piano = _parts(xml)
    attributes = _start_attributes(voice.findall("measure")[0])
    assert attributes.findtext("key/fifths") == "-3"
    assert attributes.findtext("time/beats") == "3"
    assert attributes.findtext("time/beat-type") == "4"
    assert attributes.findtext("clef/sign") == "G"

    attributes = _start_attributes(piano.findall("measure")[0])
    assert attributes.findtext("key/fifths") == "-3"
    assert attributes.findtext("time/beats") == "3"
    clefs = {c.get("number"): c.findtext("sign") for c in attributes.findall("clef")}
    # El pentagrama inferior empieza el compás 3 en clave de sol (cambió a mitad del 2)...
    assert clefs == {"1": "G", "2": "G"}
    # ...y la vuelta a la de fa a mitad del compás se conserva donde está.
    first = piano.findall("measure")[0]
    later = [a for a in first.findall("attributes") if a is not attributes]
    assert [c.findtext("sign") for a in later for c in a.findall("clef")] == ["F"]


def test_without_a_range_the_whole_score_is_written(tmp_path: Path) -> None:
    xml = musicxml_excerpt(_song(tmp_path))

    for part in _parts(xml):
        assert [m.get("number") for m in part.findall("measure")] == ["1", "2", "3", "4"]


def test_no_title_or_composer_is_made_up(tmp_path: Path) -> None:
    root = ET.fromstring(musicxml_excerpt(_song(tmp_path)).encode("utf-8"))

    assert root.find("movement-title") is None
    assert root.find("identification/creator") is None


def test_the_output_does_not_depend_on_the_day(tmp_path: Path) -> None:
    # Ni la fecha ni los identificadores que music21 inventa en cada escritura.
    xml = musicxml_excerpt(_song(tmp_path), 2, 3)

    root = ET.fromstring(xml.encode("utf-8"))
    assert root.find("identification/encoding/encoding-date") is None
    assert [p.get("id") for p in root.findall("part-list/score-part")] == ["P1", "P2"]
    assert [i.get("id") for i in root.iter("score-instrument")] == ["P1-I1", "P2-I1"]
    assert [p.get("id") for p in root.findall("part")] == ["P1", "P2"]
    assert xml == musicxml_excerpt(_song(tmp_path), 2, 3)


@pytest.mark.parametrize(("first", "last"), [(0, 2), (3, 2), (2, 5), (None, 2), (2, None)])
def test_an_impossible_range_is_refused(
    tmp_path: Path, first: int | None, last: int | None
) -> None:
    with pytest.raises(InterchangeError):
        musicxml_excerpt(_song(tmp_path), first, last)


def _written(tmp_path: Path, xml: str) -> Path:
    path = tmp_path / "excerpt.musicxml"
    path.write_text(xml, encoding="utf-8")
    return path
