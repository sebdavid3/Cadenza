"""`append_edit` y `undo_edit` con ligaduras de prolongación y notas de un acorde (ADR-0055,
#312, D61): cada orden es una edición que se valida, se guarda con su instantánea y se deshace de
un paso."""

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
    Articulation,
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


def _anchor(event_index: int = 0, measure: int = 1) -> Anchor:
    return Anchor(part=0, staff=0, measure=measure, voice=0, event_index=event_index, staff_id="s0")


def _note(pitch: str, beats: int = 1, **kwargs: Any) -> Event:
    return Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=Fraction(beats), **kwargs)


def _score() -> ScoreIR:
    # Compás 1: un acorde de Do mayor con acento, un Re y un Sol; compás 2: un Sol redonda.
    first = (
        _note("C4", articulations=(Articulation.ACCENT,)),
        _note("E4", is_chord=True),
        _note("G4", is_chord=True),
        _note("D4"),
        _note("G4", 2),
    )
    measures = (
        Measure(number=1, events=first, time_signature=TimeSignature(4, 4)),
        Measure(number=2, events=(_note("G4", 4),)),
    )
    return ScoreIR(parts=(Part(id="p0", staves=(Staff(id="s0", measures=measures),)),))


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


Repos = tuple[InMemorySessionRepository, InMemoryEditEventRepository]


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


def _current(repos: Repos) -> ScoreIR:
    return materialize(_score(), repos[1].list_events("s1"))


def _events(score: ScoreIR, measure: int = 1) -> tuple[Event, ...]:
    return score.parts[0].staves[0].measures[measure - 1].events


ACROSS: dict[str, Any] = {
    "tie": "start",
    "next": {"measure": 2, "voice": 0, "event_index": 0, "tie": "stop"},
}


def test_a_tie_across_the_barline_is_one_edit_and_one_undo() -> None:
    repos = _repos()
    edit = _append(repos, EditOp.SET_TIE, _anchor(4), ACROSS)
    assert edit.before == {
        "tie": None,
        "next": {"measure": 2, "voice": 0, "event_index": 0, "tie": None},
    }
    current = _current(repos)
    assert _events(current, 1)[4].tie is not None and _events(current, 2)[0].tie is not None
    _undo_restores_the_original(repos)


def test_the_client_before_of_a_tie_must_match_the_server_snapshot() -> None:
    repos = _repos()
    wrong = {"tie": "start", "next": {"measure": 2, "voice": 0, "event_index": 0, "tie": None}}
    with pytest.raises(InvalidEdit, match="no coincide"):
        _append(repos, EditOp.SET_TIE, _anchor(4), ACROSS, before=wrong)
    right = {"tie": None, "next": {"event_index": 0, "voice": 0, "measure": 2, "tie": None}}
    _append(repos, EditOp.SET_TIE, _anchor(4), ACROSS, before=right)


def test_a_note_added_to_a_chord_is_one_edit_and_one_undo() -> None:
    repos = _repos()
    after = {"kind": "note", "pitch": "B4", "duration_beats": "1", "is_chord": True}
    _append(repos, EditOp.INSERT_EVENT, _anchor(3), after)
    assert [e.pitch for e in _events(_current(repos))][:4] == ["C4", "E4", "G4", "B4"]
    _undo_restores_the_original(repos)


def test_the_first_note_of_a_chord_is_removed_in_one_edit_and_one_undo() -> None:
    repos = _repos()
    edit = _append(repos, EditOp.DELETE_EVENT, _anchor(0), {"keep_chord": True})
    assert edit.before is not None and "next_in_chord" in edit.before
    head = _events(_current(repos))[0]
    assert (head.pitch, head.is_chord, head.articulations) == ("E4", False, (Articulation.ACCENT,))
    _undo_restores_the_original(repos)


@pytest.mark.parametrize(
    ("op", "anchor", "after"),
    [
        # La primera nota de un acorde no se borra sin conservar el acorde.
        (EditOp.DELETE_EVENT, _anchor(0), None),
        (EditOp.DELETE_EVENT, _anchor(3), {"keep_chord": True}),
        # Un evento sin is_chord no parte un acorde; una nota de acorde va tras otra nota.
        (EditOp.INSERT_EVENT, _anchor(1), {"kind": "rest", "duration_beats": "1"}),
        (
            EditOp.INSERT_EVENT,
            _anchor(0),
            {"kind": "note", "pitch": "A3", "duration_beats": "1", "is_chord": True},
        ),
        # La ligadura une la nota con la siguiente de la misma altura.
        (EditOp.SET_TIE, _anchor(3), {**ACROSS, "next": {**ACROSS["next"], "measure": 1}}),
        (
            EditOp.SET_TIE,
            _anchor(0),
            {"tie": "start", "next": {"measure": 1, "voice": 0, "event_index": 3, "tie": "stop"}},
        ),
    ],
)
def test_invalid_tie_and_chord_edits_are_rejected_without_persisting(
    op: EditOp, anchor: Anchor, after: dict[str, Any] | None
) -> None:
    repos = _repos()
    with pytest.raises(InvalidEdit):
        _append(repos, op, anchor, after)
    assert not repos[1].list_events("s1")


def test_a_tie_counts_as_a_meter_intervention_and_chord_notes_as_content() -> None:
    # Las métricas de esfuerzo siguen con tres clases (protocolo §3.4, ADR-0055 §4).
    assert effort_class(EditOp.SET_TIE) == "meter"
    assert effort_class(EditOp.INSERT_EVENT) == "content"
    assert effort_class(EditOp.DELETE_EVENT) == "content"


def test_a_suggestion_of_a_tie_matches_its_equivalent_edit() -> None:
    from cadenza.application.suggestions import same_after

    assert same_after(EditOp.SET_TIE, ACROSS, dict(ACROSS))
    assert not same_after(EditOp.SET_TIE, ACROSS, {**ACROSS, "tie": None})
