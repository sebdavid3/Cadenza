"""Pruebas de la regla de consistencia de armadura y alteraciones (KeyConsistencyRule)."""

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
    Provenance,
    ScoreDocument,
    ScoreIR,
    Severity,
    Staff,
    TimeSignature,
    build_anchor_index,
)
from cadenza.validation import KeyConsistencyRule, ValidationEngine


def _make_document(
    events: tuple[Event, ...],
    key_signature: KeySignature | None = None,
    staff_id: str = "staff-0",
) -> ScoreDocument:
    measure = Measure(
        number=1,
        events=events,
        time_signature=TimeSignature(4, 4),
        clef=Clef.treble(),
        key_signature=key_signature,
    )
    staff = Staff(id=staff_id, measures=(measure,))
    part = Part(id="part-0", staves=(staff,))
    score = ScoreIR(parts=(part,))
    return ScoreDocument(
        id="test-key-doc",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="fake", model_version="1.0"),
    )


def test_rule_id() -> None:
    assert KeyConsistencyRule().rule_id == "key.consistency"


def test_consistent_key_signature_notes_have_no_findings() -> None:
    # 2 sostenidos (Re mayor): D4, E4, F#4, A4
    doc = _make_document(
        (
            Event(kind=EventKind.NOTE, voice=0, pitch="D4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=0, pitch="E4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=0, pitch="F#4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=0, pitch="A4", duration_beats=Fraction(1)),
        ),
        key_signature=KeySignature(fifths=2),
    )
    engine = ValidationEngine([KeyConsistencyRule()])
    assert engine.validate(doc) == []


def test_flat_in_sharp_key_reports_warning() -> None:
    # 2 sostenidos, pero aparece Bb4
    doc = _make_document(
        (
            Event(kind=EventKind.NOTE, voice=0, pitch="D4", duration_beats=Fraction(2)),
            Event(kind=EventKind.NOTE, voice=0, pitch="Bb4", duration_beats=Fraction(2)),
        ),
        key_signature=KeySignature(fifths=2),
    )
    findings = ValidationEngine([KeyConsistencyRule()]).validate(doc)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "key.consistency"
    assert f.severity == Severity.WARNING
    assert "Bb4" in f.message
    assert "bemol inconsistente" in f.message
    assert f.anchor.event_index == 1
    assert f.suggested_fix is not None


def test_sharp_in_flat_key_reports_warning() -> None:
    # 2 bemoles (Sib mayor, fifths = -2), pero aparece C#4
    doc = _make_document(
        (
            Event(kind=EventKind.NOTE, voice=0, pitch="Bb3", duration_beats=Fraction(2)),
            Event(kind=EventKind.NOTE, voice=0, pitch="C#4", duration_beats=Fraction(2)),
        ),
        key_signature=KeySignature(fifths=-2),
    )
    findings = ValidationEngine([KeyConsistencyRule()]).validate(doc)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "key.consistency"
    assert f.severity == Severity.WARNING
    assert "C#4" in f.message
    assert "sostenido inconsistente" in f.message


def test_contradictory_accidentals_in_same_measure_and_voice() -> None:
    # F#4 y Fb4 en el mismo compás y voz
    doc = _make_document(
        (
            Event(kind=EventKind.NOTE, voice=0, pitch="F#4", duration_beats=Fraction(2)),
            Event(kind=EventKind.NOTE, voice=0, pitch="Fb4", duration_beats=Fraction(2)),
        ),
        key_signature=KeySignature(fifths=0),
    )
    findings = ValidationEngine([KeyConsistencyRule()]).validate(doc)
    assert any("contradictorias" in f.message for f in findings)


def test_piano_staves_key_signature_discrepancy() -> None:
    # Piano: Pentagrama 0 con 2 sostenidos, Pentagrama 1 con 0 sostenidos
    m1_s0 = Measure(
        number=1,
        events=(Event(kind=EventKind.NOTE, voice=0, pitch="D4", duration_beats=Fraction(4)),),
        time_signature=TimeSignature(4, 4),
        clef=Clef.treble(),
        key_signature=KeySignature(fifths=2),
    )
    m1_s1 = Measure(
        number=1,
        events=(Event(kind=EventKind.NOTE, voice=0, pitch="D3", duration_beats=Fraction(4)),),
        time_signature=TimeSignature(4, 4),
        clef=Clef.bass(),
        key_signature=KeySignature(fifths=0),
    )
    staff_0 = Staff(id="piano-staff-0", measures=(m1_s0,))
    staff_1 = Staff(id="piano-staff-1", measures=(m1_s1,))
    part = Part(id="part-0", staves=(staff_0, staff_1))
    score = ScoreIR(parts=(part,))
    doc = ScoreDocument(
        id="piano-key-doc",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="fake", model_version="1.0"),
    )

    findings = ValidationEngine([KeyConsistencyRule()]).validate(doc)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "key.consistency"
    assert f.severity == Severity.WARNING
    assert "Discrepancia de armadura en compás 1" in f.message
    assert "pentagrama 1" in f.message
    assert f.suggested_fix is not None


def test_rule_does_not_mutate_document(tmp_path: Path) -> None:
    doc = _make_document(
        (Event(kind=EventKind.NOTE, voice=0, pitch="Bb4", duration_beats=Fraction(4)),),
        key_signature=KeySignature(fifths=1),
    )
    snapshot = doc
    ValidationEngine([KeyConsistencyRule()]).validate(doc)
    assert doc == snapshot
