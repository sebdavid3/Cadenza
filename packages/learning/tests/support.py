"""Fábricas de objetos de dominio para los tests de `cadenza.learning`."""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction

from cadenza.domain import (
    Anchor,
    EditEvent,
    EditOp,
    Event,
    EventKind,
    Finding,
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


def make_document(document_id: str = "doc-1") -> ScoreDocument:
    measure = Measure(
        number=1,
        events=(
            Event(kind=EventKind.NOTE, voice=0, pitch="C4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=0, pitch="D4", duration_beats=Fraction(1)),
        ),
        time_signature=TimeSignature(4, 4),
    )
    staff = Staff(id="part-0-staff-0", measures=(measure,))
    score = ScoreIR(parts=(Part(id="part-0", staves=(staff,)),))
    return ScoreDocument(
        id=document_id,
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="fake"),
    )


def make_anchor(event_index: int = 0, measure: int = 1) -> Anchor:
    return Anchor(
        part=0,
        staff=0,
        measure=measure,
        voice=0,
        event_index=event_index,
        staff_id="part-0-staff-0",
    )


def make_edit(
    seq: int,
    anchor: Anchor,
    before: str | None,
    after: str | None,
    *,
    document_id: str = "doc-1",
    op: EditOp = EditOp.SET_PITCH,
) -> EditEvent:
    return EditEvent(
        id=f"edit-{seq}",
        document_id=document_id,
        seq=seq,
        anchor=anchor,
        op=op,
        author="tester",
        created_at=datetime(2026, 9, 20, tzinfo=UTC),
        before=None if before is None else {"pitch": before},
        after=None if after is None else {"pitch": after},
    )


def make_finding(anchor: Anchor, rule_id: str = "measure.balance") -> Finding:
    return Finding(anchor=anchor, rule_id=rule_id, severity=Severity.ERROR, message="msg")
