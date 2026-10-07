"""Pruebas de Clef, KeySignature, Tie y compatibilidad en ScoreIR (ADR-0010, #2)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

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
    build_anchor_index,
)


def test_clef_value_object() -> None:
    clef_g = Clef(sign="G", line=2, octave_change=0)
    assert clef_g.sign == "G"
    assert clef_g.line == 2
    assert clef_g.octave_change == 0

    assert Clef.treble() == Clef(sign="G", line=2, octave_change=0)
    assert Clef.bass() == Clef(sign="F", line=4, octave_change=0)
    assert Clef.alto() == Clef(sign="C", line=3, octave_change=0)
    assert Clef.tenor() == Clef(sign="C", line=4, octave_change=0)

    # Inmutabilidad
    with pytest.raises(FrozenInstanceError):
        clef_g.sign = "F"  # type: ignore[misc]

    # Validaciones
    with pytest.raises(ValueError, match="sign must be non-empty"):
        Clef(sign="", line=2)
    with pytest.raises(ValueError, match="line must be positive"):
        Clef(sign="G", line=0)

    # Roundtrip primitivo
    primitive = clef_g.to_primitive()
    assert primitive == {"sign": "G", "line": 2, "octave_change": 0}
    assert Clef.from_primitive(primitive) == clef_g


def test_key_signature_value_object() -> None:
    key_sig = KeySignature(fifths=2, mode="major")
    assert key_sig.fifths == 2
    assert key_sig.mode == "major"

    # Inmutabilidad
    with pytest.raises(FrozenInstanceError):
        key_sig.fifths = 3  # type: ignore[misc]

    # Rango de quintas (-7 a 7)
    with pytest.raises(ValueError, match="fifths must be between -7 and 7"):
        KeySignature(fifths=8)
    with pytest.raises(ValueError, match="fifths must be between -7 and 7"):
        KeySignature(fifths=-8)

    # Roundtrip primitivo
    primitive = key_sig.to_primitive()
    assert primitive == {"fifths": 2, "mode": "major"}
    assert KeySignature.from_primitive(primitive) == key_sig


def test_tie_enum() -> None:
    assert Tie.START.value == "start"
    assert Tie.CONTINUE.value == "continue"
    assert Tie.STOP.value == "stop"


def test_measure_and_event_with_attributes_roundtrip() -> None:
    event_start = Event(kind=EventKind.NOTE, voice=0, pitch="C4", tie=Tie.START)
    event_stop = Event(kind=EventKind.NOTE, voice=0, pitch="C4", tie=Tie.STOP)
    measure = Measure(
        number=1,
        events=(event_start, event_stop),
        time_signature=TimeSignature(4, 4),
        clef=Clef.treble(),
        key_signature=KeySignature(1, "major"),
    )
    staff = Staff(id="staff-0", measures=(measure,))
    score = ScoreIR(parts=(Part(id="part-0", staves=(staff,)),))

    primitive = score.to_primitive()
    reconstructed = ScoreIR.from_primitive(primitive)
    assert reconstructed == score

    rec_measure = reconstructed.parts[0].staves[0].measures[0]
    assert rec_measure.clef == Clef.treble()
    assert rec_measure.key_signature == KeySignature(1, "major")
    assert rec_measure.events[0].tie == Tie.START
    assert rec_measure.events[1].tie == Tie.STOP


def test_backward_compatibility_deserialization() -> None:
    """Documentos serializados antes del cambio siguen siendo válidos."""
    legacy_measure_primitive = {
        "number": 1,
        "events": [
            {
                "kind": "note",
                "voice": 0,
                "pitch": "C4",
                "duration_beats": "1",
                # Sin campo "tie"
            },
            {
                "kind": "rest",
                "voice": 0,
                "pitch": None,
                "duration_beats": "1",
            },
        ],
        "time_signature": {"beats": 4, "beat_type": 4},
        # Sin campos "clef" ni "key_signature"
    }

    measure = Measure.from_primitive(legacy_measure_primitive)
    assert measure.number == 1
    assert measure.clef is None
    assert measure.key_signature is None
    assert measure.time_signature == TimeSignature(4, 4)
    assert measure.events[0].tie is None
    assert measure.events[1].tie is None


def test_anchor_index_stability_with_attributes() -> None:
    """Clef y KeySignature son atributos del compás y no afectan el AnchorIndex."""
    measure_plain = Measure(
        number=1,
        events=(
            Event(kind=EventKind.NOTE, voice=0, pitch="C4"),
            Event(kind=EventKind.NOTE, voice=0, pitch="D4"),
        ),
    )
    staff_plain = Staff(id="staff-0", measures=(measure_plain,))
    score_plain = ScoreIR(parts=(Part(id="part-0", staves=(staff_plain,)),))

    measure_with_attrs = Measure(
        number=1,
        events=(
            Event(kind=EventKind.NOTE, voice=0, pitch="C4", tie=Tie.START),
            Event(kind=EventKind.NOTE, voice=0, pitch="D4", tie=Tie.STOP),
        ),
        clef=Clef.treble(),
        key_signature=KeySignature(2),
    )
    staff_with_attrs = Staff(id="staff-0", measures=(measure_with_attrs,))
    score_with_attrs = ScoreIR(parts=(Part(id="part-0", staves=(staff_with_attrs,)),))

    index_plain = build_anchor_index(score_plain)
    index_with_attrs = build_anchor_index(score_with_attrs)

    # Las anclas y sus posiciones son exactamente idénticas
    assert len(index_plain) == len(index_with_attrs) == 2
    for anchor_plain, anchor_attrs in zip(index_plain, index_with_attrs, strict=True):
        assert anchor_plain.part == anchor_attrs.part
        assert anchor_plain.staff == anchor_attrs.staff
        assert anchor_plain.measure == anchor_attrs.measure
        assert anchor_plain.voice == anchor_attrs.voice
        assert anchor_plain.event_index == anchor_attrs.event_index
