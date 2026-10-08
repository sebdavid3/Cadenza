"""Pruebas de la regla de ligaduras y cierres (TieResolutionRule)."""

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
    Tie,
    TimeSignature,
    build_anchor_index,
)
from cadenza.validation import TieResolutionRule, ValidationEngine


def _make_document(
    measures_events: list[tuple[Event, ...]],
    staff_id: str = "staff-0",
) -> ScoreDocument:
    measures = tuple(
        Measure(
            number=i + 1,
            events=events,
            time_signature=TimeSignature(4, 4),
            clef=Clef.treble(),
        )
        for i, events in enumerate(measures_events)
    )
    staff = Staff(id=staff_id, measures=measures)
    part = Part(id="part-0", staves=(staff,))
    score = ScoreIR(parts=(part,))
    return ScoreDocument(
        id="test-tie-doc",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="fake", model_version="1.0"),
    )


def test_rule_id() -> None:
    assert TieResolutionRule().rule_id == "tie.resolution"


def test_valid_ties_have_no_findings() -> None:
    # Compás 1: nota con START ligada a STOP en compás 2
    doc = _make_document(
        [
            (
                Event(
                    kind=EventKind.NOTE,
                    voice=0,
                    pitch="C4",
                    duration_beats=Fraction(4),
                    tie=Tie.START,
                ),
            ),
            (
                Event(
                    kind=EventKind.NOTE,
                    voice=0,
                    pitch="C4",
                    duration_beats=Fraction(4),
                    tie=Tie.STOP,
                ),
            ),
        ]
    )
    engine = ValidationEngine([TieResolutionRule()])
    assert engine.validate(doc) == []


def test_valid_three_note_tie_chain_has_no_findings() -> None:
    # START -> CONTINUE -> STOP
    doc = _make_document(
        [
            (
                Event(
                    kind=EventKind.NOTE,
                    voice=0,
                    pitch="G4",
                    duration_beats=Fraction(4),
                    tie=Tie.START,
                ),
            ),
            (
                Event(
                    kind=EventKind.NOTE,
                    voice=0,
                    pitch="G4",
                    duration_beats=Fraction(4),
                    tie=Tie.CONTINUE,
                ),
            ),
            (
                Event(
                    kind=EventKind.NOTE,
                    voice=0,
                    pitch="G4",
                    duration_beats=Fraction(4),
                    tie=Tie.STOP,
                ),
            ),
        ]
    )
    assert ValidationEngine([TieResolutionRule()]).validate(doc) == []


def test_unresolved_open_tie_at_end_of_score_reports_warning() -> None:
    # Nota con START que nunca se cierra
    doc = _make_document(
        [
            (
                Event(
                    kind=EventKind.NOTE,
                    voice=0,
                    pitch="C4",
                    duration_beats=Fraction(4),
                    tie=Tie.START,
                ),
            ),
        ]
    )
    findings = ValidationEngine([TieResolutionRule()]).validate(doc)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "tie.resolution"
    assert f.severity == Severity.WARNING
    assert "nunca fue cerrada" in f.message
    assert f.suggested_fix is not None


def test_unmatched_tie_stop_reports_warning() -> None:
    # Nota con STOP sin un START previo
    doc = _make_document(
        [
            (
                Event(
                    kind=EventKind.NOTE,
                    voice=0,
                    pitch="D4",
                    duration_beats=Fraction(4),
                    tie=Tie.STOP,
                ),
            ),
        ]
    )
    findings = ValidationEngine([TieResolutionRule()]).validate(doc)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "tie.resolution"
    assert f.severity == Severity.WARNING
    assert "cierre de ligadura ('stop') sin ligadura previa" in f.message


def test_unmatched_tie_continue_reports_warning() -> None:
    # Nota con CONTINUE sin START previo
    doc = _make_document(
        [
            (
                Event(
                    kind=EventKind.NOTE,
                    voice=0,
                    pitch="E4",
                    duration_beats=Fraction(4),
                    tie=Tie.CONTINUE,
                ),
            ),
            (
                Event(
                    kind=EventKind.NOTE,
                    voice=0,
                    pitch="E4",
                    duration_beats=Fraction(4),
                    tie=Tie.STOP,
                ),
            ),
        ]
    )
    findings = ValidationEngine([TieResolutionRule()]).validate(doc)
    assert len(findings) == 1
    assert "sin ligadura previa" in findings[0].message


def test_rest_with_tie_reports_warning() -> None:
    # Silencio con ligadura
    doc = _make_document(
        [
            (
                Event(
                    kind=EventKind.REST,
                    voice=0,
                    duration_beats=Fraction(4),
                    tie=Tie.START,
                ),
            ),
        ]
    )
    findings = ValidationEngine([TieResolutionRule()]).validate(doc)
    assert len(findings) == 1
    assert "Un silencio no puede tener ligadura" in findings[0].message


def test_tie_interrupted_by_untied_note_reports_warning() -> None:
    # START en compás 1, pero compás 2 tiene la misma nota sin ligadura (None)
    doc = _make_document(
        [
            (
                Event(
                    kind=EventKind.NOTE,
                    voice=0,
                    pitch="C4",
                    duration_beats=Fraction(4),
                    tie=Tie.START,
                ),
            ),
            (
                Event(
                    kind=EventKind.NOTE,
                    voice=0,
                    pitch="C4",
                    duration_beats=Fraction(4),
                    tie=None,
                ),
            ),
        ]
    )
    findings = ValidationEngine([TieResolutionRule()]).validate(doc)
    assert len(findings) == 1
    assert "quedó interrumpida" in findings[0].message


def test_rule_does_not_mutate_document(tmp_path: Path) -> None:
    doc = _make_document(
        [
            (
                Event(
                    kind=EventKind.NOTE,
                    voice=0,
                    pitch="C4",
                    duration_beats=Fraction(4),
                    tie=Tie.START,
                ),
            ),
        ]
    )
    snapshot = doc
    ValidationEngine([TieResolutionRule()]).validate(doc)
    assert doc == snapshot
