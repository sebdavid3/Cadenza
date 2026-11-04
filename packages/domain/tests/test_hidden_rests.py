"""Silencios invisibles: el hueco de una voz que no empieza con el compás (ADR-0032, #218).

Un silencio invisible es un silencio más (`Event.hidden`): ocupa su tiempo en la voz, tiene
ancla y no se dibuja. Vacío no se serializa, como las marcas de ADR-0031.
"""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction
from typing import Any

import pytest
from cadenza.domain import (
    Anchor,
    EditEvent,
    EditOp,
    Event,
    EventKind,
    InvalidEditPayload,
    Measure,
    Part,
    ScoreIR,
    Staff,
    TimeSignature,
    apply_edit,
    build_anchor_index,
    compute_timing_map,
    create_inverse_edit,
    has_complete_before,
    materialize,
    snapshot_before,
    validate_after,
)

STAFF_ID = "part-0-staff-0"


def _score() -> ScoreIR:
    """Voz 0: un Mi5 redonda; voz 1: un hueco de dos negras y después Do5 y Si4."""

    events = (
        Event(kind=EventKind.NOTE, voice=0, pitch="E5", duration_beats=Fraction(4)),
        Event(kind=EventKind.REST, voice=1, duration_beats=Fraction(2), hidden=True),
        Event(kind=EventKind.NOTE, voice=1, pitch="C5", duration_beats=Fraction(1)),
        Event(kind=EventKind.NOTE, voice=1, pitch="B4", duration_beats=Fraction(1)),
    )
    measure = Measure(number=1, events=events, time_signature=TimeSignature(4, 4))
    return ScoreIR(parts=(Part(id="part-0", staves=(Staff(id=STAFF_ID, measures=(measure,)),)),))


def _anchor(event_index: int, voice: int = 1) -> Anchor:
    return Anchor(
        part=0, staff=0, measure=1, voice=voice, event_index=event_index, staff_id=STAFF_ID
    )


def _edit(
    op: EditOp,
    event_index: int,
    *,
    seq: int = 1,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> EditEvent:
    return EditEvent(
        id=f"e{seq}",
        document_id="doc-1",
        seq=seq,
        anchor=_anchor(event_index),
        op=op,
        author="ana",
        created_at=datetime(2026, 10, 24, tzinfo=UTC),
        before=before,
        after=after,
    )


def _events(score: ScoreIR) -> tuple[Event, ...]:
    return score.parts[0].staves[0].measures[0].events


def test_a_hidden_rest_is_serialized_only_when_hidden() -> None:
    score = _score()
    primitives = [event.to_primitive() for event in _events(score)]
    assert primitives[1]["hidden"] is True
    assert all("hidden" not in primitive for i, primitive in enumerate(primitives) if i != 1)
    assert ScoreIR.from_primitive(score.to_primitive()) == score


def test_a_document_saved_before_218_reads_with_visible_rests() -> None:
    saved = {
        "kind": "rest",
        "voice": 0,
        "pitch": None,
        "duration_beats": "1",
        "tie": None,
        "is_chord": False,
        "bbox": None,
        "confidence": None,
        "ir_handle": None,
    }
    event = Event.from_primitive(saved)
    assert event.hidden is False
    assert event.to_primitive() == saved


def test_only_a_rest_can_be_hidden() -> None:
    with pytest.raises(ValueError, match="silencio"):
        Event(kind=EventKind.NOTE, pitch="C5", duration_beats=Fraction(1), hidden=True)


def test_the_timing_map_places_the_notes_after_the_hidden_rest() -> None:
    timing = compute_timing_map(_score())
    onsets = {
        (t.anchor.voice, t.anchor.event_index): (t.kind, t.offset_beats) for t in timing.events
    }
    assert onsets == {
        (0, 0): (EventKind.NOTE, Fraction(0)),
        (1, 0): (EventKind.REST, Fraction(0)),
        (1, 1): (EventKind.NOTE, Fraction(2)),
        (1, 2): (EventKind.NOTE, Fraction(3)),
    }
    assert [t.offset_beats for t in timing.sounding_events()] == [0, 2, 3]
    assert timing.total_beats == 4


def test_the_hidden_rest_has_an_anchor_and_counts_in_event_index() -> None:
    anchors = {
        (anchor.voice, anchor.event_index): ref.kind
        for anchor, ref in build_anchor_index(_score()).items()
    }
    assert anchors == {
        (0, 0): EventKind.NOTE,
        (1, 0): EventKind.REST,
        (1, 1): EventKind.NOTE,
        (1, 2): EventKind.NOTE,
    }


def test_changing_the_duration_of_a_hidden_rest_keeps_it_hidden() -> None:
    score = _score()
    after = {"duration_beats": "1"}
    validate_after(score, _anchor(0), EditOp.SET_DURATION, after)
    edited = _events(apply_edit(score, _edit(EditOp.SET_DURATION, 0, after=after)))[1]
    assert edited == Event(kind=EventKind.REST, voice=1, duration_beats=Fraction(1), hidden=True)


def test_undoing_the_delete_of_a_hidden_rest_restores_it_hidden() -> None:
    score = _score()
    before = snapshot_before(score, _anchor(0), EditOp.DELETE_EVENT)
    assert before is not None
    assert before["hidden"] is True
    delete = _edit(EditOp.DELETE_EVENT, 0, before=before)
    assert has_complete_before(delete)
    inverse = create_inverse_edit(
        delete, id="inv", seq=2, author="ana", created_at=datetime(2026, 10, 24, tzinfo=UTC)
    )
    assert materialize(score, [delete, inverse]) == score


def test_insert_event_accepts_a_hidden_rest() -> None:
    score = _score()
    after = {"kind": "rest", "duration_beats": "1", "hidden": True}
    validate_after(score, _anchor(3), EditOp.INSERT_EVENT, after)
    inserted = _events(apply_edit(score, _edit(EditOp.INSERT_EVENT, 3, after=after)))[4]
    assert inserted == Event(kind=EventKind.REST, voice=1, duration_beats=Fraction(1), hidden=True)


@pytest.mark.parametrize(
    "after",
    [
        {"kind": "note", "pitch": "C5", "duration_beats": "1", "hidden": True},
        {"kind": "rest", "duration_beats": "1", "hidden": "yes"},
    ],
)
def test_insert_event_rejects_a_hidden_note_or_a_non_boolean_hidden(after: dict[str, Any]) -> None:
    with pytest.raises(InvalidEditPayload, match="hidden"):
        validate_after(_score(), _anchor(3), EditOp.INSERT_EVENT, after)
