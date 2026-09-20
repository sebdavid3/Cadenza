"""Pruebas de serialización round-trip de los modelos del dominio."""

from __future__ import annotations

from datetime import UTC, datetime

from cadenza.domain import (
    Anchor,
    AnchorIndex,
    EditEvent,
    EditOp,
    EventKind,
    EventRef,
    Finding,
    Provenance,
    ScoreDocument,
    Severity,
    build_anchor_index,
)
from cadenza.domain.score import Event, Measure, Part, ScoreIR, Staff


def _sample_score() -> ScoreIR:
    measure = Measure(
        number=1,
        events=(
            Event(kind=EventKind.NOTE, voice=0, pitch="C4"),
            Event(kind=EventKind.REST, voice=0),
        ),
    )
    staff = Staff(id="staff-0", measures=(measure,))
    return ScoreIR(parts=(Part(id="part-0", staves=(staff,)),))


def test_anchor_roundtrip() -> None:
    anchor = Anchor(
        part=1,
        staff=2,
        measure=3,
        voice=0,
        event_index=4,
        staff_id="staff-2",
        bbox=(1.0, 2.0, 3.0, 4.0),
        confidence=0.9,
    )
    assert Anchor.from_primitive(anchor.to_primitive()) == anchor


def test_event_ref_roundtrip() -> None:
    reference = EventRef(
        kind=EventKind.NOTE,
        ir_handle="handle-1",
        bbox=(0.0, 0.0, 1.0, 1.0),
        confidence=0.5,
    )
    assert EventRef.from_primitive(reference.to_primitive()) == reference


def test_anchor_index_roundtrip() -> None:
    index = build_anchor_index(_sample_score())
    assert AnchorIndex.from_primitive(index.to_primitive()) == index


def test_score_ir_roundtrip() -> None:
    score = _sample_score()
    assert ScoreIR.from_primitive(score.to_primitive()) == score


def test_provenance_roundtrip() -> None:
    provenance = Provenance(
        omr_engine="homr",
        model_version="0.1.0",
        rules_version="rules-1",
        source_image_hash="deadbeef",
        created_at=datetime(2026, 9, 20, tzinfo=UTC),
    )
    assert Provenance.from_primitive(provenance.to_primitive()) == provenance


def test_score_document_roundtrip() -> None:
    score = _sample_score()
    document = ScoreDocument(
        id="doc-1",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="homr"),
    )
    assert ScoreDocument.from_primitive(document.to_primitive()) == document


def test_edit_event_roundtrip() -> None:
    event = EditEvent(
        id="edit-1",
        document_id="doc-1",
        seq=2,
        anchor=Anchor(
            part=0,
            staff=0,
            measure=1,
            voice=0,
            event_index=0,
            staff_id="staff-0",
        ),
        op=EditOp.SET_PITCH,
        author="tester",
        created_at=datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
        before={"pitch": "C4"},
        after={"pitch": "D4"},
    )
    assert EditEvent.from_primitive(event.to_primitive()) == event


def test_finding_roundtrip() -> None:
    finding = Finding(
        anchor=Anchor(
            part=0,
            staff=0,
            measure=7,
            voice=0,
            event_index=0,
            staff_id="staff-0",
        ),
        rule_id="measure.balance",
        severity=Severity.ERROR,
        message="Las duraciones no suman la métrica del compás.",
        suggested_fix="Ajustar la última figura.",
    )
    assert Finding.from_primitive(finding.to_primitive()) == finding
