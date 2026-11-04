"""`append_edit` y `undo_edit` con la figura de un acorde (ADR-0049, #243, D61)."""

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
OP = EditOp.SET_CHORD_DURATION


def _anchor(event_index: int = 0) -> Anchor:
    return Anchor(part=0, staff=0, measure=1, voice=0, event_index=event_index, staff_id="s0")


def _note(pitch: str, beats: Fraction, is_chord: bool = False) -> Event:
    return Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=beats, is_chord=is_chord)


def _score() -> ScoreIR:
    # Un acorde de Do mayor en blancas y una blanca: un compás de 4/4 lleno.
    events = (
        _note("C4", Fraction(2)),
        _note("E4", Fraction(2), is_chord=True),
        _note("G4", Fraction(2), is_chord=True),
        _note("D4", Fraction(2)),
    )
    measure = Measure(number=1, events=events, time_signature=TimeSignature(4, 4))
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
    anchor: Anchor,
    after: dict[str, Any] | None,
    before: dict[str, Any] | None = None,
) -> EditEvent:
    session_repo, edit_repo = repos
    events = edit_repo.list_events("s1")
    return append_edit(
        "s1",
        anchor=anchor,
        op=OP,
        base_seq=events[-1].seq if events else 0,
        before=before,
        after=after,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=USER,
    )


def _durations(score: ScoreIR) -> list[Fraction | None]:
    return [e.duration_beats for e in score.parts[0].staves[0].measures[0].events]


def test_the_chord_figure_is_one_edit_and_one_undo() -> None:
    repos = _repos()
    edit = _append(repos, _anchor(), {"durations": ["1", "1", "1"]})
    assert edit.before == {"durations": ["2", "2", "2"]}
    assert len(repos[1].list_events("s1")) == 1
    current = materialize(_score(), repos[1].list_events("s1"))
    assert _durations(current) == [1, 1, 1, 2]
    result = undo_edit(
        "s1", session_repository=repos[0], edit_repository=repos[1], current_user=USER
    )
    assert result.current_score == _score().to_primitive()


def test_client_before_must_match_the_server_snapshot() -> None:
    repos = _repos()
    with pytest.raises(InvalidEdit, match="no coincide"):
        _append(repos, _anchor(), {"durations": ["1"] * 3}, before={"durations": ["1"] * 3})
    # La grafía de las figuras no cuenta («2», «2/1», «2.0»).
    _append(repos, _anchor(), {"durations": ["1"] * 3}, before={"durations": ["2", "2/1", "2.0"]})


@pytest.mark.parametrize(
    "anchor, after",
    [
        (_anchor(), {"durations": ["1"] * 2}),
        (_anchor(), {"durations": ["1", "1", "1/2"]}),
        (_anchor(1), {"durations": ["1"] * 2}),
        (_anchor(3), {"durations": ["1"]}),
        (_anchor(), {"duration_beats": "1"}),
    ],
)
def test_invalid_chord_edits_are_rejected_without_persisting(
    anchor: Anchor, after: dict[str, Any]
) -> None:
    repos = _repos()
    with pytest.raises(InvalidEdit):
        _append(repos, anchor, after)
    assert not repos[1].list_events("s1")


def test_a_suggestion_of_a_chord_figure_matches_its_equivalent_edit() -> None:
    """Aplicar una sugerencia compara su `after` normalizado (ADR-0036 §5)."""
    from cadenza.application.suggestions import same_after

    assert same_after(OP, {"durations": ["1/2", "1/2"]}, {"durations": ["0.5", "2/4"]})
    assert not same_after(OP, {"durations": ["1/2", "1/2"]}, {"durations": ["1", "1"]})
