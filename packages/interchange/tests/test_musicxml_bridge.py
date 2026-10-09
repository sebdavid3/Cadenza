"""Pruebas del puente canónico MusicXML → ScoreIR (music21)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

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
    build_anchor_index,
)
from cadenza.interchange import musicxml_to_score_ir, read_score, score_ir_to_musicxml

FIXTURE = Path(__file__).parent / "fixtures" / "simple.musicxml"
PIANO_FIXTURE = Path(__file__).parent / "fixtures" / "piano.musicxml"


def _score() -> ScoreIR:
    return musicxml_to_score_ir(FIXTURE.read_text(encoding="utf-8"))


def test_parts_and_staves() -> None:
    score = _score()
    assert len(score.parts) == 1
    assert score.parts[0].id == "part-0"
    assert score.parts[0].staves[0].id == "part-0-staff-0"


def test_measures_durations_and_pitches() -> None:
    measures = _score().parts[0].staves[0].measures
    assert [measure.number for measure in measures] == [1, 2]

    first_events = measures[0].events
    assert [event.kind for event in first_events] == [
        EventKind.NOTE,
        EventKind.NOTE,
        EventKind.REST,
    ]
    assert first_events[0].pitch == "C4"
    assert first_events[0].duration_beats == Fraction(1)
    assert first_events[1].pitch == "D4"
    assert first_events[2].pitch is None
    assert first_events[2].duration_beats == Fraction(2)


def test_clef_and_key_signature_are_extracted() -> None:
    measures = _score().parts[0].staves[0].measures
    # Medida 1: Sol en 2ª, sin alteraciones
    assert measures[0].clef == Clef(sign="G", line=2, octave_change=0)
    assert measures[0].key_signature == KeySignature(fifths=0)

    # Medida 2: no redefine clave ni armadura (se mantiene la del anterior)
    assert measures[1].clef is None
    assert measures[1].key_signature is None


def test_time_signature_is_mapped_and_inherited() -> None:
    measures = _score().parts[0].staves[0].measures
    assert measures[0].time_signature == TimeSignature(4, 4)
    assert measures[1].time_signature == TimeSignature(4, 4)


def test_anchor_index_is_deterministic_and_complete() -> None:
    score = _score()
    index = build_anchor_index(score)
    assert len(index) == 4
    assert index == build_anchor_index(score)


def test_read_score_matches_text_parsing() -> None:
    assert read_score(FIXTURE) == _score()


def test_musicxml_roundtrip_preserves_supported_subset() -> None:
    original = _score()
    reparsed = musicxml_to_score_ir(score_ir_to_musicxml(original))

    original_measures = original.parts[0].staves[0].measures
    reparsed_measures = reparsed.parts[0].staves[0].measures
    assert [m.number for m in reparsed_measures] == [m.number for m in original_measures]
    for expected, actual in zip(original_measures, reparsed_measures, strict=True):
        assert actual.clef == expected.clef
        assert actual.key_signature == expected.key_signature
        assert actual.time_signature == expected.time_signature
        assert [e.pitch for e in actual.events] == [e.pitch for e in expected.events]
        assert [e.duration_beats for e in actual.events] == [
            e.duration_beats for e in expected.events
        ]
        assert [e.tie for e in actual.events] == [e.tie for e in expected.events]


def test_musicxml_roundtrip_with_clef_key_changes_and_ties() -> None:
    """Test de roundtrip MusicXML ↔ ScoreIR con claves, armaduras y ligaduras (ADR-0010)."""
    measure_1 = Measure(
        number=1,
        events=(
            Event(kind=EventKind.NOTE, voice=0, pitch="F3", duration_beats=Fraction(1)),
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="Ab3",
                duration_beats=Fraction(2),
                tie=Tie.START,
            ),
        ),
        time_signature=TimeSignature(3, 4),
        clef=Clef.bass(),
        key_signature=KeySignature(fifths=-3),  # 3 bemoles (Mib mayor / Do menor)
    )
    measure_2 = Measure(
        number=2,
        events=(
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="Ab3",
                duration_beats=Fraction(1),
                tie=Tie.STOP,
            ),
            Event(kind=EventKind.NOTE, voice=0, pitch="C4", duration_beats=Fraction(2)),
        ),
        time_signature=TimeSignature(3, 4),
        clef=None,  # se mantiene bass
        key_signature=None,  # se mantiene 3 bemoles
    )
    measure_3 = Measure(
        number=3,
        events=(
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="A4",
                duration_beats=Fraction(3),
                tie=Tie.START,
            ),
        ),
        time_signature=TimeSignature(3, 4),
        clef=Clef.treble(),  # cambio de clave a sol
        key_signature=KeySignature(fifths=2),  # cambio de armadura a 2 sostenidos
    )
    measure_4 = Measure(
        number=4,
        events=(
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="A4",
                duration_beats=Fraction(3),
                tie=Tie.STOP,
            ),
        ),
        time_signature=TimeSignature(3, 4),
        clef=None,
        key_signature=None,
    )

    staff = Staff(id="part-0-staff-0", measures=(measure_1, measure_2, measure_3, measure_4))
    original = ScoreIR(parts=(Part(id="part-0", staves=(staff,)),))

    xml_text = score_ir_to_musicxml(original)
    reparsed = musicxml_to_score_ir(xml_text)

    orig_measures = original.parts[0].staves[0].measures
    repar_measures = reparsed.parts[0].staves[0].measures
    assert len(repar_measures) == len(orig_measures) == 4

    for expected, actual in zip(orig_measures, repar_measures, strict=True):
        assert actual.number == expected.number
        assert actual.clef == expected.clef
        assert actual.key_signature == expected.key_signature
        assert actual.time_signature == expected.time_signature
        assert [e.kind for e in actual.events] == [e.kind for e in expected.events]
        assert [e.pitch for e in actual.events] == [e.pitch for e in expected.events]
        assert [e.duration_beats for e in actual.events] == [
            e.duration_beats for e in expected.events
        ]
        assert [e.tie for e in actual.events] == [e.tie for e in expected.events]
        assert [e.is_chord for e in actual.events] == [e.is_chord for e in expected.events]


def test_piano_fixture_loads_two_staves_and_chords() -> None:
    score = read_score(PIANO_FIXTURE)
    assert len(score.parts) == 1
    part = score.parts[0]
    assert len(part.staves) == 2
    assert part.staves[0].id == "part-0-staff-0"
    assert part.staves[1].id == "part-0-staff-1"

    # Staff 0: clave de sol, compás 1 con acorde
    staff_0 = part.staves[0]
    assert staff_0.measures[0].clef == Clef(sign="G", line=2, octave_change=0)
    m1_events = staff_0.measures[0].events
    assert len(m1_events) == 4
    assert [e.pitch for e in m1_events] == ["C4", "D4", "E4", "G4"]
    assert [e.is_chord for e in m1_events] == [False, False, False, True]

    # Staff 1: clave de fa, compás 1 con redonda
    staff_1 = part.staves[1]
    assert staff_1.measures[0].clef == Clef(sign="F", line=4, octave_change=0)
    assert len(staff_1.measures[0].events) == 1
    assert staff_1.measures[0].events[0].pitch == "C3"
    assert staff_1.measures[0].events[0].duration_beats == Fraction(4)

    # Staff 0, Compás 2: dos voces polifónicas
    m2_events = staff_0.measures[1].events
    voices = {e.voice for e in m2_events}
    assert len(voices) == 2


def test_piano_musicxml_roundtrip_preserves_staves_voices_and_chords() -> None:
    original = read_score(PIANO_FIXTURE)
    xml_exported = score_ir_to_musicxml(original)
    reparsed = musicxml_to_score_ir(xml_exported)

    assert len(reparsed.parts) == len(original.parts) == 1
    orig_staves = original.parts[0].staves
    repar_staves = reparsed.parts[0].staves
    assert len(repar_staves) == len(orig_staves) == 2

    for orig_staff, repar_staff in zip(orig_staves, repar_staves, strict=True):
        assert orig_staff.id == repar_staff.id
        for orig_m, repar_m in zip(orig_staff.measures, repar_staff.measures, strict=True):
            assert repar_m.number == orig_m.number
            assert repar_m.clef == orig_m.clef
            assert repar_m.key_signature == orig_m.key_signature
            assert repar_m.time_signature == orig_m.time_signature
            assert len(repar_m.events) == len(orig_m.events)
            for orig_e, repar_e in zip(orig_m.events, repar_m.events, strict=True):
                assert repar_e.kind == orig_e.kind
                assert repar_e.pitch == orig_e.pitch
                assert repar_e.duration_beats == orig_e.duration_beats
                assert repar_e.voice == orig_e.voice
                assert repar_e.is_chord == orig_e.is_chord
