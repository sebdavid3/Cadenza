"""Fidelidad del MusicXML exportado al `ScoreIR` materializado (#152).

El exportador alimenta la vista de la partitura (OSMD) y la descarga del usuario: cada compás
debe salir con sus eventos tal cual, la métrica solo donde cambia y sin metadatos de relleno.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction

import pytest
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
from cadenza.interchange import (
    InterchangeError,
    musicxml_to_score_ir,
    score_ir_to_midi,
    score_ir_to_musicxml,
)

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


def _beams(measure: ET.Element) -> list[str | None]:
    beams = []
    for note_element in measure.findall("note"):
        beam = note_element.find("beam")
        beams.append(None if beam is None else beam.text)
    return beams


def test_incomplete_measure_after_the_first_is_beamed_from_the_downbeat() -> None:
    # Un incipit truncado acaba a mitad de compás: las barras empiezan en la parte 1, no como
    # en una anacrusa (hallazgo de la revisión de #152).
    six_eight = TimeSignature(beats=6, beat_type=8)
    eighths = [_note(pitch, "1/2") for pitch in ("D5", "C5", "B4", "A4", "G4", "F4")]
    score = _score(
        _first(1, *eighths, signature=six_eight),
        _next(2, *eighths[:4], signature=six_eight),
    )

    measures = _xml_measures(score_ir_to_musicxml(score))

    assert _beams(measures[0]) == ["begin", "continue", "end", "begin", "continue", "end"]
    assert _beams(measures[1]) == ["begin", "continue", "end", None]


def test_incomplete_first_measure_is_beamed_as_a_pickup() -> None:
    score = _score(_first(1, _note("G4", "1/2"), _note("A4", "1/2"), _note("B4", "1/2")))

    measures = _xml_measures(score_ir_to_musicxml(score))

    # Anacrusa de tres corcheas en 3/4: se agrupan las que caen en la misma parte.
    assert _beams(measures[0]) == [None, "begin", "end"]


def test_two_voices_in_incomplete_and_overfull_measures_roundtrip() -> None:
    score = _score(
        _first(1, _note("C5", "3"), _note("E4", "3", voice=1)),
        _next(2, _note("D5", "2"), _note("F4", "1/2", voice=1)),
        _next(3, _note("E5", "3"), _note("C5", "1"), _note("G4", "3", voice=1)),
    )

    xml_text = score_ir_to_musicxml(score)

    assert 'print-object="no"' not in xml_text
    assert _events(musicxml_to_score_ir(xml_text)) == _events(score)


def test_two_staves_with_incomplete_and_overfull_measures_roundtrip() -> None:
    upper = (
        _first(1, _note("C5", "3")),
        _next(2, _note("D5", "1")),
        _next(3, _note("E5", "3"), _note("F5", "1")),
    )
    lower = (
        Measure(
            number=1,
            events=(_note("C3", "3"),),
            time_signature=THREE_FOUR,
            clef=Clef(sign="F", line=4),
        ),
        _next(2, _note("D3", "3")),
        _next(3, _note("E3", "3")),
    )
    score = ScoreIR(
        parts=(
            Part(
                id="Piano",
                staves=(Staff(id="upper", measures=upper), Staff(id="lower", measures=lower)),
            ),
        )
    )

    xml_text = score_ir_to_musicxml(score)

    assert 'print-object="no"' not in xml_text
    assert xml_text.count("<time>") == 1
    assert _events(musicxml_to_score_ir(xml_text)) == _events(score)


def test_score_without_parts_is_rejected() -> None:
    with pytest.raises(InterchangeError):
        score_ir_to_musicxml(ScoreIR(parts=()))


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


def _durations(measure: ET.Element) -> list[int | None]:
    """Duración MusicXML de cada nota del compás: None en una nota de adorno, que no la lleva."""
    durations = []
    for note_element in measure.findall("note"):
        duration = note_element.find("duration")
        durations.append(None if duration is None or duration.text is None else int(duration.text))
    return durations


def test_zero_or_null_duration_note_is_a_grace_note_that_takes_no_time() -> None:
    # HOMR da duración 0 a las notas de adorno. Antes salían como negras que el ScoreIR no suma:
    # music21 cambia la duración cero por una negra, y el exportador hacía lo mismo con la nula
    # (D60, #199).
    null_note = Event(kind=EventKind.NOTE, voice=0, pitch="D5", duration_beats=None)
    score = _score(
        _first(1, _note("G#4", "0"), _note("A4", "2"), _note("B4", "1")),
        _next(2, null_note, _note("E5", "3")),
    )

    xml_text = score_ir_to_musicxml(score)

    first, second = _xml_measures(xml_text)
    assert [note.find("grace") is not None for note in first.findall("note")] == [
        True,
        False,
        False,
    ]
    assert [note.find("grace") is not None for note in second.findall("note")] == [True, False]
    # Las notas de adorno no llevan duración: cada compás suma sus tres negras.
    divisions = int(first.findtext("attributes/divisions") or 0)
    assert _durations(first) == [None, 2 * divisions, divisions]
    assert _durations(second) == [None, 3 * divisions]

    reloaded = musicxml_to_score_ir(xml_text).parts[0].staves[0].measures
    assert [(e.pitch, e.duration_beats) for e in reloaded[0].events] == [
        ("G#4", Fraction(0)),
        ("A4", Fraction(2)),
        ("B4", Fraction(1)),
    ]
    assert [(e.pitch, e.duration_beats) for e in reloaded[1].events] == [
        ("D5", Fraction(0)),
        ("E5", Fraction(3)),
    ]


def test_zero_duration_chord_is_a_grace_chord() -> None:
    score = _score(
        _first(1, _note("C5", "0"), _note("E5", "0", is_chord=True), _note("D5", "3")),
    )

    xml_text = score_ir_to_musicxml(score)

    (measure,) = _xml_measures(xml_text)
    assert [note.find("grace") is not None for note in measure.findall("note")] == [
        True,
        True,
        False,
    ]
    events = musicxml_to_score_ir(xml_text).parts[0].staves[0].measures[0].events
    assert [(e.pitch, e.duration_beats, e.is_chord) for e in events] == [
        ("C5", Fraction(0), False),
        ("E5", Fraction(0), True),
        ("D5", Fraction(3), False),
    ]


def test_grace_note_at_the_end_of_a_measure_stays_in_it() -> None:
    score = _score(_first(1, _note("F5", "3"), _note("G5", "0")), _next(2, _note("A5", "3")))

    xml_text = score_ir_to_musicxml(score)

    first, second = _xml_measures(xml_text)
    assert [note.findtext("pitch/step") for note in first.findall("note")] == ["F", "G"]
    assert first.findall("note")[1].find("grace") is not None
    assert [note.findtext("pitch/step") for note in second.findall("note")] == ["A"]


def test_zero_duration_rest_is_still_written_as_a_quarter_rest() -> None:
    # MusicXML no tiene silencios de adorno: un silencio de duración cero sigue saliendo como
    # silencio de negra, como hasta ahora.
    score = _score(_first(1, _rest("0"), _note("C4", "3")))

    xml_text = score_ir_to_musicxml(score)

    (measure,) = _xml_measures(xml_text)
    divisions = int(measure.findtext("attributes/divisions") or 0)
    assert measure.findall("note")[0].find("rest") is not None
    assert _durations(measure)[0] == divisions


def test_midi_export_accepts_grace_notes() -> None:
    score = _score(_first(1, _note("G#4", "0"), _note("A4", "3")))

    assert score_ir_to_midi(score).startswith(b"MThd")
