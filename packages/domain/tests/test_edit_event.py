"""Pruebas de inmutabilidad, igualdad e igualdad por hash de `EditEvent`."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from cadenza.domain import Anchor, EditEvent, EditOp


def _anchor() -> Anchor:
    return Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="staff-0")


def _event(
    before: dict[str, str] | None = None,
    after: dict[str, str] | None = None,
) -> EditEvent:
    return EditEvent(
        id="edit-1",
        document_id="doc-1",
        seq=0,
        anchor=_anchor(),
        op=EditOp.SET_PITCH,
        author="tester",
        created_at=datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
        before=before,
        after=after,
    )


def test_edit_event_is_frozen() -> None:
    event = _event()
    with pytest.raises(FrozenInstanceError):
        event.seq = 1  # type: ignore[misc]


def test_edit_event_mappings_are_immutable() -> None:
    event = _event(before={"pitch": "C4"})
    before = event.before
    assert before is not None
    with pytest.raises(TypeError):
        before["pitch"] = "D4"  # type: ignore[index]


def test_edit_event_equality_and_hash() -> None:
    assert _event() == _event()
    assert _event(before={"pitch": "C4"}) != _event(before={"pitch": "D4"})
    assert len({_event(), _event()}) == 1


def test_edit_event_rejects_invalid_values() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValueError):
        EditEvent(
            id="",
            document_id="doc",
            seq=0,
            anchor=_anchor(),
            op=EditOp.SET_PITCH,
            author="a",
            created_at=now,
        )
    with pytest.raises(ValueError):
        EditEvent(
            id="e",
            document_id="doc",
            seq=-1,
            anchor=_anchor(),
            op=EditOp.SET_PITCH,
            author="a",
            created_at=now,
        )
    with pytest.raises(ValueError):
        EditEvent(
            id="e",
            document_id="doc",
            seq=0,
            anchor=_anchor(),
            op=EditOp.SET_PITCH,
            author="",
            created_at=now,
        )


def test_edit_op_members() -> None:
    assert set(EditOp) == {
        EditOp.SET_PITCH,
        EditOp.SET_DURATION,
        EditOp.SET_ACCIDENTAL,
        EditOp.INSERT_EVENT,
        EditOp.DELETE_EVENT,
        EditOp.SET_CLEF,
        EditOp.SET_KEY,
    }
