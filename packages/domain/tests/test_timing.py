"""Tests unitarios del mapa tiempo→ancla para la reproducción sincronizada (#42, D12)."""

from fractions import Fraction

from cadenza.domain import (
    Event,
    EventKind,
    EventTiming,
    Measure,
    Part,
    ScoreIR,
    Staff,
    TimeSignature,
    TimingMap,
    compute_timing_map,
)


def test_empty_score_timing_map() -> None:
    score = ScoreIR(parts=())
    timing = compute_timing_map(score)
    assert timing.events == ()
    assert timing.total_beats == Fraction(0)
    assert timing.measure_offsets == {}


def test_single_voice_monophonic_timing() -> None:
    # Compás 1 (4/4): 4 negras (duración 1 c/u)
    # Compás 2 (4/4): 2 blancas (duración 2 c/u)
    m1 = Measure(
        number=1,
        time_signature=TimeSignature(beats=4, beat_type=4),
        events=(
            Event(kind=EventKind.NOTE, voice=0, pitch="C4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=0, pitch="D4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=0, pitch="E4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=0, pitch="F4", duration_beats=Fraction(1)),
        ),
    )
    m2 = Measure(
        number=2,
        events=(
            Event(kind=EventKind.NOTE, voice=0, pitch="G4", duration_beats=Fraction(2)),
            Event(kind=EventKind.NOTE, voice=0, pitch="C5", duration_beats=Fraction(2)),
        ),
    )
    score = ScoreIR(parts=(Part(id="P1", staves=(Staff(id="P1-1", measures=(m1, m2)),)),))

    timing = compute_timing_map(score)
    assert timing.total_beats == Fraction(8)
    assert timing.measure_offsets == {1: Fraction(0), 2: Fraction(4)}
    assert len(timing.events) == 6

    # Revisar compás 1
    assert timing.events[0].offset_beats == Fraction(0)
    assert timing.events[0].duration_beats == Fraction(1)
    assert timing.events[0].measure_offset_beats == Fraction(0)

    assert timing.events[1].offset_beats == Fraction(1)
    assert timing.events[2].offset_beats == Fraction(2)
    assert timing.events[3].offset_beats == Fraction(3)

    # Revisar compás 2
    assert timing.events[4].offset_beats == Fraction(4)
    assert timing.events[4].duration_beats == Fraction(2)
    assert timing.events[4].measure_offset_beats == Fraction(0)

    assert timing.events[5].offset_beats == Fraction(6)
    assert timing.events[5].duration_beats == Fraction(2)
    assert timing.events[5].measure_offset_beats == Fraction(2)


def test_polyphony_multiple_voices_timing() -> None:
    # Compás 1: Voz 0 tiene dos blancas (2 beats c/u); Voz 1 tiene cuatro negras (1 beat c/u)
    m1 = Measure(
        number=1,
        time_signature=TimeSignature(beats=4, beat_type=4),
        events=(
            Event(kind=EventKind.NOTE, voice=0, pitch="C5", duration_beats=Fraction(2)),
            Event(kind=EventKind.NOTE, voice=0, pitch="D5", duration_beats=Fraction(2)),
            Event(kind=EventKind.NOTE, voice=1, pitch="C4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=1, pitch="E4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=1, pitch="G4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=1, pitch="B4", duration_beats=Fraction(1)),
        ),
    )
    score = ScoreIR(parts=(Part(id="P1", staves=(Staff(id="P1-1", measures=(m1,)),)),))

    timing = compute_timing_map(score)
    assert timing.total_beats == Fraction(4)

    # Buscar eventos de voz 0
    v0_events = [e for e in timing.events if e.voice == 0]
    assert len(v0_events) == 2
    assert v0_events[0].offset_beats == Fraction(0)
    assert v0_events[0].duration_beats == Fraction(2)
    assert v0_events[1].offset_beats == Fraction(2)
    assert v0_events[1].duration_beats == Fraction(2)

    # Buscar eventos de voz 1
    v1_events = [e for e in timing.events if e.voice == 1]
    assert len(v1_events) == 4
    assert [e.offset_beats for e in v1_events] == [
        Fraction(0),
        Fraction(1),
        Fraction(2),
        Fraction(3),
    ]


def test_chords_and_rests_timing() -> None:
    # Acorde: C4 + E4 + G4 simultáneos en beat 0, luego silencio de negra en beat 1
    m1 = Measure(
        number=1,
        time_signature=TimeSignature(beats=2, beat_type=4),
        events=(
            Event(
                kind=EventKind.NOTE, voice=0, pitch="C4", duration_beats=Fraction(1), is_chord=False
            ),
            Event(
                kind=EventKind.NOTE, voice=0, pitch="E4", duration_beats=Fraction(1), is_chord=True
            ),
            Event(
                kind=EventKind.NOTE, voice=0, pitch="G4", duration_beats=Fraction(1), is_chord=True
            ),
            Event(
                kind=EventKind.REST, voice=0, pitch=None, duration_beats=Fraction(1), is_chord=False
            ),
        ),
    )
    score = ScoreIR(parts=(Part(id="P1", staves=(Staff(id="P1-1", measures=(m1,)),)),))

    timing = compute_timing_map(score)
    assert timing.total_beats == Fraction(2)

    # Las 3 notas del acorde deben compartir offset 0
    chord_notes = [e for e in timing.events if e.kind == EventKind.NOTE]
    assert len(chord_notes) == 3
    assert all(e.offset_beats == Fraction(0) for e in chord_notes)
    assert all(e.duration_beats == Fraction(1) for e in chord_notes)

    # El silencio debe estar en offset 1
    rests = [e for e in timing.events if e.kind == EventKind.REST]
    assert len(rests) == 1
    assert rests[0].offset_beats == Fraction(1)
    assert rests[0].duration_beats == Fraction(1)


def test_meter_change_timing() -> None:
    # Compás 1: 4/4 (4 beats)
    # Compás 2: 3/4 (3 beats)
    # Compás 3: 6/8 (3 beats)
    m1 = Measure(
        number=1,
        time_signature=TimeSignature(beats=4, beat_type=4),
        events=(Event(kind=EventKind.NOTE, voice=0, pitch="C4", duration_beats=Fraction(4)),),
    )
    m2 = Measure(
        number=2,
        time_signature=TimeSignature(beats=3, beat_type=4),
        events=(Event(kind=EventKind.NOTE, voice=0, pitch="D4", duration_beats=Fraction(3)),),
    )
    m3 = Measure(
        number=3,
        time_signature=TimeSignature(beats=6, beat_type=8),
        events=(Event(kind=EventKind.NOTE, voice=0, pitch="E4", duration_beats=Fraction(3)),),
    )
    score = ScoreIR(parts=(Part(id="P1", staves=(Staff(id="P1-1", measures=(m1, m2, m3)),)),))

    timing = compute_timing_map(score)
    assert timing.total_beats == Fraction(10)
    assert timing.measure_offsets == {
        1: Fraction(0),
        2: Fraction(4),
        3: Fraction(7),
    }
    assert timing.events[0].offset_beats == Fraction(0)
    assert timing.events[1].offset_beats == Fraction(4)
    assert timing.events[2].offset_beats == Fraction(7)


def test_timing_map_primitive_roundtrip() -> None:
    m1 = Measure(
        number=1,
        time_signature=TimeSignature(beats=4, beat_type=4),
        events=(
            Event(kind=EventKind.NOTE, voice=0, pitch="C4", duration_beats=Fraction(1)),
            Event(kind=EventKind.REST, voice=0, duration_beats=Fraction(1)),
        ),
    )
    score = ScoreIR(parts=(Part(id="P1", staves=(Staff(id="P1-1", measures=(m1,)),)),))
    timing = compute_timing_map(score)

    prim = timing.to_primitive()
    reconstructed = TimingMap.from_primitive(prim)

    assert reconstructed.total_beats == timing.total_beats
    assert reconstructed.measure_offsets == timing.measure_offsets
    assert len(reconstructed.events) == len(timing.events)
    assert reconstructed.events[0] == timing.events[0]

    # Probar búsqueda por ancla
    anchor = timing.events[0].anchor
    found = reconstructed.get(anchor)
    assert found is not None
    assert found.offset_beats == Fraction(0)


def test_timing_seconds_and_bpm_conversion() -> None:
    import pytest
    from cadenza.domain import Anchor

    anchor = Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="P1-1")
    ev = EventTiming(
        anchor=anchor,
        kind=EventKind.NOTE,
        measure_number=1,
        voice=0,
        offset_beats=Fraction(2),
        duration_beats=Fraction(1),
        measure_offset_beats=Fraction(2),
    )
    t_map = TimingMap(
        events=(ev,),
        total_beats=Fraction(4),
        measure_offsets={1: Fraction(0)},
    )

    # A 120 BPM: 1 beat = 0.5s
    assert ev.offset_seconds(120.0) == 1.0
    assert ev.duration_seconds(120.0) == 0.5
    assert t_map.total_seconds(120.0) == 2.0

    # A 60 BPM: 1 beat = 1.0s
    assert ev.offset_seconds(60.0) == 2.0
    assert ev.duration_seconds(60.0) == 1.0
    assert t_map.total_seconds(60.0) == 4.0

    # Validar BPM no positivo
    with pytest.raises(ValueError, match="BPM must be positive"):
        ev.offset_seconds(0)
    with pytest.raises(ValueError, match="BPM must be positive"):
        ev.duration_seconds(-10)
    with pytest.raises(ValueError, match="BPM must be positive"):
        t_map.total_seconds(0)


def test_timing_map_get_with_logical_anchor() -> None:
    from cadenza.domain import Anchor

    anchor_with_bbox = Anchor(
        part=0,
        staff=0,
        measure=1,
        voice=0,
        event_index=2,
        staff_id="P1-1",
        bbox=(10, 20, 30, 40),
        confidence=0.95,
    )
    ev = EventTiming(
        anchor=anchor_with_bbox,
        kind=EventKind.NOTE,
        measure_number=1,
        voice=0,
        offset_beats=Fraction(2),
        duration_beats=Fraction(1),
        measure_offset_beats=Fraction(2),
    )
    t_map = TimingMap(
        events=(ev,),
        total_beats=Fraction(4),
        measure_offsets={1: Fraction(0)},
    )

    # Ancla lógica pura (sin bbox ni confidence)
    logical_anchor = Anchor(part=0, staff=0, measure=1, voice=0, event_index=2, staff_id="P1-1")
    found = t_map.get(logical_anchor)
    assert found is not None
    assert found.offset_beats == Fraction(2)
