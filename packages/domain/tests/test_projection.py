"""Proyección del log de eventos sobre el `ScoreIR` (ADR-0007)."""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction

import pytest
from cadenza.domain import (
    Anchor,
    EditEvent,
    EditOp,
    Event,
    EventKind,
    Measure,
    Part,
    ScoreIR,
    Staff,
    TimeSignature,
    UnsupportedEditOpError,
    apply_edit,
    materialize,
)


def _score() -> ScoreIR:
    measure = Measure(
        number=1,
        events=(
            Event(kind=EventKind.NOTE, voice=0, pitch="C4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=0, pitch="D4", duration_beats=Fraction(1)),
        ),
        time_signature=TimeSignature(4, 4),
    )
    staff = Staff(id="part-0-staff-0", measures=(measure,))
    return ScoreIR(parts=(Part(id="part-0", staves=(staff,)),))


def _anchor(event_index: int = 0) -> Anchor:
    return Anchor(
        part=0,
        staff=0,
        measure=1,
        voice=0,
        event_index=event_index,
        staff_id="part-0-staff-0",
    )


def _edit(
    op: EditOp,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
    *,
    seq: int = 1,
    event_index: int = 0,
) -> EditEvent:
    return EditEvent(
        id=f"edit-{seq}",
        document_id="doc-1",
        seq=seq,
        anchor=_anchor(event_index),
        op=op,
        author="tester",
        created_at=datetime(2026, 9, 20, tzinfo=UTC),
        before=before,
        after=after,
    )


def _pitches(score: ScoreIR) -> list[str | None]:
    return [event.pitch for event in score.parts[0].staves[0].measures[0].events]


def test_set_pitch_updates_without_mutating_original() -> None:
    score = _score()
    updated = apply_edit(score, _edit(EditOp.SET_PITCH, {"pitch": "C4"}, {"pitch": "F#4"}))
    assert _pitches(updated) == ["F#4", "D4"]
    assert _pitches(score) == ["C4", "D4"]


def test_materialize_applies_events_in_seq_order() -> None:
    score = _score()
    first = _edit(EditOp.SET_PITCH, {"pitch": "C4"}, {"pitch": "D4"}, seq=1)
    second = _edit(EditOp.SET_PITCH, {"pitch": "D4"}, {"pitch": "E4"}, seq=2)
    assert _pitches(materialize(score, [second, first])) == ["E4", "D4"]


def test_delete_event_removes_target() -> None:
    updated = apply_edit(_score(), _edit(EditOp.DELETE_EVENT, {"pitch": "C4"}, None))
    assert _pitches(updated) == ["D4"]


def test_insert_event_adds_target() -> None:
    edit = _edit(
        EditOp.INSERT_EVENT,
        None,
        {"kind": "note", "pitch": "A4", "duration_beats": "2"},
    )
    updated = apply_edit(_score(), edit)
    assert _pitches(updated) == ["A4", "C4", "D4"]


def test_unsupported_op_is_explicit() -> None:
    with pytest.raises(UnsupportedEditOpError):
        apply_edit(_score(), _edit(EditOp.SET_CLEF, None, {"clef": "treble"}))
