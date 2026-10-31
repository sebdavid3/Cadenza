"""`append_edit` y `undo_edit` conservan las marcas de notación (ADR-0031, ADR-0017, #213)."""

from __future__ import annotations

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
    Articulation,
    Dynamic,
    DynamicMark,
    EditEvent,
    EditOp,
    Event,
    EventKind,
    Measure,
    Part,
    ScoreIR,
    Slur,
    SlurType,
    Staff,
    TimeSignature,
    Wedge,
    WedgeType,
    materialize,
)

USER = User(id="u1", username="transcriptor1", password_hash="h", role=Role.TRANSCRIPTOR)


def _anchor(event_index: int) -> Anchor:
    return Anchor(part=0, staff=0, measure=1, voice=0, event_index=event_index, staff_id="s0")


def _score() -> ScoreIR:
    measure = Measure(
        number=1,
        events=(
            Event(
                kind=EventKind.NOTE,
                pitch="C5",
                duration_beats=Fraction(1),
                articulations=(Articulation.STACCATO, Articulation.TENUTO),
                slurs=(Slur(SlurType.START, 1),),
            ),
            Event(
                kind=EventKind.NOTE,
                pitch="D5",
                duration_beats=Fraction(1),
                fermata=True,
                slurs=(Slur(SlurType.STOP, 1),),
            ),
            Event(kind=EventKind.REST, duration_beats=Fraction(2), fermata=True),
        ),
        time_signature=TimeSignature(4, 4),
        dynamics=(Dynamic(DynamicMark.FP, Fraction(0)),),
        wedges=(
            Wedge(WedgeType.DIMINUENDO, 1, Fraction(1)),
            Wedge(WedgeType.STOP, 1, Fraction(2)),
        ),
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
    repos: tuple[InMemorySessionRepository, InMemoryEditEventRepository],
    op: EditOp,
    event_index: int,
    after: dict[str, Any] | None,
) -> EditEvent:
    session_repo, edit_repo = repos
    events = edit_repo.list_events("s1")
    return append_edit(
        "s1",
        anchor=_anchor(event_index),
        op=op,
        base_seq=events[-1].seq if events else 0,
        after=after,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=USER,
    )


@pytest.mark.parametrize("event_index", [0, 1, 2])
def test_undoing_a_delete_restores_the_marks(event_index: int) -> None:
    repos = _repos()
    deleted = _append(repos, EditOp.DELETE_EVENT, event_index, None)
    assert deleted.before is not None
    assert "fermata" in deleted.before or "articulations" in deleted.before

    result = undo_edit(
        "s1", session_repository=repos[0], edit_repository=repos[1], current_user=USER
    )
    assert result.current_score == _score().to_primitive()
    assert materialize(_score(), repos[1].list_events("s1")) == _score()


def test_value_edits_keep_the_marks() -> None:
    repos = _repos()
    _append(repos, EditOp.SET_PITCH, 0, {"pitch": "E5"})
    _append(repos, EditOp.SET_DURATION, 0, {"duration_beats": "1/2"})
    _append(repos, EditOp.SET_ACCIDENTAL, 0, {"accidental": "b"})
    _append(repos, EditOp.SET_KEY, 0, {"fifths": 3})
    current = materialize(_score(), repos[1].list_events("s1"))
    measure = current.parts[0].staves[0].measures[0]
    assert measure.events[0].pitch == "Eb5"
    assert measure.events[0].articulations == (Articulation.STACCATO, Articulation.TENUTO)
    assert measure.events[0].slurs == (Slur(SlurType.START, 1),)
    assert measure.dynamics == _score().parts[0].staves[0].measures[0].dynamics
    assert measure.wedges == _score().parts[0].staves[0].measures[0].wedges


def test_insert_event_with_marks_is_validated_and_persisted() -> None:
    repos = _repos()
    inserted = _append(
        repos,
        EditOp.INSERT_EVENT,
        3,
        {"kind": "note", "pitch": "F5", "duration_beats": "1", "articulations": ["accent"]},
    )
    assert inserted.after is not None
    current = materialize(_score(), repos[1].list_events("s1"))
    assert current.parts[0].staves[0].measures[0].events[3].articulations == (Articulation.ACCENT,)

    with pytest.raises(InvalidEdit):
        _append(
            repos,
            EditOp.INSERT_EVENT,
            0,
            {"kind": "note", "pitch": "F5", "duration_beats": "1", "articulations": ["trill"]},
        )
    assert len(repos[1].list_events("s1")) == 1


# --- Añadir y quitar marcas (ADR-0039, #214) ----------------------------------------------


def _undo(repos: tuple[InMemorySessionRepository, InMemoryEditEventRepository]) -> None:
    session_repo, edit_repo = repos
    undo_edit(
        "s1",
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=USER,
        base_seq=edit_repo.list_events("s1")[-1].seq,
    )


def _current(repos: tuple[InMemorySessionRepository, InMemoryEditEventRepository]) -> ScoreIR:
    return materialize(_score(), repos[1].list_events("s1"))


MARK_EDITS: list[tuple[EditOp, int, dict[str, Any], dict[str, Any]]] = [
    (
        EditOp.SET_NOTE_MARKS,
        0,
        {"articulations": ["accent"], "fermata": True},
        {"articulations": ["staccato", "tenuto"], "fermata": False},
    ),
    (
        EditOp.SET_DYNAMIC,
        0,
        {"offset_beats": "3", "mark": "ff"},
        {"offset_beats": "3", "mark": None},
    ),
    (
        EditOp.SET_SLUR,
        0,
        {"number": 1, "start": None, "stop": None},
        {
            "number": 1,
            "start": {"staff": 0, "measure": 1, "voice": 0, "event_index": 0},
            "stop": {"staff": 0, "measure": 1, "voice": 0, "event_index": 1},
        },
    ),
    (
        EditOp.SET_WEDGE,
        0,
        {
            "number": 2,
            "start": {"staff": 0, "measure": 1, "offset_beats": "2", "type": "crescendo"},
            "stop": {"staff": 0, "measure": 1, "offset_beats": "4"},
        },
        {"number": 2, "start": None, "stop": None},
    ),
]


@pytest.mark.parametrize(("op", "event_index", "after", "before"), MARK_EDITS)
def test_mark_edits_are_saved_with_the_server_snapshot_and_undone_exactly(
    op: EditOp, event_index: int, after: dict[str, Any], before: dict[str, Any]
) -> None:
    repos = _repos()
    saved = _append(repos, op, event_index, after)
    assert saved.before == before
    assert _current(repos) != _score()

    _undo(repos)
    assert _current(repos) == _score()
    # Rehacer es volver a enviar la misma edición (ADR-0034): deja el mismo estado.
    redone = _append(repos, op, event_index, after)
    assert redone.before == before


def test_a_client_before_must_match_the_marks() -> None:
    session_repo, edit_repo = repos = _repos()
    after = {"articulations": ["accent"], "fermata": False}
    with pytest.raises(InvalidEdit):
        append_edit(
            "s1",
            anchor=_anchor(0),
            op=EditOp.SET_NOTE_MARKS,
            base_seq=0,
            before={"articulations": [], "fermata": False},
            after=after,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=USER,
        )
    with pytest.raises(InvalidEdit):
        append_edit(
            "s1",
            anchor=_anchor(0),
            op=EditOp.SET_NOTE_MARKS,
            base_seq=0,
            before={"articulations": ["staccato", "tenuto"], "fermata": 0},
            after=after,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=USER,
        )
    # El mismo estado en otro orden y con otra grafía de la posición sí coincide.
    append_edit(
        "s1",
        anchor=_anchor(0),
        op=EditOp.SET_NOTE_MARKS,
        base_seq=0,
        before={"articulations": ["tenuto", "staccato"], "fermata": False},
        after=after,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=USER,
    )
    append_edit(
        "s1",
        anchor=_anchor(0),
        op=EditOp.SET_DYNAMIC,
        base_seq=1,
        before={"offset_beats": "0/1", "mark": "fp"},
        after={"offset_beats": 0, "mark": "p"},
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=USER,
    )
    assert len(_current(repos).parts[0].staves[0].measures[0].dynamics) == 1


def test_a_dynamic_in_a_measure_without_events_in_the_voice_is_accepted() -> None:
    # Como la clave y la armadura, una dinámica es del compás: el ancla no necesita un evento.
    repos = _repos()
    session_repo, edit_repo = repos
    append_edit(
        "s1",
        anchor=Anchor(part=0, staff=0, measure=1, voice=3, event_index=0, staff_id="s0"),
        op=EditOp.SET_DYNAMIC,
        base_seq=0,
        before={"offset_beats": "1", "mark": None},
        after={"offset_beats": "1", "mark": "mp"},
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=USER,
    )


@pytest.mark.parametrize(
    ("op", "event_index", "after"),
    [
        (EditOp.SET_NOTE_MARKS, 2, {"articulations": ["accent"], "fermata": True}),
        (EditOp.SET_DYNAMIC, 0, {"offset_beats": "9", "mark": "p"}),
        (EditOp.SET_SLUR, 0, {"number": 1, "start": None}),
        (EditOp.SET_WEDGE, 0, {"number": 4, "start": None, "stop": None}),
    ],
)
def test_invalid_mark_edits_are_rejected_without_persisting(
    op: EditOp, event_index: int, after: dict[str, Any]
) -> None:
    repos = _repos()
    with pytest.raises(InvalidEdit):
        _append(repos, op, event_index, after)
    assert not repos[1].list_events("s1")
