"""`append_edit` y `undo_edit` con el compás y los tresillos (ADR-0044, #236)."""

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


def _anchor(measure: int = 1, event_index: int = 0) -> Anchor:
    return Anchor(part=0, staff=0, measure=measure, voice=0, event_index=event_index, staff_id="s0")


def _score() -> ScoreIR:
    eighths = tuple(
        Event(kind=EventKind.NOTE, pitch="C5", duration_beats=Fraction(1, 2)) for _ in range(12)
    )
    measures = (
        Measure(number=1, events=eighths, time_signature=TimeSignature(4, 4)),
        Measure(
            number=2,
            events=(Event(kind=EventKind.NOTE, pitch="D5", duration_beats=Fraction(4)),),
            time_signature=TimeSignature(4, 4),
        ),
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


def _append(
    repos: tuple[InMemorySessionRepository, InMemoryEditEventRepository],
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


def test_twelve_eighths_to_triplets_is_one_edit_and_one_undo() -> None:
    repos = _repos()
    edit = _append(repos, EditOp.SET_TUPLET, _anchor(), {"durations": ["1/3"] * 12})
    assert edit.before == {"durations": ["1/2"] * 12}
    current = materialize(_score(), repos[1].list_events("s1"))
    assert {e.duration_beats for e in current.parts[0].staves[0].measures[0].events} == {
        Fraction(1, 3)
    }
    result = undo_edit(
        "s1", session_repository=repos[0], edit_repository=repos[1], current_user=USER
    )
    assert result.current_score == _score().to_primitive()


def test_set_time_with_symbol_is_saved_and_undone_exactly() -> None:
    repos = _repos()
    after = {"time_signature": {"beats": 4, "beat_type": 4, "symbol": "common"}}
    edit = _append(repos, EditOp.SET_TIME, _anchor(), after)
    assert edit.before == {"time_signature": {"beats": 4, "beat_type": 4}, "measures": 2}
    current = materialize(_score(), repos[1].list_events("s1"))
    assert [
        m.time_signature.symbol for m in current.parts[0].staves[0].measures if m.time_signature
    ] == [
        "common",
        "common",
    ]
    result = undo_edit(
        "s1", session_repository=repos[0], edit_repository=repos[1], current_user=USER
    )
    assert result.current_score == _score().to_primitive()


def test_client_before_must_match_the_server_snapshot() -> None:
    repos = _repos()
    # Coincide: la indicación sin la longitud del tramo, que calcula el servidor.
    _append(
        repos,
        EditOp.SET_TIME,
        _anchor(),
        {"time_signature": {"beats": 3, "beat_type": 4}},
        before={"time_signature": {"beats": 4, "beat_type": 4}},
    )
    # No coincide: ya es 3/4, y C no es 3/4 ni se escribe igual que 4/4.
    with pytest.raises(InvalidEdit, match="no coincide"):
        _append(
            repos,
            EditOp.SET_TIME,
            _anchor(),
            {"time_signature": {"beats": 2, "beat_type": 4}},
            before={"time_signature": {"beats": 4, "beat_type": 4, "symbol": "common"}},
        )
    with pytest.raises(InvalidEdit, match="no coincide"):
        _append(
            repos,
            EditOp.SET_TUPLET,
            _anchor(),
            {"durations": ["1/3"] * 3},
            before={"durations": ["1/4"] * 3},
        )
    _append(
        repos,
        EditOp.SET_TUPLET,
        _anchor(),
        {"durations": ["1/3"] * 3},
        before={"durations": ["0.5", "1/2", "2/4"]},
    )
    # Un número que no cabe en un entero (1e999 en JSON) es un 422, no un 500.
    with pytest.raises(InvalidEdit, match="no válido"):
        _append(
            repos,
            EditOp.SET_TIME,
            _anchor(),
            {"time_signature": {"beats": 2, "beat_type": 4}},
            before={"time_signature": {"beats": float("inf"), "beat_type": 4}},
        )


@pytest.mark.parametrize(
    "op, after",
    [
        (EditOp.SET_TIME, {"time_signature": {"beats": 3, "beat_type": 3}}),
        (EditOp.SET_TIME, {"time_signature": None}),
        (EditOp.SET_TUPLET, {"durations": ["1/4"] * 12}),
        (EditOp.SET_TUPLET, {"durations": ["1/3"] * 13}),
    ],
)
def test_invalid_meter_edits_are_rejected_without_persisting(
    op: EditOp, after: dict[str, Any]
) -> None:
    repos = _repos()
    with pytest.raises(InvalidEdit):
        _append(repos, op, _anchor(), after)
    assert not repos[1].list_events("s1")


def test_a_suggestion_of_set_time_or_set_tuplet_matches_its_equivalent_edit() -> None:
    """Aplicar una sugerencia compara su `after` normalizado (ADR-0036 §5)."""
    from cadenza.application.suggestions import same_after

    proposed = {"time_signature": {"beats": 4, "beat_type": 4}}
    sent = {"time_signature": {"beats": 4, "beat_type": 4, "symbol": None}}
    assert same_after(EditOp.SET_TIME, proposed, sent)
    common = {"time_signature": {"beats": 4, "beat_type": 4, "symbol": "common"}}
    assert not same_after(EditOp.SET_TIME, proposed, common)
    # El candidato de time.signature es de una parte (#326): `all_parts: false` es lo mismo, y
    # todas las partes, otra edición.
    assert same_after(EditOp.SET_TIME, proposed, {**sent, "all_parts": False})
    assert not same_after(EditOp.SET_TIME, proposed, {**sent, "all_parts": True})
    assert same_after(EditOp.SET_TUPLET, {"durations": ["1/3", None]}, {"durations": ["2/6", None]})
