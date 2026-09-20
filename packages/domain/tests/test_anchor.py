"""Pruebas del `AnchorIndex`: determinismo, estabilidad y validación."""

from __future__ import annotations

import pytest
from cadenza.domain import (
    Anchor,
    AnchorIndex,
    EventKind,
    build_anchor_index,
)
from cadenza.domain.score import Event, Measure, Part, ScoreIR, Staff


def _sample_score() -> ScoreIR:
    measure_one = Measure(
        number=1,
        events=(
            Event(kind=EventKind.NOTE, voice=0, pitch="C4"),
            Event(kind=EventKind.NOTE, voice=0, pitch="D4"),
            Event(kind=EventKind.NOTE, voice=1, pitch="E4"),
        ),
    )
    measure_two = Measure(
        number=2,
        events=(Event(kind=EventKind.REST, voice=0),),
    )
    staff = Staff(id="staff-0", measures=(measure_one, measure_two))
    part = Part(id="part-0", staves=(staff,))
    return ScoreIR(parts=(part,))


def test_build_anchor_index_is_deterministic() -> None:
    score = _sample_score()
    first = build_anchor_index(score)
    second = build_anchor_index(score)
    assert first == second
    assert first.anchors() == second.anchors()
    assert first.to_primitive() == second.to_primitive()


def test_anchor_index_assigns_stable_coordinates() -> None:
    index = build_anchor_index(_sample_score())
    anchors = index.anchors()
    assert len(anchors) == 4
    assert [(a.measure, a.voice, a.event_index) for a in anchors] == [
        (1, 0, 0),
        (1, 0, 1),
        (1, 1, 0),
        (2, 0, 0),
    ]
    assert all(a.staff_id == "staff-0" for a in anchors)


def test_anchor_index_lookup_and_membership() -> None:
    index = build_anchor_index(_sample_score())
    anchor = Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="staff-0")
    assert anchor in index
    reference = index.get(anchor)
    assert reference is not None
    assert reference.kind is EventKind.NOTE

    absent = Anchor(part=9, staff=9, measure=9, voice=9, event_index=9, staff_id="x")
    assert absent not in index
    assert index.get(absent) is None


def test_empty_index() -> None:
    index = AnchorIndex.empty()
    assert len(index) == 0
    assert index.anchors() == ()


def test_anchor_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        Anchor(part=-1, staff=0, measure=1, voice=0, event_index=0, staff_id="s")
    with pytest.raises(ValueError):
        Anchor(part=0, staff=0, measure=0, voice=0, event_index=0, staff_id="s")
    with pytest.raises(ValueError):
        Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="")
    with pytest.raises(ValueError):
        Anchor(
            part=0,
            staff=0,
            measure=1,
            voice=0,
            event_index=0,
            staff_id="s",
            confidence=1.5,
        )
