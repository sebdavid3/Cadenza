"""`append_edit` y `undo_edit` ante `after` inválido y `before` ausente (#117, ADR-0017)."""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction
from typing import Any

import pytest
from cadenza.application import (
    InMemoryEditEventRepository,
    InMemorySessionRepository,
    InvalidEdit,
    Role,
    SessionData,
    SessionStatus,
    User,
    append_edit,
    undo_edit,
)
from cadenza.domain import (
    Anchor,
    Clef,
    EditEvent,
    EditOp,
    Event,
    EventKind,
    KeySignature,
    Measure,
    Part,
    ScoreIR,
    Staff,
    TimeSignature,
    materialize,
)

USER = User(id="u1", username="transcriptor1", password_hash="h", role=Role.TRANSCRIPTOR)
NOTE = Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="s0")


def _score() -> ScoreIR:
    measure = Measure(
        number=1,
        events=(
            Event(kind=EventKind.NOTE, pitch="C4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, pitch="D4", duration_beats=Fraction(1)),
            Event(kind=EventKind.REST, duration_beats=Fraction(2)),
        ),
        time_signature=TimeSignature(4, 4),
        clef=Clef.treble(),
        key_signature=KeySignature(fifths=0, mode="major"),
    )
    return ScoreIR(parts=(Part(id="p0", staves=(Staff(id="s0", measures=(measure,)),)),))


def _repos() -> tuple[InMemorySessionRepository, InMemoryEditEventRepository]:
    session_repo = InMemorySessionRepository()
    session_repo.add(
        SessionData(
            id="s1",
            document_id="d1",
            omr_engine="fake",
            model_version=None,
            status=SessionStatus.TRANSCRIBED,
            image_artifact="a1",
            document={"score": _score().to_primitive()},
            validated_at_seq=0,
            owner_id=USER.id,
        ),
        findings=(),
    )
    return session_repo, InMemoryEditEventRepository()


def _append(
    session_repo: InMemorySessionRepository,
    edit_repo: InMemoryEditEventRepository,
    op: EditOp,
    *,
    after: dict[str, Any] | None,
    before: dict[str, Any] | None = None,
    anchor: Anchor = NOTE,
) -> EditEvent:
    events = edit_repo.list_events("s1")
    return append_edit(
        "s1",
        anchor=anchor,
        op=op,
        base_seq=events[-1].seq if events else 0,
        before=before,
        after=after,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=USER,
    )


@pytest.mark.parametrize(
    ("op", "after"),
    [
        (EditOp.SET_PITCH, {}),
        (EditOp.SET_PITCH, None),
        (EditOp.SET_PITCH, {"pitch": "H9"}),
        (EditOp.SET_DURATION, {}),
        (EditOp.SET_KEY, {"fifths": 9}),
        (EditOp.DELETE_EVENT, {"pitch": "C4"}),
    ],
)
def test_append_edit_rejects_invalid_after_without_persisting(
    op: EditOp, after: dict[str, Any] | None
) -> None:
    session_repo, edit_repo = _repos()
    with pytest.raises(InvalidEdit, match="after"):
        _append(session_repo, edit_repo, op, after=after)
    assert edit_repo.list_events("s1") == ()
    session = session_repo.get("s1")
    assert session is not None and session.status == SessionStatus.TRANSCRIBED


@pytest.mark.parametrize(
    ("op", "before", "after"),
    [
        (EditOp.SET_KEY, {"key_signature": None}, {"fifths": 1}),
        (EditOp.SET_CLEF, {"foo": 1}, {"sign": "F", "line": 4}),
        (EditOp.SET_DURATION, {"duration_beats": "abc"}, {"duration_beats": "2"}),
        (EditOp.SET_ACCIDENTAL, {"accidental": "#"}, {"accidental": "b"}),
    ],
)
def test_append_edit_rejects_unusable_or_mismatched_before(
    op: EditOp, before: dict[str, Any], after: dict[str, Any]
) -> None:
    session_repo, edit_repo = _repos()
    with pytest.raises(InvalidEdit, match="before"):
        _append(session_repo, edit_repo, op, before=before, after=after)
    assert edit_repo.list_events("s1") == ()


@pytest.mark.parametrize("before_accidental", [None, "", "natural", "n", "none"])
def test_append_edit_accepts_before_accidental_aliases(before_accidental: str | None) -> None:
    session_repo, edit_repo = _repos()
    edit = _append(
        session_repo,
        edit_repo,
        EditOp.SET_ACCIDENTAL,
        before={"accidental": before_accidental},
        after={"accidental": "#"},
    )
    assert edit.before == {"accidental": ""}


def test_append_edit_stores_server_snapshot_as_before() -> None:
    session_repo, edit_repo = _repos()
    pitch = _append(session_repo, edit_repo, EditOp.SET_PITCH, after={"pitch": "E4"})
    assert pitch.before == {"pitch": "C4"}
    deleted = _append(
        session_repo, edit_repo, EditOp.DELETE_EVENT, before={"pitch": "E4"}, after=None
    )
    assert deleted.before == {
        "kind": "note",
        "pitch": "E4",
        "duration_beats": "1",
        "tie": None,
        "is_chord": False,
        "bbox": None,
        "confidence": None,
    }


VALID_EDITS: list[tuple[EditOp, dict[str, Any] | None]] = [
    (EditOp.SET_PITCH, {"pitch": "E4"}),
    (EditOp.SET_DURATION, {"duration_beats": "1/2"}),
    (EditOp.SET_ACCIDENTAL, {"accidental": "#"}),
    (EditOp.INSERT_EVENT, {"kind": "note", "pitch": "G4", "duration_beats": "1"}),
    (EditOp.DELETE_EVENT, None),
    (EditOp.SET_CLEF, {"sign": "F", "line": 4}),
    (EditOp.SET_KEY, {"fifths": -2}),
]


@pytest.mark.parametrize(("op", "after"), VALID_EDITS)
def test_undo_restores_exact_state_when_edit_was_sent_without_before(
    op: EditOp, after: dict[str, Any] | None
) -> None:
    session_repo, edit_repo = _repos()
    _append(session_repo, edit_repo, op, after=after)
    result = undo_edit(
        "s1", session_repository=session_repo, edit_repository=edit_repo, current_user=USER
    )
    assert result.current_score == _score().to_primitive()
    assert materialize(_score(), edit_repo.list_events("s1")) == _score()


def test_undo_rejects_legacy_edit_without_complete_before() -> None:
    session_repo, edit_repo = _repos()
    legacy = EditEvent(
        id="legacy-1",
        document_id="d1",
        seq=1,
        anchor=NOTE,
        op=EditOp.SET_PITCH,
        author=USER.username,
        created_at=datetime.now(UTC),
        before=None,
        after={"pitch": "E4"},
    )
    edit_repo.append("s1", legacy)
    with pytest.raises(InvalidEdit, match="estado previo"):
        undo_edit(
            "s1", session_repository=session_repo, edit_repository=edit_repo, current_user=USER
        )
    assert edit_repo.list_events("s1") == (legacy,)
