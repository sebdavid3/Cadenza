"""Pruebas de la regla de colisión de voces (VoiceCollisionRule)."""

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
from cadenza.validation import ValidationEngine, VoiceCollisionRule


def _make_document(
    events: tuple[Event, ...],
    staff_id: str = "staff-0",
) -> ScoreDocument:
    measure = Measure(
        number=1,
        events=events,
        time_signature=TimeSignature(4, 4),
        clef=Clef.treble(),
    )
    staff = Staff(id=staff_id, measures=(measure,))
    part = Part(id="part-0", staves=(staff,))
    score = ScoreIR(parts=(part,))
    return ScoreDocument(
        id="test-collision-doc",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="fake", model_version="1.0"),
    )


def test_rule_id() -> None:
    assert VoiceCollisionRule().rule_id == "voice.collision"


def test_valid_monophonic_and_chords_have_no_findings() -> None:
    # Compás con una nota sola y luego un acorde de 3 notas con la misma duración
    doc = _make_document(
        (
            Event(kind=EventKind.NOTE, voice=0, pitch="C4", duration_beats=Fraction(1)),
            # Acorde de blanca en tiempo 2: C4, E4, G4
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="C4",
                duration_beats=Fraction(2),
                is_chord=False,
            ),
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="E4",
                duration_beats=Fraction(2),
                is_chord=True,
            ),
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="G4",
                duration_beats=Fraction(2),
                is_chord=True,
            ),
            Event(kind=EventKind.REST, voice=0, duration_beats=Fraction(1)),
        )
    )
    engine = ValidationEngine([VoiceCollisionRule()])
    assert engine.validate(doc) == []


def test_chord_duration_mismatch_reports_error() -> None:
    # Nota base dura 2, pero nota del acorde dura 1 (desincronización temporal)
    doc = _make_document(
        (
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="C4",
                duration_beats=Fraction(2),
                is_chord=False,
            ),
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="G4",
                duration_beats=Fraction(1),
                is_chord=True,
            ),
            Event(kind=EventKind.REST, voice=0, duration_beats=Fraction(2)),
        )
    )
    findings = ValidationEngine([VoiceCollisionRule()]).validate(doc)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "voice.collision"
    assert f.severity == Severity.ERROR
    assert "Desincronización temporal" in f.message
    assert f.anchor.event_index == 1
    assert f.suggested_fix is not None


def test_orphaned_chord_event_without_base_reports_error() -> None:
    # Primer evento de la voz marcado como is_chord=True
    doc = _make_document(
        (
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="E4",
                duration_beats=Fraction(4),
                is_chord=True,
            ),
        )
    )
    findings = ValidationEngine([VoiceCollisionRule()]).validate(doc)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "voice.collision"
    assert f.severity == Severity.ERROR
    assert "sin una nota base previa" in f.message


def test_duplicate_pitch_in_same_chord_reports_error() -> None:
    # Acorde con C4 y C4 en la misma voz
    doc = _make_document(
        (
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="C4",
                duration_beats=Fraction(4),
                is_chord=False,
            ),
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="C4",
                duration_beats=Fraction(4),
                is_chord=True,
            ),
        )
    )
    findings = ValidationEngine([VoiceCollisionRule()]).validate(doc)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "voice.collision"
    assert f.severity == Severity.ERROR
    assert "Altura duplicada C4" in f.message


def test_rest_as_chord_reports_error() -> None:
    # Silencio con is_chord=True
    doc = _make_document(
        (
            Event(
                kind=EventKind.REST,
                voice=0,
                duration_beats=Fraction(4),
                is_chord=True,
            ),
        )
    )
    findings = ValidationEngine([VoiceCollisionRule()]).validate(doc)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "voice.collision"
    assert f.severity == Severity.ERROR
    assert "Un silencio no puede formar parte de un acorde" in f.message


def test_non_positive_duration_reports_error() -> None:
    # Evento con duración 0
    doc = _make_document(
        (
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="C4",
                duration_beats=Fraction(0),
            ),
            Event(kind=EventKind.NOTE, voice=0, pitch="D4", duration_beats=Fraction(4)),
        )
    )
    findings = ValidationEngine([VoiceCollisionRule()]).validate(doc)
    assert any("Duración no positiva" in f.message for f in findings)


def test_rule_does_not_mutate_document(tmp_path: Path) -> None:
    doc = _make_document(
        (
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="C4",
                duration_beats=Fraction(4),
                is_chord=True,
            ),
        )
    )
    snapshot = doc
    ValidationEngine([VoiceCollisionRule()]).validate(doc)
    assert doc == snapshot
