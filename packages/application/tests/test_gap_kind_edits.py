"""`append_edit` y `undo_edit` con los huecos de una voz (ADR-0058, #317): escribir una nota en un
hueco, hacerlo visible o borrarlo es una edición que se valida, se guarda con su instantánea y se
deshace de un paso."""

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
    effort_class,
    undo_edit,
)
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
    materialize,
)

USER = User(id="u1", username="transcriptor1", password_hash="h", role=Role.TRANSCRIPTOR)
KIND = EditOp.SET_EVENT_KIND


def _anchor(event_index: int = 0, measure: int = 1, voice: int = 0) -> Anchor:
    return Anchor(
        part=0, staff=0, measure=measure, voice=voice, event_index=event_index, staff_id="s0"
    )


def _note(pitch: str, beats: str = "1", **kwargs: Any) -> Event:
    return Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=Fraction(beats), **kwargs)


def _gap(beats: str, voice: int = 0) -> Event:
    return Event(kind=EventKind.REST, duration_beats=Fraction(beats), hidden=True, voice=voice)


def _score() -> ScoreIR:
    # Compás 1 de la voz de TS-03 como lo importa HOMR: dos huecos de semicorchea.
    first = (
        _note("G#4", "3/4"),
        _gap("1/4"),
        _note("F#4", "1/2"),
        _note("D5", "3/4"),
        _gap("1/4"),
        _note("G#4", "1/4"),
        _note("G#4", "1/2"),
    )
    measures = (Measure(number=1, events=first, time_signature=TimeSignature(6, 8)),)
    return ScoreIR(parts=(Part(id="p0", staves=(Staff(id="s0", measures=measures),)),))


Repos = tuple[InMemorySessionRepository, InMemoryEditEventRepository]


def _repos() -> Repos:
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
    repos: Repos,
    op: EditOp,
    anchor: Anchor,
    after: dict[str, Any] | None,
    before: dict[str, Any] | None = None,
) -> EditEvent:
    session_repo, edit_repo = repos
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


def _undo_restores_the_original(repos: Repos) -> None:
    result = undo_edit(
        "s1", session_repository=repos[0], edit_repository=repos[1], current_user=USER
    )
    assert result.current_score == _score().to_primitive()


def _current(repos: Repos) -> tuple[Event, ...]:
    return materialize(_score(), repos[1].list_events("s1")).parts[0].staves[0].measures[0].events


NOTE: dict[str, Any] = {"kind": "note", "pitch": "F#4", "hidden": False}
GAP: dict[str, Any] = {"kind": "rest", "pitch": None, "hidden": True}


def test_a_note_in_a_gap_is_one_edit_and_one_undo() -> None:
    repos = _repos()
    edit = _append(repos, KIND, _anchor(1), NOTE)
    assert edit.before == GAP
    note = _current(repos)[1]
    assert (note.kind, note.pitch, note.duration_beats) == (EventKind.NOTE, "F#4", Fraction(1, 4))
    _undo_restores_the_original(repos)


def test_a_gap_made_visible_is_one_edit_and_one_undo() -> None:
    repos = _repos()
    _append(repos, KIND, _anchor(1), {"kind": "rest", "pitch": None, "hidden": False})
    rest = _current(repos)[1]
    assert (rest.kind, rest.hidden) == (EventKind.REST, False)
    _undo_restores_the_original(repos)


def test_a_deleted_gap_comes_back_hidden_on_undo() -> None:
    repos = _repos()
    _append(repos, EditOp.DELETE_EVENT, _anchor(4), None)
    assert [e.pitch for e in _current(repos)] == ["G#4", None, "F#4", "D5", "G#4", "G#4"]
    _undo_restores_the_original(repos)


def test_the_client_before_must_match_the_server_snapshot() -> None:
    repos = _repos()
    with pytest.raises(InvalidEdit, match="no coincide"):
        _append(repos, KIND, _anchor(1), NOTE, before={**GAP, "hidden": False})
    assert not repos[1].list_events("s1")
    _append(repos, KIND, _anchor(1), NOTE, before=dict(GAP))


@pytest.mark.parametrize(
    ("anchor", "after"),
    [
        # Una nota no es un hueco.
        (_anchor(0), {"kind": "rest", "pitch": None, "hidden": False}),
        # Un hueco que sigue siendo hueco no cambia nada.
        (_anchor(1), GAP),
        (_anchor(1), {"kind": "note", "pitch": "H4", "hidden": False}),
        (_anchor(1), {"kind": "note", "pitch": "F#4"}),
        (_anchor(9), NOTE),
    ],
)
def test_invalid_gap_edits_are_rejected_without_persisting(
    anchor: Anchor, after: dict[str, Any]
) -> None:
    repos = _repos()
    with pytest.raises(InvalidEdit):
        _append(repos, KIND, anchor, after)
    assert not repos[1].list_events("s1")


def test_a_gap_edit_counts_as_a_content_intervention() -> None:
    # Las métricas de esfuerzo siguen con tres clases (protocolo §3.4, ADR-0058).
    assert effort_class(KIND) == "content"
    assert {effort_class(op) for op in EditOp} == {"content", "mark", "meter"}
