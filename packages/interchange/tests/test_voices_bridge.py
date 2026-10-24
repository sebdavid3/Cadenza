"""Varias voces en la ida y vuelta MusicXML ↔ `ScoreIR` (ADR-0032, #218).

Cada nota conserva dónde empieza dentro de su voz: una voz que entra a mitad del compás
(`<forward>`), un hueco entre dos notas de una voz y un silencio invisible (`print-object="no"`)
son silencios invisibles del `ScoreIR`. Las fixtures:

- `forward_second_voice.musicxml`: el caso mínimo del fallo, una segunda voz que entra a mitad
  del compás;
- `voices_piano.musicxml`: piano con dos voces en cada pentagrama (numeradas como HOMR), voces
  que entran, callan y salen a mitad del compás, un acorde y una ligadura de prolongación en la
  segunda voz y marcas de notación (ADR-0031) en las dos voces;
- `voices_melody.musicxml`: una sola voz con un hueco entre dos notas y un silencio invisible.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

import pytest
from cadenza.domain import (
    Event,
    EventKind,
    Measure,
    Part,
    ScoreIR,
    Staff,
    TimeSignature,
    compute_timing_map,
)
from cadenza.interchange import (
    music21_stream_to_score_ir,
    musicxml_to_score_ir,
    read_score,
    score_ir_to_midi,
    score_ir_to_musicxml,
)
from music21 import converter, stream

FIXTURES = Path(__file__).parent / "fixtures"
FORWARD = FIXTURES / "forward_second_voice.musicxml"
PIANO = FIXTURES / "voices_piano.musicxml"
MELODY = FIXTURES / "voices_melody.musicxml"
# Compás de 4/4: voz 1, un Mi5 redonda; voz 2, `<forward>` de dos negras y después Do5 y Si4.
FORWARD_IN_SECOND_VOICE = FORWARD.read_text(encoding="utf-8")

# Lugar de una nota: pentagrama, compás, voz, instante en el compás y altura.
Place = tuple[int, int, int, Fraction, str | None]


def _read(path: Path) -> ScoreIR:
    return musicxml_to_score_ir(path.read_text(encoding="utf-8"))


def _sounding_onsets(score: ScoreIR) -> dict[str, Fraction]:
    """Instante de cada nota que suena, según el mapa de tiempos, por su altura."""

    events = {
        (timing.anchor.voice, timing.anchor.event_index): timing
        for timing in compute_timing_map(score).events
    }
    onsets: dict[str, Fraction] = {}
    for measure in score.parts[0].staves[0].measures:
        counters: dict[int, int] = {}
        for event in measure.events:
            index = counters.get(event.voice, 0)
            counters[event.voice] = index + 1
            if event.pitch is not None:
                onsets[event.pitch] = events[(event.voice, index)].offset_beats
    return onsets


def _music21_onsets(xml: str) -> dict[str, Fraction]:
    """Instante de cada nota del MusicXML dentro de su compás, según music21."""

    parsed = converter.parseData(xml, format="musicxml")
    measure = parsed.parts[0].getElementsByClass(stream.Measure)[0]
    return {
        note.nameWithOctave: Fraction(note.getOffsetInHierarchy(measure))
        for note in measure.recurse().notes
    }


def _drawn(xml: str) -> list[tuple[int, int, int, Fraction, str, Fraction]]:
    """Lo que se dibuja de un MusicXML, según music21: cada nota, acorde o silencio visible con
    su pentagrama, su compás, el orden de su voz en el compás, su instante y su duración."""

    found = []
    parsed = converter.parseData(xml, format="musicxml")
    for staff_index, staff in enumerate(parsed.parts):
        for measure in staff.getElementsByClass(stream.Measure):
            voices = sorted(measure.voices, key=lambda voice: int(voice.id)) or [measure]
            for voice_rank, voice in enumerate(voices):
                for element in voice.notesAndRests:
                    if element.style.hideObjectOnPrint:
                        continue
                    label = (
                        "R"
                        if element.isRest
                        else "+".join(p.nameWithOctave for p in element.pitches)
                    )
                    found.append(
                        (
                            staff_index,
                            measure.number,
                            voice_rank,
                            Fraction(element.offset),
                            label,
                            Fraction(element.quarterLength),
                        )
                    )
    return sorted(found)


def _voice(score: ScoreIR, staff: int, number: int, voice: int) -> list[tuple[object, ...]]:
    """Eventos de una voz de un compás: clase, altura, duración, acorde, ligadura e invisible."""

    measure = next(m for m in score.parts[0].staves[staff].measures if m.number == number)
    return [
        (
            event.kind.value,
            event.pitch,
            event.duration_beats,
            event.is_chord,
            None if event.tie is None else event.tie.value,
            event.hidden,
        )
        for event in measure.events
        if event.voice == voice
    ]


def test_forward_keeps_the_onset_of_a_voice_that_enters_mid_measure() -> None:
    score = musicxml_to_score_ir(FORWARD_IN_SECOND_VOICE)

    assert _sounding_onsets(score) == {"E5": 0, "C5": 2, "B4": 3}

    exported = score_ir_to_musicxml(score)
    assert _music21_onsets(exported) == {"E5": 0, "C5": 2, "B4": 3}
    assert _sounding_onsets(musicxml_to_score_ir(exported)) == {"E5": 0, "C5": 2, "B4": 3}


@pytest.mark.parametrize("path", [FORWARD, PIANO, MELODY], ids=lambda path: path.stem)
def test_the_round_trip_keeps_where_every_note_starts(path: Path) -> None:
    original = path.read_text(encoding="utf-8")
    exported = score_ir_to_musicxml(musicxml_to_score_ir(original))
    assert _drawn(exported) == _drawn(original)


@pytest.mark.parametrize("path", [FORWARD, PIANO, MELODY], ids=lambda path: path.stem)
def test_the_round_trip_gives_back_the_same_score_ir(path: Path) -> None:
    score = _read(path)
    assert musicxml_to_score_ir(score_ir_to_musicxml(score)) == score


def test_gaps_and_invisible_rests_become_hidden_rests() -> None:
    score = _read(PIANO)
    one, two = Fraction(1), Fraction(2)
    # Compás 1: la voz 2 entra a mitad del compás; la voz 6, tras una negra, y calla otra.
    assert _voice(score, 0, 1, 1) == [
        ("rest", None, two, False, None, True),
        ("note", "G4", one, False, None, False),
        ("note", "F4", one, False, None, False),
    ]
    assert _voice(score, 1, 1, 1) == [
        ("rest", None, one, False, None, True),
        ("note", "E3", one, False, None, False),
        ("rest", None, one, False, None, True),
        ("note", "G3", one, False, None, False),
    ]
    # Compás 2: silencio invisible y un acorde ligado al compás siguiente.
    three = Fraction(3)
    assert _voice(score, 0, 2, 1) == [
        ("rest", None, one, False, None, True),
        ("note", "E4", three, False, None, False),
        ("note", "G4", three, True, "start", False),
    ]
    # Compás 3: acaba la ligadura de prolongación, calla dos negras y vuelve a entrar; abajo, la
    # voz 6 entra tras una negra y sale: lo que falta hasta el final no es un evento.
    assert _voice(score, 0, 3, 1) == [
        ("note", "G4", one, False, "stop", False),
        ("rest", None, two, False, None, True),
        ("note", "A4", one, False, None, False),
    ]
    assert _voice(score, 1, 3, 1) == [
        ("rest", None, one, False, None, True),
        ("note", "E3", one, False, None, False),
    ]

    melody = _read(MELODY)
    assert _voice(melody, 0, 1, 0) == [
        ("note", "A4", one, False, None, False),
        ("rest", None, one, False, None, True),
        ("note", "B4", one, False, None, False),
    ]
    assert _voice(melody, 0, 2, 0) == [
        ("rest", None, one, False, None, True),
        ("note", "C5", two, False, None, False),
    ]


def test_a_multirest_of_mei_is_a_rest_that_is_seen() -> None:
    """converter21 cambia un `<multiRest>` por un silencio de compás entero oculto, pero en la
    partitura se ve: solo en MusicXML un silencio oculto es invisible. Así se leían, y se siguen
    leyendo, 32 de las 100 verdades de PrIMuS de `data/`."""

    pytest.importorskip("converter21")
    score = read_score(FIXTURES / "multirest.mei")
    assert [
        [(e.kind.value, e.pitch, e.duration_beats, e.hidden) for e in m.events]
        for m in score.parts[0].staves[0].measures
    ] == [
        [("rest", None, Fraction(3), False)],
        [
            ("note", "G4", Fraction(1), False),
            ("rest", None, Fraction(1), False),
            ("note", "C5", Fraction(1), False),
        ],
    ]


def test_a_rest_hidden_by_music21_is_seen_if_the_format_is_unknown() -> None:
    parsed = converter.parseData(MELODY.read_text(encoding="utf-8"), format="musicxml")
    score = music21_stream_to_score_ir(parsed)
    second = score.parts[0].staves[0].measures[1].events
    assert [(e.kind.value, e.hidden) for e in second] == [("rest", False), ("note", False)]
    # Los huecos de una voz sí son silencios invisibles: no dependen del formato.
    first = score.parts[0].staves[0].measures[0].events
    assert [(e.kind.value, e.hidden) for e in first] == [
        ("note", False),
        ("rest", True),
        ("note", False),
    ]


def test_without_gaps_the_voices_have_no_hidden_rests() -> None:
    score = _read(FIXTURES / "marks_piano.musicxml")
    assert not any(
        event.hidden
        for staff in score.parts[0].staves
        for measure in staff.measures
        for event in measure.events
    )


def test_export_writes_each_hidden_rest_as_an_invisible_rest() -> None:
    score = _read(PIANO)
    root = ET.fromstring(score_ir_to_musicxml(score))
    hidden = [note for note in root.iter("note") if note.get("print-object") == "no"]
    expected = sum(
        event.hidden
        for staff in score.parts[0].staves
        for measure in staff.measures
        for event in measure.events
    )
    assert expected == 6
    assert len(hidden) == expected
    assert all(note.find("rest") is not None for note in hidden)
    # Ningún hueco sale como `<forward>`: los que quedan sitúan los reguladores (ADR-0031).
    for measure in root.iter("measure"):
        children = list(measure)
        for position, child in enumerate(children[:-1]):
            if child.tag == "forward":
                assert children[position + 1].tag == "direction"


def _voices_by_measure(xml: str) -> dict[str, set[tuple[str | None, str | None]]]:
    root = ET.fromstring(xml)
    return {
        str(measure.get("number")): {
            (note.findtext("staff"), note.findtext("voice")) for note in measure.iter("note")
        }
        for measure in root.iter("measure")
    }


def test_export_numbers_the_voices_of_each_staff_apart() -> None:
    """Como HOMR y MuseScore: del 1 en adelante arriba y del 5 en adelante abajo, en todos los
    compases. music21 repetía los números del pentagrama superior en el inferior."""

    assert _voices_by_measure(score_ir_to_musicxml(_read(PIANO))) == {
        "1": {("1", "1"), ("1", "2"), ("2", "5"), ("2", "6")},
        "2": {("1", "1"), ("1", "2"), ("2", "5")},
        "3": {("1", "1"), ("1", "2"), ("2", "5"), ("2", "6")},
    }


def test_export_points_the_stems_of_each_voice_apart() -> None:
    """Con varias voces con notas en un pentagrama, la más aguda hacia arriba y las demás hacia
    abajo; con una sola, la plica la decide quien dibuja. En el pentagrama inferior del compás
    1, la voz 6 (Mi3 y Sol3) es más aguda que la 5 (un Do3 redonda, sin plica)."""

    root = ET.fromstring(score_ir_to_musicxml(_read(PIANO)))
    stems: dict[tuple[str, str | None, str | None], set[str | None]] = {}
    for measure in root.iter("measure"):
        for note in measure.iter("note"):
            # La plica de un acorde va en su primera nota; una redonda no tiene.
            if (
                note.find("rest") is not None
                or note.find("chord") is not None
                or note.findtext("type") == "whole"
            ):
                continue
            key = (str(measure.get("number")), note.findtext("staff"), note.findtext("voice"))
            stems.setdefault(key, set()).add(note.findtext("stem"))
    assert stems == {
        ("1", "1", "1"): {"up"},
        ("1", "1", "2"): {"down"},
        ("1", "2", "6"): {"up"},
        ("2", "1", "1"): {"up"},
        ("2", "1", "2"): {"down"},
        ("2", "2", "5"): {None},
        ("3", "1", "2"): {"down"},
        ("3", "2", "6"): {"up"},
    }


def test_the_stems_follow_the_pitch_of_the_voices_not_their_number() -> None:
    """HOMR no numera las voces por su altura: en el piano de prueba da la voz 1 a las negras
    graves y la 2 a las blancas agudas. La plica de las agudas va hacia arriba igualmente."""

    def staff_voice(voice: int, pitches: list[str], beats: Fraction) -> tuple[Event, ...]:
        return tuple(
            Event(kind=EventKind.NOTE, voice=voice, pitch=p, duration_beats=beats) for p in pitches
        )

    measure = Measure(
        number=1,
        events=(
            *staff_voice(0, ["C5", "B4", "A4", "G4"], Fraction(1)),
            *staff_voice(1, ["E5", "D5"], Fraction(2)),
        ),
        time_signature=TimeSignature(4, 4),
    )
    score = ScoreIR(parts=(Part(id="p", staves=(Staff(id="s", measures=(measure,)),)),))
    root = ET.fromstring(score_ir_to_musicxml(score))
    stems = {
        (note.findtext("pitch/step") or "")
        + (note.findtext("pitch/octave") or ""): (note.findtext("stem"))
        for note in root.iter("note")
    }
    assert stems == {
        "C5": "down",
        "B4": "down",
        "A4": "down",
        "G4": "down",
        "E5": "up",
        "D5": "up",
    }


def _marks(score: ScoreIR) -> dict[str, object]:
    """Las marcas de la partitura por el lugar de su nota o su posición, no por su índice."""

    timings = {
        (t.anchor.staff, t.anchor.measure, t.anchor.voice, t.anchor.event_index): t
        for t in compute_timing_map(score).events
    }
    notes: dict[Place, tuple[tuple[str, ...], bool]] = {}
    starts: dict[int, Place] = {}
    stops: dict[int, Place] = {}
    positioned: dict[tuple[int, int], tuple[list[str], list[str]]] = {}
    for staff_index, staff in enumerate(score.parts[0].staves):
        for measure in staff.measures:
            if measure.dynamics or measure.wedges:
                positioned[(staff_index, measure.number)] = (
                    [f"{d.mark.value}@{d.offset_beats}" for d in measure.dynamics],
                    [f"{w.type.value}@{w.offset_beats}" for w in measure.wedges],
                )
            counters: dict[int, int] = {}
            for event in measure.events:
                index = counters.get(event.voice, 0)
                counters[event.voice] = index + 1
                onset = timings[(staff_index, measure.number, event.voice, index)]
                place = (
                    staff_index,
                    measure.number,
                    event.voice,
                    onset.measure_offset_beats,
                    event.pitch,
                )
                if event.articulations or event.fermata:
                    notes[place] = (tuple(a.value for a in event.articulations), event.fermata)
                for slur in event.slurs:
                    (starts if slur.type.value == "start" else stops)[slur.number] = place
    return {
        "notes": notes,
        "positioned": positioned,
        "slurs": sorted((starts[n], stops[n]) for n in starts),
    }


def test_marks_stay_with_their_notes_and_positions_with_several_voices() -> None:
    score = _read(PIANO)
    expected = {
        "notes": {
            (0, 1, 0, Fraction(0), "C5"): (("staccato",), False),
            (0, 1, 1, Fraction(2), "G4"): (("accent",), False),
            (0, 1, 1, Fraction(3), "F4"): ((), True),
            (0, 3, 0, Fraction(0), "E5"): ((), True),
        },
        "positioned": {
            (0, 1): (["p@0", "mf@2"], []),
            (1, 1): ([], ["crescendo@1", "stop@3"]),
        },
        "slurs": [
            ((0, 1, 0, Fraction(0), "C5"), (0, 1, 0, Fraction(2), "E5")),
            ((0, 1, 1, Fraction(2), "G4"), (0, 1, 1, Fraction(3), "F4")),
        ],
    }
    assert _marks(score) == expected
    assert _marks(musicxml_to_score_ir(score_ir_to_musicxml(score))) == expected


def test_midi_plays_each_voice_at_its_onset() -> None:
    midi = converter.parseData(score_ir_to_midi(_read(FORWARD)), format="midi")
    onsets = {
        note.nameWithOctave: Fraction(note.getOffsetInHierarchy(midi))
        for note in midi.recurse().notes
    }
    assert onsets == {"E5": 0, "C5": 2, "B4": 3}


def test_the_hidden_rest_is_a_rest_of_the_timing_map_and_not_a_sound() -> None:
    timing = compute_timing_map(_read(FORWARD))
    kinds = [(t.anchor.voice, t.kind, t.offset_beats) for t in timing.events]
    assert (1, EventKind.REST, Fraction(0)) in kinds
    assert [t.offset_beats for t in timing.sounding_events()] == [0, 2, 3]
