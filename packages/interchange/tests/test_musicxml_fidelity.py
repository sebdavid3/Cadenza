"""Fidelidad del MusicXML exportado al `ScoreIR` materializado (#152).

El exportador alimenta la vista de la partitura (OSMD) y la descarga del usuario: cada compás
debe salir con sus eventos tal cual, la métrica solo donde cambia y sin metadatos de relleno.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction

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
from cadenza.interchange import musicxml_to_score_ir, score_ir_to_musicxml

THREE_FOUR = TimeSignature(beats=3, beat_type=4)


def _note(
    pitch: str,
    beats: str,
    *,
    voice: int = 0,
    tie: Tie | None = None,
    is_chord: bool = False,
) -> Event:
    return Event(
        kind=EventKind.NOTE,
        voice=voice,
        pitch=pitch,
        duration_beats=Fraction(beats),
        tie=tie,
        is_chord=is_chord,
    )


def _rest(beats: str, *, voice: int = 0) -> Event:
    return Event(kind=EventKind.REST, voice=voice, duration_beats=Fraction(beats))


def _score(*measures: Measure) -> ScoreIR:
    return ScoreIR(parts=(Part(id="P1", staves=(Staff(id="part-0-staff-0", measures=measures),)),))


def _first(number: int, *events: Event, signature: TimeSignature = THREE_FOUR) -> Measure:
    return Measure(
        number=number,
        events=events,
        time_signature=signature,
        clef=Clef(sign="G", line=2),
        key_signature=KeySignature(fifths=0),
    )


def _next(number: int, *events: Event, signature: TimeSignature = THREE_FOUR) -> Measure:
    # Como en la importación, cada compás lleva su métrica efectiva aunque no cambie.
    return Measure(number=number, events=events, time_signature=signature)


def _events(score: ScoreIR) -> list[tuple[int, tuple[tuple[object, ...], ...]]]:
    return [
        (
            measure.number,
            tuple(
                (e.kind, e.voice, e.pitch, e.duration_beats, e.tie, e.is_chord)
                for e in measure.events
            ),
        )
        for part in score.parts
        for staff in part.staves
        for measure in staff.measures
    ]


def _xml_measures(xml_text: str) -> list[ET.Element]:
    root = ET.fromstring(xml_text.encode("utf-8"))
    return root.findall("./part/measure")


def test_time_signature_only_on_first_measure_and_on_changes() -> None:
    two_four = TimeSignature(beats=2, beat_type=4)
    score = _score(
        _first(1, _note("C4", "3")),
        _next(2, _note("D4", "3")),
        _next(3, _note("E4", "2"), signature=two_four),
        _next(4, _note("F4", "2"), signature=two_four),
    )

    measures = _xml_measures(score_ir_to_musicxml(score))

    with_time = [m.get("number") for m in measures if m.find("./attributes/time") is not None]
    assert with_time == ["1", "3"]


def test_time_signature_survives_roundtrip_on_every_measure() -> None:
    score = _score(_first(1, _note("C4", "3")), _next(2, _note("D4", "3")))

    reloaded = musicxml_to_score_ir(score_ir_to_musicxml(score))

    signatures = [m.time_signature for m in reloaded.parts[0].staves[0].measures]
    assert signatures == [THREE_FOUR, THREE_FOUR]


def test_no_placeholder_title_or_composer() -> None:
    xml_text = score_ir_to_musicxml(_score(_first(1, _note("C4", "3"))))

    root = ET.fromstring(xml_text.encode("utf-8"))
    assert "Music21" not in xml_text
    assert root.find("movement-title") is None
    assert root.find("./identification/creator") is None


def test_overfull_measure_is_exported_as_transcribed() -> None:
    # Compás real de HOMR (spike de #152): 3/4 con 15/4 negras; la nota de 1/2 que cruza la
    # barra no debe partirse ni pasar al compás siguiente.
    first = _first(
        1,
        _rest("1"),
        _note("G4", "1"),
        _note("C5", "1/4"),
        _note("B4", "1/2"),
        _note("C5", "1/2"),
        _note("D5", "1/2"),
    )
    second = _next(2, _note("Eb5", "1/2"), _note("D5", "1/4"), _note("C5", "1/4"))
    score = _score(first, second)

    xml_text = score_ir_to_musicxml(score)
    measures = _xml_measures(xml_text)

    assert [len(m.findall("note")) for m in measures] == [6, 3]
    assert "<forward>" not in xml_text
    assert "<tie " not in xml_text
    assert _events(musicxml_to_score_ir(xml_text)) == _events(score)


def test_incomplete_measure_is_not_padded_with_hidden_rests() -> None:
    score = _score(_first(1, _note("C5", "2")))

    xml_text = score_ir_to_musicxml(score)

    assert 'print-object="no"' not in xml_text
    assert _events(musicxml_to_score_ir(xml_text)) == _events(score)


def test_duration_without_single_figure_becomes_tied_notes_in_same_measure() -> None:
    # 5/4 de negra no tiene figura propia: MusicXML la escribe como negra ligada a semicorchea,
    # dentro del mismo compás. Al reimportar son dos eventos ligados.
    score = _score(_first(1, _note("C4", "5/4"), _note("D4", "7/4")))

    xml_text = score_ir_to_musicxml(score)
    reloaded = musicxml_to_score_ir(xml_text)

    assert len(_xml_measures(xml_text)) == 1
    events = reloaded.parts[0].staves[0].measures[0].events
    assert [(e.pitch, e.duration_beats, e.tie) for e in events] == [
        ("C4", Fraction(1), Tie.START),
        ("C4", Fraction(1, 4), Tie.STOP),
        ("D4", Fraction(7, 4), None),
    ]


def test_roundtrip_preserves_chords_ties_and_voices() -> None:
    score = _score(
        _first(
            1,
            _note("C4", "1"),
            _note("E4", "1", is_chord=True),
            _note("G4", "1", is_chord=True),
            _note("D4", "1"),
            _note("F4", "1", tie=Tie.START),
        ),
        _next(
            2,
            _note("F4", "1", tie=Tie.STOP),
            _rest("2"),
            _note("A3", "3", voice=1),
        ),
    )

    xml_text = score_ir_to_musicxml(score)

    assert _events(musicxml_to_score_ir(xml_text)) == _events(score)


def test_beams_and_key_accidentals_are_kept() -> None:
    score = _score(
        Measure(
            number=1,
            events=(
                _note("F#4", "1/4"),
                _note("E4", "1/4"),
                _note("D4", "1/4"),
                _note("C4", "1/4"),
                _note("D4", "2"),
            ),
            time_signature=THREE_FOUR,
            clef=Clef(sign="G", line=2),
            key_signature=KeySignature(fifths=2),
        )
    )

    notes = _xml_measures(score_ir_to_musicxml(score))[0].findall("note")

    assert notes[0].find("beam") is not None
    # F# está en la armadura (re mayor): sin alteración escrita; C natural sí la lleva.
    assert notes[0].find("accidental") is None
    accidental = notes[3].find("accidental")
    assert accidental is not None and accidental.text == "natural"
