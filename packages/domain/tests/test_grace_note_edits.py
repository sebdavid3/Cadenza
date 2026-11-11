"""Escribir notas de adorno desde la vista (#404, enmienda de ADR-0028).

Una nota de adorno es una nota de duración 0. `InsertEvent` y `SetDuration` admiten esa
duración solo en una nota visible, sin ligadura de prolongación y fuera de un acorde; deshacer
devuelve el estado exacto.
"""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction
from typing import Any

import pytest
from cadenza.domain import (
    Anchor,
    Clef,
    EditEvent,
    EditOp,
    Event,
    EventKind,
    InvalidEditPayload,
    KeySignature,
    Measure,
    Part,
    ScoreIR,
    Staff,
    Tie,
    TimeSignature,
    apply_edit,
    create_inverse_edit,
    snapshot_before,
    validate_after,
)
from cadenza.domain.duration_rules import check_duration


def _note(pitch: str, beats: str = "1", **extra: Any) -> Event:
    return Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=Fraction(beats), **extra)


def _score() -> ScoreIR:
    """Compás de 4/4: Do4 negra, un acorde Mi4-Sol4 de negra, Re4 ligada, un silencio de negra
    y un hueco de negra; y una nota de adorno La4 delante de Sol4 blanca."""

    first = Measure(
        number=1,
        events=(
            _note("C4"),
            _note("E4"),
            _note("G4", is_chord=True),
            _note("D4", tie=Tie.START),
            Event(kind=EventKind.REST, duration_beats=Fraction(1)),
        ),
        time_signature=TimeSignature(4, 4),
        clef=Clef.treble(),
        key_signature=KeySignature(fifths=0),
    )
    second = Measure(
        number=2,
        events=(
            _note("D4", tie=Tie.STOP),
            _note("A4", "0"),
            _note("G4", "2"),
            Event(kind=EventKind.REST, duration_beats=Fraction(1), hidden=True),
        ),
    )
    return ScoreIR(parts=(Part(id="p0", staves=(Staff(id="s0", measures=(first, second)),)),))


def _anchor(measure: int, event_index: int) -> Anchor:
    return Anchor(part=0, staff=0, measure=measure, voice=0, event_index=event_index, staff_id="s0")


PLAIN = _anchor(1, 0)  # Do4, una nota sola
CHORD_HEAD = _anchor(1, 1)  # Mi4, primera nota del acorde
CHORD_MEMBER = _anchor(1, 2)  # Sol4, nota del acorde
TIED = _anchor(1, 3)  # Re4 con ligadura
REST = _anchor(1, 4)
GRACE = _anchor(2, 1)  # La4 de adorno
AFTER_GRACE = _anchor(2, 2)  # Sol4, la nota que adorna
HIDDEN = _anchor(2, 3)


def _edit(
    op: EditOp, anchor: Anchor, after: dict[str, Any] | None, before: Any = None
) -> EditEvent:
    return EditEvent(
        id="e1",
        document_id="d1",
        seq=1,
        anchor=anchor,
        op=op,
        author="t",
        created_at=datetime.now(UTC),
        before=before,
        after=after,
    )


def _event(score: ScoreIR, anchor: Anchor) -> Event:
    measure = score.parts[0].staves[0].measures[anchor.measure - 1]
    return measure.events[anchor.event_index]


def _apply_and_undo(op: EditOp, anchor: Anchor, after: dict[str, Any]) -> tuple[ScoreIR, ScoreIR]:
    score = _score()
    validate_after(score, anchor, op, after)
    edit = _edit(op, anchor, after, snapshot_before(score, anchor, op, after))
    edited = apply_edit(score, edit)
    inverse = create_inverse_edit(edit, id="e2", seq=2, author="t", created_at=datetime.now(UTC))
    return edited, apply_edit(edited, inverse)


# --- La duración 0 solo con permiso explícito ---------------------------------------------


def test_check_duration_still_rejects_zero_unless_grace_is_allowed() -> None:
    with pytest.raises(InvalidEditPayload):
        check_duration(0)
    assert check_duration("0", allow_grace=True) == 0
    assert check_duration("1/2", allow_grace=True) == Fraction(1, 2)
    with pytest.raises(InvalidEditPayload):
        check_duration("-1/2", allow_grace=True)


# --- Convertir una nota en nota de adorno y deshacerlo ------------------------------------


@pytest.mark.parametrize("zero", [0, "0", "0/1"])
def test_a_plain_note_becomes_a_grace_note(zero: object) -> None:
    edited, undone = _apply_and_undo(EditOp.SET_DURATION, PLAIN, {"duration_beats": zero})
    assert _event(edited, PLAIN).duration_beats == 0
    assert _event(edited, PLAIN).pitch == "C4"
    assert undone == _score()


def test_a_grace_note_becomes_a_plain_note_and_back() -> None:
    edited, undone = _apply_and_undo(EditOp.SET_DURATION, GRACE, {"duration_beats": "1/2"})
    assert _event(edited, GRACE).duration_beats == Fraction(1, 2)
    assert undone == _score()


@pytest.mark.parametrize(
    ("anchor", "reason"),
    [
        (REST, "nota"),
        (HIDDEN, "nota"),
        (CHORD_HEAD, "acorde"),
        (CHORD_MEMBER, "acorde"),
        (TIED, "ligadura"),
    ],
)
def test_only_a_lone_untied_note_becomes_a_grace_note(anchor: Anchor, reason: str) -> None:
    with pytest.raises(InvalidEditPayload, match=reason):
        validate_after(_score(), anchor, EditOp.SET_DURATION, {"duration_beats": 0})


def test_a_grace_note_that_is_already_one_does_not_change() -> None:
    with pytest.raises(InvalidEditPayload, match="ya es"):
        validate_after(_score(), GRACE, EditOp.SET_DURATION, {"duration_beats": "0"})


# --- Insertar una nota de adorno ----------------------------------------------------------


def test_a_grace_note_is_inserted_before_a_note_and_undone() -> None:
    after = {"kind": "note", "pitch": "B4", "duration_beats": "0"}
    edited, undone = _apply_and_undo(EditOp.INSERT_EVENT, AFTER_GRACE, after)
    inserted = _event(edited, AFTER_GRACE)
    assert (inserted.pitch, inserted.duration_beats) == ("B4", Fraction(0))
    assert _event(edited, _anchor(2, 3)).pitch == "G4"
    assert undone == _score()


@pytest.mark.parametrize(
    ("after", "reason"),
    [
        ({"kind": "rest", "duration_beats": 0}, "nota"),
        ({"kind": "rest", "duration_beats": "0", "hidden": True}, "nota"),
        ({"kind": "note", "pitch": "B4", "duration_beats": 0, "tie": "start"}, "ligadura"),
    ],
)
def test_a_grace_insertion_is_a_note_without_tie(after: dict[str, Any], reason: str) -> None:
    with pytest.raises(InvalidEditPayload, match=reason):
        validate_after(_score(), AFTER_GRACE, EditOp.INSERT_EVENT, after)


def test_a_grace_note_does_not_join_a_chord() -> None:
    after = {"kind": "note", "pitch": "B4", "duration_beats": 0, "is_chord": True}
    with pytest.raises(InvalidEditPayload, match="acorde"):
        validate_after(_score(), _anchor(1, 1), EditOp.INSERT_EVENT, after)


def test_a_note_does_not_join_a_grace_note_as_a_chord() -> None:
    after = {"kind": "note", "pitch": "C5", "duration_beats": "1/2", "is_chord": True}
    with pytest.raises(InvalidEditPayload, match="adorno"):
        validate_after(_score(), AFTER_GRACE, EditOp.INSERT_EVENT, after)


# --- Lo vecino también trata como adorno la duración 0 (revisión de #404) -----------------


def _voice(*events: Event) -> ScoreIR:
    measure = Measure(
        number=1,
        events=events,
        time_signature=TimeSignature(4, 4),
        clef=Clef.treble(),
        key_signature=KeySignature(fifths=0),
    )
    following = Measure(number=2, events=(_note("A4", "4", tie=Tie.STOP),))
    return ScoreIR(parts=(Part(id="p0", staves=(Staff(id="s0", measures=(measure, following)),)),))


@pytest.mark.parametrize("grace", [None, "0"])
def test_a_tuplet_skips_a_grace_note_of_duration_zero(grace: str | None) -> None:
    score = _voice(_note("C4", "1/2"), _note("D4", "0"), _note("E4", "1/2"), _note("F4", "1/2"))
    after = {"durations": ["1/3", grace, "1/3", "1/3"]}
    validate_after(score, _anchor(1, 0), EditOp.SET_TUPLET, after)
    with pytest.raises(InvalidEditPayload, match="adorno"):
        validate_after(
            score, _anchor(1, 0), EditOp.SET_TUPLET, {"durations": ["1/3", "1/3", "1/3", "1/3"]}
        )


def test_a_grace_note_of_duration_zero_is_not_tied_and_ties_skip_it() -> None:
    score = _voice(_note("C4", "2"), _note("A4", "0"), _note("A4", "2", tie=Tie.START))
    with pytest.raises(InvalidEditPayload, match="adorno"):
        validate_after(
            score,
            _anchor(1, 1),
            EditOp.SET_TIE,
            {"tie": "start", "next": {"measure": 1, "voice": 0, "event_index": 2, "tie": "stop"}},
        )
    # Lo que sigue a Do4 es el La4 que ocupa tiempo, no su nota de adorno (ni ella cuenta como
    # lo último de la voz).
    from cadenza.domain.tie_edits import following

    staff = score.parts[0].staves[0]
    assert following(staff, 0, 0, 0) == [(1, 0, 2)]


def test_a_note_inserted_before_an_orphan_chord_note_is_refused() -> None:
    score = _voice(
        Event(kind=EventKind.REST, duration_beats=Fraction(1)),
        _note("E4", "1", is_chord=True),
    )
    for duration in ("0", "1"):
        with pytest.raises(InvalidEditPayload, match="is_chord"):
            validate_after(
                score,
                _anchor(1, 1),
                EditOp.INSERT_EVENT,
                {"kind": "note", "pitch": "C4", "duration_beats": duration},
            )
    validate_after(score, _anchor(1, 1), EditOp.INSERT_EVENT, {"kind": "rest", "duration_beats": 1})


def test_a_grace_note_of_null_duration_is_already_one() -> None:
    score = _voice(Event(kind=EventKind.NOTE, pitch="A4", duration_beats=None), _note("G4", "4"))
    with pytest.raises(InvalidEditPayload, match="ya es"):
        validate_after(score, _anchor(1, 0), EditOp.SET_DURATION, {"duration_beats": 0})
