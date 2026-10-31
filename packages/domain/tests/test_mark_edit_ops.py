"""Operaciones que añaden y quitan marcas de notación (ADR-0039, #214).

`SetNoteMarks` fija las articulaciones y el calderón de un evento; `SetDynamic`, la dinámica de
una posición del compás; `SetSlur` y `SetWedge` crean una ligadura de expresión o un regulador
con sus dos extremos, o los quitan. Las cuatro son de tipo «fijar»: `before` es la instantánea
del servidor y la compensatoria intercambia `before` y `after` (ADR-0007, ADR-0017).
"""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction
from typing import Any

import pytest
from cadenza.domain import (
    CONTENT_EDIT_OPS,
    MARK_EDIT_OPS,
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
    snapshot_before,
    translate_anchor,
    validate_after,
)

STAFF_ID = "part-0-staff-0"
NOW = datetime(2026, 10, 31, tzinfo=UTC)


def _note(pitch: str, beats: int | Fraction = 1, **kwargs: Any) -> Event:
    return Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=Fraction(beats), **kwargs)


def _score() -> ScoreIR:
    first = Measure(
        number=1,
        events=(
            _note("C5", articulations=(Articulation.STACCATO,), slurs=(Slur(SlurType.START, 1),)),
            _note("D5"),
            _note("E5", 2, slurs=(Slur(SlurType.STOP, 1),)),
        ),
        time_signature=TimeSignature(4, 4),
        clef=Clef.treble(),
        key_signature=KeySignature(fifths=0),
        dynamics=(Dynamic(DynamicMark.P, Fraction(0)),),
        wedges=(
            Wedge(WedgeType.CRESCENDO, 1, Fraction(1)),
            Wedge(WedgeType.STOP, 1, Fraction(2)),
        ),
    )
    second = Measure(
        number=2,
        events=(
            _note("F5"),
            Event(kind=EventKind.REST, duration_beats=Fraction(1)),
            _note("G5"),
            _note("B5", is_chord=True),
            Event(kind=EventKind.REST, duration_beats=Fraction(1), hidden=True),
        ),
    )
    return ScoreIR(
        parts=(Part(id="part-0", staves=(Staff(id=STAFF_ID, measures=(first, second)),)),)
    )


def _anchor(measure: int = 1, event_index: int = 0, voice: int = 0) -> Anchor:
    return Anchor(
        part=0, staff=0, measure=measure, voice=voice, event_index=event_index, staff_id=STAFF_ID
    )


def _edit(
    score: ScoreIR, op: EditOp, anchor: Anchor, after: dict[str, Any] | None, seq: int = 1
) -> EditEvent:
    """Una edición como la guarda el servidor: `after` validado y `before` su instantánea."""

    validate_after(score, anchor, op, after)
    return EditEvent(
        id=f"e{seq}",
        document_id="doc",
        seq=seq,
        anchor=anchor,
        op=op,
        author="ana",
        created_at=NOW,
        before=snapshot_before(score, anchor, op, after),
        after=after,
    )


def _undo(score: ScoreIR, edit: EditEvent) -> ScoreIR:
    inverse = create_inverse_edit(edit, id="u", seq=edit.seq + 1, author="ana", created_at=NOW)
    return apply_edit(score, inverse)


def _events(score: ScoreIR, measure: int) -> tuple[Event, ...]:
    return score.parts[0].staves[0].measures[measure - 1].events


def _measure(score: ScoreIR, measure: int) -> Measure:
    return score.parts[0].staves[0].measures[measure - 1]


def _slot(measure: int, event_index: int, voice: int = 0, staff: int = 0) -> dict[str, int]:
    return {"staff": staff, "measure": measure, "voice": voice, "event_index": event_index}


# --- Las operaciones y su política para el dataset y las métricas -------------------------


def test_mark_ops_are_a_separate_class_of_edit_op() -> None:
    assert {
        EditOp.SET_NOTE_MARKS,
        EditOp.SET_DYNAMIC,
        EditOp.SET_WEDGE,
        EditOp.SET_SLUR,
    } == MARK_EDIT_OPS
    assert CONTENT_EDIT_OPS.isdisjoint(MARK_EDIT_OPS)
    assert set(EditOp) == CONTENT_EDIT_OPS | MARK_EDIT_OPS
    # Las siete de contenido son las que derivan los experimentos (`len` de la cobertura de exp_02).
    assert len(CONTENT_EDIT_OPS) == 7


# --- SetNoteMarks ------------------------------------------------------------------------


def test_set_note_marks_sets_articulations_and_fermata_and_undoes_exactly() -> None:
    score = _score()
    after = {"articulations": ["tenuto", "accent"], "fermata": True}
    edit = _edit(score, EditOp.SET_NOTE_MARKS, _anchor(1, 0), after)

    assert edit.before == {"articulations": ["staccato"], "fermata": False}
    edited = apply_edit(score, edit)
    target = _events(edited, 1)[0]
    assert target.articulations == (Articulation.ACCENT, Articulation.TENUTO)
    assert target.fermata is True
    # Las demás marcas de la nota no cambian: la ligadura sigue.
    assert target.slurs == (Slur(SlurType.START, 1),)
    assert _undo(edited, edit) == score


def test_set_note_marks_can_clear_all_marks_and_a_rest_takes_a_fermata() -> None:
    score = _score()
    cleared = apply_edit(
        score,
        _edit(score, EditOp.SET_NOTE_MARKS, _anchor(1, 0), {"articulations": [], "fermata": False}),
    )
    assert _events(cleared, 1)[0].articulations == ()

    rest = _anchor(2, 1)
    edit = _edit(score, EditOp.SET_NOTE_MARKS, rest, {"articulations": [], "fermata": True})
    assert _events(apply_edit(score, edit), 2)[1].fermata is True


@pytest.mark.parametrize(
    ("anchor", "after"),
    [
        (_anchor(1, 0), {"articulations": ["staccato"]}),
        (_anchor(1, 0), {"articulations": ["staccato"], "fermata": False, "slurs": []}),
        (_anchor(1, 0), {"articulations": ["portato"], "fermata": False}),
        (_anchor(1, 0), {"articulations": ["accent", "accent"], "fermata": False}),
        (_anchor(1, 0), {"articulations": "accent", "fermata": False}),
        (_anchor(1, 0), {"articulations": [], "fermata": "yes"}),
        (_anchor(1, 0), None),
        # Un silencio solo lleva calderón; un silencio invisible, nada.
        (_anchor(2, 1), {"articulations": ["staccato"], "fermata": False}),
        (_anchor(2, 4), {"articulations": [], "fermata": True}),
        # En un acorde, las marcas van en su primera nota (ADR-0031).
        (_anchor(2, 3), {"articulations": ["accent"], "fermata": False}),
    ],
)
def test_set_note_marks_rejects_invalid_after(anchor: Anchor, after: dict[str, Any] | None) -> None:
    with pytest.raises(InvalidEditPayload):
        validate_after(_score(), anchor, EditOp.SET_NOTE_MARKS, after)


def test_set_note_marks_requires_an_existing_event() -> None:
    with pytest.raises(IndexError):
        validate_after(
            _score(), _anchor(1, 9), EditOp.SET_NOTE_MARKS, {"articulations": [], "fermata": False}
        )


# --- SetDynamic --------------------------------------------------------------------------


def test_set_dynamic_puts_replaces_and_removes_a_dynamic_at_a_position() -> None:
    score = _score()
    put = _edit(score, EditOp.SET_DYNAMIC, _anchor(1, 0), {"offset_beats": "1", "mark": "mf"})
    assert put.before == {"offset_beats": "1", "mark": None}
    edited = apply_edit(score, put)
    assert _measure(edited, 1).dynamics == (
        Dynamic(DynamicMark.P, Fraction(0)),
        Dynamic(DynamicMark.MF, Fraction(1)),
    )
    assert _undo(edited, put) == score

    replace = _edit(score, EditOp.SET_DYNAMIC, _anchor(1, 0), {"offset_beats": 0, "mark": "f"})
    assert replace.before == {"offset_beats": "0", "mark": "p"}
    assert _measure(apply_edit(score, replace), 1).dynamics == (
        Dynamic(DynamicMark.F, Fraction(0)),
    )

    remove = _edit(score, EditOp.SET_DYNAMIC, _anchor(1, 0), {"offset_beats": "0", "mark": None})
    removed = apply_edit(score, remove)
    assert _measure(removed, 1).dynamics == ()
    assert _undo(removed, remove) == score


@pytest.mark.parametrize(
    "after",
    [
        {"offset_beats": "1", "mark": "sfp"},
        {"offset_beats": "1"},
        {"offset_beats": "1", "mark": "f", "voice": 0},
        {"offset_beats": "-1", "mark": "f"},
        # Más allá del final del compás de 4/4.
        {"offset_beats": "5", "mark": "f"},
        # Una posición que la exportación no escribe exacta (10080 divisiones por negra).
        {"offset_beats": "1/11", "mark": "f"},
        {"offset_beats": "abc", "mark": "f"},
        {"offset_beats": True, "mark": "f"},
        {"offset_beats": float("inf"), "mark": "f"},
        {"offset_beats": "1", "mark": 3},
    ],
)
def test_set_dynamic_rejects_invalid_after(after: dict[str, Any]) -> None:
    with pytest.raises(InvalidEditPayload):
        validate_after(_score(), _anchor(1, 0), EditOp.SET_DYNAMIC, after)


def test_set_dynamic_only_needs_the_measure_of_the_anchor() -> None:
    # Como la clave y la armadura (ADR-0010), la dinámica es del compás: basta que exista.
    score = _score()
    validate_after(score, _anchor(2, 9), EditOp.SET_DYNAMIC, {"offset_beats": "3", "mark": "pp"})
    with pytest.raises(IndexError):
        validate_after(score, _anchor(7, 0), EditOp.SET_DYNAMIC, {"offset_beats": "0", "mark": "p"})


def test_set_dynamic_refuses_a_position_with_two_dynamics() -> None:
    # La instantánea guarda una dinámica por posición: con dos, deshacer no sería exacto.
    score = _score()
    doubled = apply_edit(
        score,
        EditEvent(
            id="x",
            document_id="doc",
            seq=1,
            anchor=_anchor(1, 0),
            op=EditOp.SET_DYNAMIC,
            author="ana",
            created_at=NOW,
            after={"offset_beats": "1", "mark": "f"},
        ),
    )
    first = doubled.parts[0].staves[0].measures[0]
    crowded = Measure(
        number=first.number,
        events=first.events,
        time_signature=first.time_signature,
        clef=first.clef,
        key_signature=first.key_signature,
        dynamics=(*first.dynamics, Dynamic(DynamicMark.SF, Fraction(1))),
    )
    staff = Staff(id=STAFF_ID, measures=(crowded, doubled.parts[0].staves[0].measures[1]))
    crowded_score = ScoreIR(parts=(Part(id="part-0", staves=(staff,)),))
    with pytest.raises(InvalidEditPayload):
        validate_after(
            crowded_score, _anchor(1, 0), EditOp.SET_DYNAMIC, {"offset_beats": "1", "mark": "p"}
        )


# --- SetSlur -----------------------------------------------------------------------------


def test_set_slur_creates_both_ends_and_undo_removes_them() -> None:
    score = _score()
    after = {"number": 2, "start": _slot(1, 1), "stop": _slot(2, 0)}
    edit = _edit(score, EditOp.SET_SLUR, _anchor(1, 1), after)

    assert edit.before == {"number": 2, "start": None, "stop": None}
    edited = apply_edit(score, edit)
    assert _events(edited, 1)[1].slurs == (Slur(SlurType.START, 2),)
    assert _events(edited, 2)[0].slurs == (Slur(SlurType.STOP, 2),)
    assert _undo(edited, edit) == score


def test_set_slur_removes_both_ends_and_undo_restores_them() -> None:
    score = _score()
    after = {"number": 1, "start": None, "stop": None}
    edit = _edit(score, EditOp.SET_SLUR, _anchor(1, 0), after)

    assert edit.before == {"number": 1, "start": _slot(1, 0), "stop": _slot(1, 2)}
    edited = apply_edit(score, edit)
    assert all(event.slurs == () for event in _events(edited, 1))
    assert _undo(edited, edit) == score


def test_set_slur_removes_an_orphan_end() -> None:
    # Borrar la nota del fin deja el inicio huérfano (ADR-0031 §5): quitarlo lo limpia, y
    # deshacerlo devuelve solo ese extremo.
    score = _score()
    deleted = apply_edit(score, _edit(score, EditOp.DELETE_EVENT, _anchor(1, 2), None))
    remove = _edit(
        deleted, EditOp.SET_SLUR, _anchor(1, 0), {"number": 1, "start": None, "stop": None}, seq=2
    )
    assert remove.before == {"number": 1, "start": _slot(1, 0), "stop": None}
    cleaned = apply_edit(deleted, remove)
    assert _events(cleaned, 1)[0].slurs == ()
    assert _undo(cleaned, remove) == deleted


def test_set_slur_from_a_grace_note_to_its_main_note() -> None:
    grace = Event(kind=EventKind.NOTE, pitch="A4")
    measure = Measure(number=1, events=(grace, _note("G4", 4)), time_signature=TimeSignature(4, 4))
    score = ScoreIR(parts=(Part(id="p", staves=(Staff(id=STAFF_ID, measures=(measure,)),)),))
    after = {"number": 1, "start": _slot(1, 0), "stop": _slot(1, 1)}
    validate_after(score, _anchor(1, 0), EditOp.SET_SLUR, after)


@pytest.mark.parametrize(
    ("anchor", "after"),
    [
        # El número ya es de una ligadura de la parte.
        (_anchor(1, 1), {"number": 1, "start": _slot(1, 1), "stop": _slot(2, 0)}),
        # Quitar una ligadura que no está.
        (_anchor(1, 0), {"number": 5, "start": None, "stop": None}),
        # Un solo extremo: una ligadura se crea con su inicio y su fin.
        (_anchor(1, 1), {"number": 2, "start": _slot(1, 1), "stop": None}),
        # El fin antes del inicio, o el mismo evento.
        (_anchor(2, 0), {"number": 2, "start": _slot(2, 0), "stop": _slot(1, 1)}),
        (_anchor(1, 1), {"number": 2, "start": _slot(1, 1), "stop": _slot(1, 1)}),
        # Un silencio, una nota de un acorde que no es la primera, un evento que no está.
        (_anchor(1, 1), {"number": 2, "start": _slot(1, 1), "stop": _slot(2, 1)}),
        (_anchor(1, 1), {"number": 2, "start": _slot(1, 1), "stop": _slot(2, 3)}),
        (_anchor(1, 1), {"number": 2, "start": _slot(1, 1), "stop": _slot(2, 9)}),
        (_anchor(1, 1), {"number": 2, "start": _slot(1, 1), "stop": _slot(3, 0)}),
        # El ancla es el inicio (o, sin él, el fin).
        (_anchor(1, 0), {"number": 2, "start": _slot(1, 1), "stop": _slot(2, 0)}),
        (_anchor(1, 2), {"number": 1, "start": None, "stop": None}),
        # Forma.
        (_anchor(1, 1), {"number": 0, "start": _slot(1, 1), "stop": _slot(2, 0)}),
        (_anchor(1, 1), {"number": True, "start": _slot(1, 1), "stop": _slot(2, 0)}),
        (_anchor(1, 1), {"number": 2, "start": {**_slot(1, 1), "x": 1}, "stop": _slot(2, 0)}),
        (_anchor(1, 1), {"number": 2, "start": _slot(1, 1)}),
        (_anchor(1, 1), {"number": 2, "start": _slot(1, 1), "stop": _slot(2, 0), "type": "x"}),
        (_anchor(1, 1), None),
    ],
)
def test_set_slur_rejects_invalid_after(anchor: Anchor, after: dict[str, Any] | None) -> None:
    with pytest.raises(InvalidEditPayload):
        validate_after(_score(), anchor, EditOp.SET_SLUR, after)


# --- SetWedge ----------------------------------------------------------------------------


def _wedge_start(measure: int, offset: str, kind: str = "crescendo") -> dict[str, Any]:
    return {"staff": 0, "measure": measure, "offset_beats": offset, "type": kind}


def _wedge_stop(measure: int, offset: str) -> dict[str, Any]:
    return {"staff": 0, "measure": measure, "offset_beats": offset}


def test_set_wedge_creates_both_ends_and_undo_removes_them() -> None:
    score = _score()
    after = {
        "number": 2,
        "start": _wedge_start(1, "2", "diminuendo"),
        "stop": _wedge_stop(2, "1"),
    }
    edit = _edit(score, EditOp.SET_WEDGE, _anchor(1, 0), after)

    assert edit.before == {"number": 2, "start": None, "stop": None}
    edited = apply_edit(score, edit)
    assert Wedge(WedgeType.DIMINUENDO, 2, Fraction(2)) in _measure(edited, 1).wedges
    assert _measure(edited, 2).wedges == (Wedge(WedgeType.STOP, 2, Fraction(1)),)
    assert _undo(edited, edit) == score


def test_set_wedge_removes_both_ends_and_undo_restores_them() -> None:
    score = _score()
    edit = _edit(score, EditOp.SET_WEDGE, _anchor(1, 0), {"number": 1, "start": None, "stop": None})

    assert edit.before == {
        "number": 1,
        "start": _wedge_start(1, "1"),
        "stop": _wedge_stop(1, "2"),
    }
    edited = apply_edit(score, edit)
    assert _measure(edited, 1).wedges == ()
    assert _undo(edited, edit) == score


@pytest.mark.parametrize(
    ("anchor", "after"),
    [
        (_anchor(1, 0), {"number": 1, "start": _wedge_start(1, "2"), "stop": _wedge_stop(2, "1")}),
        (_anchor(1, 0), {"number": 7, "start": None, "stop": None}),
        (_anchor(1, 0), {"number": 2, "start": None, "stop": _wedge_stop(2, "1")}),
        # El fin no puede ir antes del inicio ni en la misma posición.
        (_anchor(1, 0), {"number": 2, "start": _wedge_start(1, "3"), "stop": _wedge_stop(1, "1")}),
        (_anchor(1, 0), {"number": 2, "start": _wedge_start(1, "1"), "stop": _wedge_stop(1, "1")}),
        (
            _anchor(1, 0),
            {"number": 2, "start": _wedge_start(1, "1", "stop"), "stop": _wedge_stop(2, "1")},
        ),
        (_anchor(1, 0), {"number": 2, "start": _wedge_start(1, "9"), "stop": _wedge_stop(2, "1")}),
        (_anchor(1, 0), {"number": 2, "start": _wedge_start(1, "1"), "stop": _wedge_stop(5, "1")}),
        (
            _anchor(1, 0),
            {"number": 2, "start": _wedge_start(1, "1/11"), "stop": _wedge_stop(2, "1")},
        ),
        # El ancla está en el compás del inicio.
        (_anchor(2, 0), {"number": 2, "start": _wedge_start(1, "1"), "stop": _wedge_stop(2, "1")}),
        (_anchor(2, 0), {"number": 1, "start": None, "stop": None}),
        (
            _anchor(1, 0),
            {
                "number": 2,
                "start": {**_wedge_start(1, "1"), "voice": 0},
                "stop": _wedge_stop(2, "1"),
            },
        ),
        (_anchor(1, 0), {"number": 2, "start": _wedge_start(1, "1")}),
    ],
)
def test_set_wedge_rejects_invalid_after(anchor: Anchor, after: dict[str, Any]) -> None:
    with pytest.raises(InvalidEditPayload):
        validate_after(_score(), anchor, EditOp.SET_WEDGE, after)


# --- Deshacer, anclas y estado previo ---------------------------------------------------


@pytest.mark.parametrize(
    ("op", "before", "complete"),
    [
        (EditOp.SET_NOTE_MARKS, {"articulations": [], "fermata": False}, True),
        (EditOp.SET_NOTE_MARKS, {"articulations": []}, False),
        (EditOp.SET_DYNAMIC, {"offset_beats": "0", "mark": None}, True),
        (EditOp.SET_DYNAMIC, {"offset_beats": "0"}, False),
        (EditOp.SET_SLUR, {"number": 1, "start": None, "stop": None}, True),
        (EditOp.SET_SLUR, {"number": 1}, False),
        (EditOp.SET_WEDGE, {"number": 1, "start": None, "stop": None}, True),
        (EditOp.SET_WEDGE, None, False),
    ],
)
def test_has_complete_before_for_mark_ops(
    op: EditOp, before: dict[str, Any] | None, complete: bool
) -> None:
    edit = EditEvent(
        id="e",
        document_id="doc",
        seq=1,
        anchor=_anchor(),
        op=op,
        author="ana",
        created_at=NOW,
        before=before,
    )
    assert has_complete_before(edit) is complete


def test_mark_ops_do_not_move_anchors() -> None:
    # Ninguna marca es un evento (ADR-0031 §2): no desplazan el `event_index` (ADR-0011 §2).
    score = _score()
    edits = [
        _edit(
            score,
            EditOp.SET_SLUR,
            _anchor(1, 1),
            {"number": 2, "start": _slot(1, 1), "stop": _slot(1, 2)},
        ),
    ]
    assert translate_anchor(_anchor(1, 2), 0, 1, edits) == _anchor(1, 2)
