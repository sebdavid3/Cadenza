"""El título, el compositor y el instrumento de cada parte en el MusicXML y el MIDI (#235).

ADR-0041: sin metadatos, la exportación es la de siempre; con ellos, el MusicXML lleva
`work-title`, `creator` y, en cada `score-part`, su nombre, `score-instrument` y
`midi-instrument`, y el MIDI, el programa de cada parte.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from cadenza.application import ScoreExporter
from cadenza.domain import Instrument, PartMetadata, ScoreIR, ScoreMetadata
from cadenza.interchange import (
    Music21ScoreExporter,
    musicxml_to_score_ir,
    read_score,
    score_ir_to_midi,
    score_ir_to_musicxml,
)
from music21 import midi

FIXTURES = Path(__file__).parent / "fixtures"
PROGRAM_CHANGE = 0xC0


def _voice_and_piano() -> ScoreIR:
    """Una parte de un pentagrama y otra de dos, como las detecta HOMR en *Mondnacht*."""
    melody = read_score(FIXTURES / "simple.musicxml").parts[0]
    piano = read_score(FIXTURES / "piano.musicxml").parts[0]
    return ScoreIR(parts=(melody, piano))


def _stable(xml_text: str) -> str:
    """Sin lo que cambia entre dos exportaciones iguales: la fecha y los id de las partes."""
    without_date = re.sub(r"<encoding-date>[^<]*</encoding-date>", "", xml_text)
    return re.sub(r'"P[0-9a-f]{32}', '"P', without_date)


def _root(xml_text: str) -> ET.Element:
    return ET.fromstring(xml_text.encode("utf-8"))


def _programs(data: bytes) -> list[list[int]]:
    """Los programas distintos que fija cada pista del MIDI (music21 repite el cambio)."""
    mf = midi.MidiFile()
    mf.readstr(data)
    return [
        list(dict.fromkeys(int(e.data) for e in track.events if e.type == PROGRAM_CHANGE))
        for track in mf.tracks
    ]


METADATA = ScoreMetadata(
    title="Mondnacht",
    composer="Robert Schumann",
    parts=(PartMetadata(Instrument.VOICE), PartMetadata(Instrument.PIANO)),
)


@pytest.mark.parametrize("metadata", [None, ScoreMetadata()])
def test_without_metadata_the_musicxml_is_the_same_as_before(
    metadata: ScoreMetadata | None,
) -> None:
    score = _voice_and_piano()
    assert _stable(score_ir_to_musicxml(score, metadata)) == _stable(score_ir_to_musicxml(score))


@pytest.mark.parametrize("metadata", [None, ScoreMetadata()])
def test_without_metadata_the_midi_is_the_same_as_before(metadata: ScoreMetadata | None) -> None:
    score = _voice_and_piano()
    assert score_ir_to_midi(score, metadata) == score_ir_to_midi(score)
    assert all(programs == [] for programs in _programs(score_ir_to_midi(score)))


def test_title_and_composer_are_written() -> None:
    root = _root(score_ir_to_musicxml(_voice_and_piano(), METADATA))

    # `work` va antes que todo lo demás en `score-partwise` (MusicXML 4.0).
    assert root[0].tag == "work"
    assert root.findtext("work/work-title") == "Mondnacht"
    creators = root.findall("identification/creator")
    assert [(c.get("type"), c.text) for c in creators] == [("composer", "Robert Schumann")]
    # `creator` va antes que `encoding` en `identification`.
    identification = root.find("identification")
    assert identification is not None
    assert identification[0].tag == "creator"
    assert root.find("movement-title") is None


def test_each_part_has_its_name_and_instrument() -> None:
    root = _root(score_ir_to_musicxml(_voice_and_piano(), METADATA))

    score_parts = root.findall("part-list/score-part")
    assert len(score_parts) == 2
    expected = [("Voz", "53", "1", "voice.vocals"), ("Piano", "1", "2", "keyboard.piano")]
    for score_part, (name, program, channel, sound) in zip(score_parts, expected, strict=True):
        tags = [child.tag for child in score_part]
        assert tags == ["part-name", "score-instrument", "midi-instrument"]
        assert score_part.findtext("part-name") == name
        instrument_id = score_part.find("score-instrument")
        assert instrument_id is not None
        assert instrument_id.get("id") == f"{score_part.get('id')}-I1"
        assert score_part.findtext("score-instrument/instrument-name") == name
        assert score_part.findtext("score-instrument/instrument-sound") == sound
        midi_instrument = score_part.find("midi-instrument")
        assert midi_instrument is not None
        assert midi_instrument.get("id") == instrument_id.get("id")
        assert midi_instrument.findtext("midi-channel") == channel
        assert midi_instrument.findtext("midi-program") == program


def test_a_given_name_is_the_part_name_and_other_sounds_as_piano() -> None:
    metadata = ScoreMetadata(
        parts=(
            PartMetadata(Instrument.OTHER, name="Theremin"),
            PartMetadata(name="Mano derecha y mano izquierda"),
        )
    )
    root = _root(score_ir_to_musicxml(_voice_and_piano(), metadata))

    first, second = root.findall("part-list/score-part")
    assert first.findtext("part-name") == "Theremin"
    assert first.findtext("score-instrument/instrument-name") == "Theremin"
    assert first.find("score-instrument/instrument-sound") is None
    assert first.findtext("midi-instrument/midi-program") == "1"
    # Un nombre sin instrumento: solo el nombre.
    assert second.findtext("part-name") == "Mano derecha y mano izquierda"
    assert second.find("score-instrument") is None
    assert second.find("midi-instrument") is None
    assert root.find("work") is None
    assert root.find("identification/creator") is None


def test_part_without_data_is_written_as_before() -> None:
    plain = _root(score_ir_to_musicxml(_voice_and_piano())).findall("part-list/score-part")[1]
    only_first = _root(
        score_ir_to_musicxml(
            _voice_and_piano(), ScoreMetadata(parts=(PartMetadata(Instrument.VOICE),))
        )
    ).findall("part-list/score-part")[1]
    assert [child.tag for child in only_first] == [child.tag for child in plain]
    assert only_first.findtext("part-name") == plain.findtext("part-name")


def test_text_is_escaped() -> None:
    metadata = ScoreMetadata(title='Lied <Nr. 2> & "Coda"', composer="Fanny & Felix")
    root = _root(score_ir_to_musicxml(_voice_and_piano(), metadata))
    assert root.findtext("work/work-title") == 'Lied <Nr. 2> & "Coda"'
    assert root.findtext("identification/creator") == "Fanny & Felix"


def test_metadata_does_not_change_the_imported_score() -> None:
    score = _voice_and_piano()
    with_metadata = musicxml_to_score_ir(score_ir_to_musicxml(score, METADATA))
    without = musicxml_to_score_ir(score_ir_to_musicxml(score))
    assert with_metadata == without


def test_midi_sets_the_program_of_each_part() -> None:
    data = score_ir_to_midi(_voice_and_piano(), METADATA)

    # La pista 0 es la de tempo; la voz tiene una pista y el piano, una por pentagrama. El MIDI
    # numera los programas desde 0: la voz (53 en MusicXML) es el 52 y el piano, el 0.
    assert _programs(data)[1:] == [[52], [0], [0]]


def test_midi_part_without_instrument_has_no_program_change() -> None:
    metadata = ScoreMetadata(parts=(PartMetadata(), PartMetadata(Instrument.CELLO)))
    assert _programs(score_ir_to_midi(_voice_and_piano(), metadata))[1:] == [[], [42], [42]]


def test_exporter_port_passes_the_metadata() -> None:
    exporter: ScoreExporter = Music21ScoreExporter()
    score = _voice_and_piano()

    root = _root(exporter.to_musicxml(score, METADATA))
    assert root.findtext("work/work-title") == "Mondnacht"
    assert _programs(exporter.to_midi(score, METADATA))[1:] == [[52], [0], [0]]
    assert _stable(exporter.to_musicxml(score)) == _stable(score_ir_to_musicxml(score))
