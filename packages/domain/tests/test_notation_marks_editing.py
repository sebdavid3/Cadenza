"""Marcas de notación al editar y al deshacer (ADR-0031, ADR-0017, #213)."""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction
from typing import Any

import pytest
from cadenza.domain import (
    Anchor,
    Articulation,
    Clef,
    Dynamic,
    DynamicMark,
    EditEvent,
    EditOp,
    Event,
    EventKind,
    InvalidEditPayload,
    KeySignature,
    Measure,
    Part,
    ScoreIR,
    Slur,
    SlurType,
    Staff,
    TimeSignature,
    Wedge,
    WedgeType,
    apply_edit,
    create_inverse_edit,
    has_complete_before,
    materialize,
    snapshot_before,
    validate_after,
)

STAFF_ID = "part-0-staff-0"
DYNAMICS = (Dynamic(DynamicMark.P, Fraction(0)), Dynamic(DynamicMark.SFZ, Fraction(2)))
WEDGES = (
    Wedge(WedgeType.CRESCENDO, 1, Fraction(1, 2)),
    Wedge(WedgeType.STOP, 1, Fraction(3)),
)


def _score() -> ScoreIR:
    events = (
        Event(
            kind=EventKind.NOTE,
            pitch="C5",
            duration_beats=Fraction(1),
            articulations=(Articulation.STACCATO, Articulation.ACCENT),
            slurs=(Slur(SlurType.START, 1),),
        ),
        Event(
            kind=EventKind.NOTE,
            pitch="D5",
            duration_beats=Fraction(1),
            articulations=(Articulation.MARCATO,),
            fermata=True,
        ),
        Event(
            kind=EventKind.NOTE,
            pitch="E5",
            duration_beats=Fraction(2),
            slurs=(Slur(SlurType.STOP, 1),),
        ),
    )
    measure = Measure(
        number=1,
        events=events,
        time_signature=TimeSignature(4, 4),
        clef=Clef.treble(),
        key_signature=KeySignature(fifths=0),
        dynamics=DYNAMICS,
        wedges=WEDGES,
    )
    return ScoreIR(parts=(Part(id="part-0", staves=(Staff(id=STAFF_ID, measures=(measure,)),)),))


def _anchor(event_index: int) -> Anchor:
    return Anchor(part=0, staff=0, measure=1, voice=0, event_index=event_index, staff_id=STAFF_ID)


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


def _measure(score: ScoreIR) -> Measure:
    return score.parts[0].staves[0].measures[0]


@pytest.mark.parametrize(
    ("op", "after"),
    [
        (EditOp.SET_PITCH, {"pitch": "G5"}),
        (EditOp.SET_DURATION, {"duration_beats": "1/2"}),
        (EditOp.SET_ACCIDENTAL, {"accidental": "#"}),
    ],
)
def test_value_edits_keep_the_event_marks(op: EditOp, after: dict[str, Any]) -> None:
    score = _score()
    validate_after(score, _anchor(0), op, after)
    edited = _events(apply_edit(score, _edit(op, 0, after=after)))[0]
    assert edited.articulations == (Articulation.STACCATO, Articulation.ACCENT)
    assert edited.slurs == (Slur(SlurType.START, 1),)


@pytest.mark.parametrize(
    ("op", "after"),
    [
        (EditOp.SET_CLEF, {"sign": "F", "line": 4}),
        (EditOp.SET_KEY, {"fifths": -2}),
    ],
)
def test_measure_edits_keep_dynamics_and_wedges(op: EditOp, after: dict[str, Any]) -> None:
    measure = _measure(apply_edit(_score(), _edit(op, 0, after=after)))
    assert measure.dynamics == DYNAMICS
    assert measure.wedges == WEDGES


def test_insert_and_delete_do_not_move_measure_marks() -> None:
    """Las dinámicas y los reguladores son posiciones del compás: insertar o borrar no los mueve."""

    score = _score()
    insert = _edit(EditOp.INSERT_EVENT, 0, after={"kind": "rest", "duration_beats": "1"})
    inserted = apply_edit(score, insert)
    assert _measure(inserted).dynamics == DYNAMICS
    assert _measure(inserted).wedges == WEDGES
    # Las marcas de cada nota viajan con ella al desplazarse su `event_index`.
    assert _events(inserted)[1] == _events(score)[0]

    deleted = apply_edit(score, _edit(EditOp.DELETE_EVENT, 1, before=None))
    assert _measure(deleted).dynamics == DYNAMICS
    assert _measure(deleted).wedges == WEDGES


def test_delete_snapshot_keeps_the_marks() -> None:
    score = _score()
    before = snapshot_before(score, _anchor(1), EditOp.DELETE_EVENT)
    assert before is not None
    assert before["articulations"] == ["marcato"]
    assert before["fermata"] is True

    before_first = snapshot_before(score, _anchor(0), EditOp.DELETE_EVENT)
    assert before_first is not None
    assert before_first["articulations"] == ["staccato", "accent"]
    assert before_first["slurs"] == [{"type": "start", "number": 1}]


def test_delete_snapshot_without_marks_has_the_same_keys_as_before() -> None:
    score = apply_edit(
        _score(), _edit(EditOp.INSERT_EVENT, 0, after={"kind": "rest", "duration_beats": "1"})
    )
    before = snapshot_before(score, _anchor(0), EditOp.DELETE_EVENT)
    assert before is not None
    assert set(before) == {
        "kind",
        "pitch",
        "duration_beats",
        "tie",
        "is_chord",
        "bbox",
        "confidence",
    }


@pytest.mark.parametrize("event_index", [0, 1, 2])
def test_undoing_a_delete_restores_the_event_with_its_exact_marks(event_index: int) -> None:
    score = _score()
    before = snapshot_before(score, _anchor(event_index), EditOp.DELETE_EVENT)
    delete = _edit(EditOp.DELETE_EVENT, event_index, before=before)
    assert has_complete_before(delete)
    inverse = create_inverse_edit(
        delete, id="inv", seq=2, author="ana", created_at=datetime(2026, 10, 24, tzinfo=UTC)
    )
    assert materialize(score, [delete, inverse]) == score


def test_delete_snapshot_saved_before_213_is_still_complete() -> None:
    """Una instantánea anterior a #213 no tiene marcas: se deshace igual, sin marcas que poner."""

    delete = _edit(
        EditOp.DELETE_EVENT,
        0,
        before={"kind": "note", "pitch": "C5", "duration_beats": "1"},
    )
    assert has_complete_before(delete)
    inverse = create_inverse_edit(
        delete, id="inv", seq=2, author="ana", created_at=datetime(2026, 10, 24, tzinfo=UTC)
    )
    restored = _events(materialize(_score(), [delete, inverse]))[0]
    assert restored.articulations == ()
    assert restored.slurs == ()


def test_deleting_a_slur_start_leaves_its_stop_orphaned_until_undone() -> None:
    """Borrar una nota no toca otras: el fin de su ligadura queda huérfano (ADR-0031)."""

    score = _score()
    before = snapshot_before(score, _anchor(0), EditOp.DELETE_EVENT)
    delete = _edit(EditOp.DELETE_EVENT, 0, before=before)
    deleted = apply_edit(score, delete)
    assert [e.slurs for e in _events(deleted)] == [(), (Slur(SlurType.STOP, 1),)]

    inverse = create_inverse_edit(
        delete, id="inv", seq=2, author="ana", created_at=datetime(2026, 10, 24, tzinfo=UTC)
    )
    assert apply_edit(deleted, inverse) == score


def test_insert_event_accepts_marks() -> None:
    score = _score()
    after = {
        "kind": "note",
        "pitch": "A4",
        "duration_beats": "1/2",
        "articulations": ["tenuto", "staccato"],
        "fermata": True,
        "slurs": [{"type": "start", "number": 7}],
    }
    validate_after(score, _anchor(3), EditOp.INSERT_EVENT, after)
    inserted = _events(apply_edit(score, _edit(EditOp.INSERT_EVENT, 3, after=after)))[3]
    assert inserted.articulations == (Articulation.STACCATO, Articulation.TENUTO)
    assert inserted.fermata is True
    assert inserted.slurs == (Slur(SlurType.START, 7),)


def test_insert_event_accepts_a_rest_with_a_fermata_and_empty_marks() -> None:
    score = _score()
    rest = {
        "kind": "rest",
        "duration_beats": "1",
        "fermata": True,
        "articulations": [],
        "slurs": [],
    }
    validate_after(score, _anchor(0), EditOp.INSERT_EVENT, rest)
    inserted = _events(apply_edit(score, _edit(EditOp.INSERT_EVENT, 0, after=rest)))[0]
    assert inserted.fermata is True
    assert inserted.articulations == ()


@pytest.mark.parametrize(
    "marks",
    [
        {"articulations": "staccato"},
        {"articulations": ["legato"]},
        {"articulations": [1]},
        {"fermata": "yes"},
        {"fermata": 1},
        {"slurs": {"type": "start", "number": 1}},
        {"slurs": [{"type": "begin", "number": 1}]},
        {"slurs": [{"type": "start", "number": 0}]},
        {"slurs": [{"type": "start", "number": True}]},
        {"slurs": [{"type": "start"}]},
        {"slurs": [{"type": "start", "number": 1, "placement": "above"}]},
        {"slurs": ["start"]},
    ],
)
def test_insert_event_rejects_invalid_marks(marks: dict[str, Any]) -> None:
    after = {"kind": "note", "pitch": "A4", "duration_beats": "1", **marks}
    with pytest.raises(InvalidEditPayload):
        validate_after(_score(), _anchor(0), EditOp.INSERT_EVENT, after)


def test_insert_event_rejects_a_slur_end_already_in_the_part() -> None:
    """El `number` identifica la ligadura en su parte: no se repite un extremo (ADR-0031)."""

    after = {
        "kind": "note",
        "pitch": "A4",
        "duration_beats": "1",
        "slurs": [{"type": "start", "number": 1}],
    }
    with pytest.raises(InvalidEditPayload, match="start 1"):
        validate_after(_score(), _anchor(3), EditOp.INSERT_EVENT, after)
    validate_after(
        _score(),
        _anchor(3),
        EditOp.INSERT_EVENT,
        {**after, "slurs": [{"type": "start", "number": 2}]},
    )


def test_marks_given_as_lists_are_normalized_to_tuples() -> None:
    # Se pasan listas a propósito, contra el tipo declarado: lo que se comprueba es que el
    # evento las normaliza a tuplas y sigue siendo hashable.
    event = Event(kind=EventKind.NOTE, pitch="C4", articulations=[], slurs=[])  # type: ignore[arg-type]
    assert event.articulations == () and event.slurs == ()
    assert hash(event) == hash(Event(kind=EventKind.NOTE, pitch="C4"))
    assert Event.from_primitive({"kind": "note", "voice": 0, "fermata": "false"}).fermata is False
