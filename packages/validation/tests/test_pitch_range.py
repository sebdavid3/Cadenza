"""Pruebas de la regla de rango tonal (PitchRangeRule)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from cadenza.domain import (
    Clef,
    Event,
    EventKind,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Severity,
    Staff,
    TimeSignature,
    build_anchor_index,
)
from cadenza.validation import PitchRangeRule, ValidationEngine


def _make_document(
    events: tuple[Event, ...],
    clef: Clef | None = None,
    staff_id: str = "staff-0",
) -> ScoreDocument:
    measure = Measure(
        number=1,
        events=events,
        time_signature=TimeSignature(4, 4),
        clef=clef or Clef.treble(),
    )
    staff = Staff(id=staff_id, measures=(measure,))
    part = Part(id="part-0", staves=(staff,))
    score = ScoreIR(parts=(part,))
    return ScoreDocument(
        id="test-range-doc",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="fake", model_version="1.0"),
    )


def test_rule_id() -> None:
    assert PitchRangeRule().rule_id == "pitch.range"


def test_normal_treble_notes_have_no_findings() -> None:
    doc = _make_document(
        (
            Event(kind=EventKind.NOTE, voice=0, pitch="C4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=0, pitch="G4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=0, pitch="E5", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=0, pitch="A5", duration_beats=Fraction(1)),
        ),
        clef=Clef.treble(),
    )
    engine = ValidationEngine([PitchRangeRule()])
    assert engine.validate(doc) == []


def test_extreme_low_note_in_treble_reports_warning() -> None:
    # C2 (MIDI 36) está muy por debajo de G2 (MIDI 43)
    doc = _make_document(
        (
            Event(kind=EventKind.NOTE, voice=0, pitch="C2", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=0, pitch="G4", duration_beats=Fraction(3)),
        ),
        clef=Clef.treble(),
    )
    engine = ValidationEngine([PitchRangeRule()])
    findings = engine.validate(doc)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "pitch.range"
    assert f.severity == Severity.WARNING
    assert "C2" in f.message
    assert f.anchor.event_index == 0
    assert f.suggested_fix is not None


def test_extreme_high_note_in_treble_reports_warning() -> None:
    # C8 (MIDI 108) está muy por encima de C7 (MIDI 96)
    doc = _make_document(
        (Event(kind=EventKind.NOTE, voice=0, pitch="C8", duration_beats=Fraction(4)),),
        clef=Clef.treble(),
    )
    engine = ValidationEngine([PitchRangeRule()])
    findings = engine.validate(doc)
    assert len(findings) == 1
    assert "C8" in findings[0].message
    assert findings[0].severity == Severity.WARNING


def test_bass_clef_notes_range() -> None:
    # En clave de Fa (F4): C1 a C5
    # C2 y G3 son válidos; C6 (MIDI 84) es excesivamente aguda para clave de Fa
    doc = _make_document(
        (
            Event(kind=EventKind.NOTE, voice=0, pitch="C2", duration_beats=Fraction(2)),
            Event(kind=EventKind.NOTE, voice=0, pitch="C6", duration_beats=Fraction(2)),
        ),
        clef=Clef.bass(),
    )
    engine = ValidationEngine([PitchRangeRule()])
    findings = engine.validate(doc)
    assert len(findings) == 1
    assert "C6" in findings[0].message
    assert "Fa en 4ª" in findings[0].message


def test_clef_octave_change_shifts_range() -> None:
    # Treble con octave_change = -1 (tenor vocal: rige 1 octava más abajo: G1 a C6)
    # Por tanto C3 es normal, pero G6 (MIDI 91) queda fuera
    doc = _make_document(
        (Event(kind=EventKind.NOTE, voice=0, pitch="G6", duration_beats=Fraction(4)),),
        clef=Clef(sign="G", line=2, octave_change=-1),
    )
    findings = ValidationEngine([PitchRangeRule()]).validate(doc)
    assert len(findings) == 1
    assert "G6" in findings[0].message


def test_rests_and_unparseable_pitches_are_ignored() -> None:
    doc = _make_document(
        (
            Event(kind=EventKind.REST, voice=0, duration_beats=Fraction(2)),
            Event(kind=EventKind.NOTE, voice=0, pitch=None, duration_beats=Fraction(2)),
        ),
        clef=Clef.treble(),
    )
    assert ValidationEngine([PitchRangeRule()]).validate(doc) == []


def test_rule_does_not_mutate_document(tmp_path: Path) -> None:
    doc = _make_document(
        (Event(kind=EventKind.NOTE, voice=0, pitch="C1", duration_beats=Fraction(4)),),
        clef=Clef.treble(),
    )
    snapshot = doc
    ValidationEngine([PitchRangeRule()]).validate(doc)
    assert doc == snapshot
