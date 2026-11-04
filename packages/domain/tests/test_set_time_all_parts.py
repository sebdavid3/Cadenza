"""Cambiar el compás en todas las partes con una sola edición (#326, enmienda de ADR-0044).

`SetTime` con ``"all_parts": true`` cambia el compás desde el compás del ancla hasta el siguiente
cambio en todas las partes de la partitura (en cada una, su tramo, en todos sus pentagramas),
con una edición que se deshace de un paso y exactamente. Sin él, como siempre: solo la parte del
ancla, para que un `SetTime` guardado antes de #326 (y el candidato de `time.signature`, que es
de una parte) siga materializando igual.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from cadenza.domain import (
    Anchor,
    EditEvent,
    EditOp,
    Event,
    EventKind,
    InvalidEditPayload,
    Measure,
    Part,
    ScoreIR,
    Staff,
    TimeSignature,
    apply_edit,
    create_inverse_edit,
    has_complete_before,
    materialize,
    snapshot_before,
    validate_after,
)

NOW = datetime(2026, 11, 2, tzinfo=UTC)
FOUR = TimeSignature(4, 4)
THREE = TimeSignature(3, 4)
THREE_AFTER = {"beats": 3, "beat_type": 4}

Signatures = list[TimeSignature | None]


def _part(index: int, *staves: Signatures) -> Part:
    return Part(
        id=f"part-{index}",
        staves=tuple(
            Staff(
                id=f"part-{index}-staff-{s}",
                measures=tuple(
                    Measure(
                        number=n,
                        events=(Event(kind=EventKind.NOTE, pitch="C5", duration_beats=None),),
                        time_signature=signature,
                    )
                    for n, signature in enumerate(signatures, start=1)
                ),
            )
            for s, signatures in enumerate(staves)
        ),
    )


def _score(*parts: list[Signatures]) -> ScoreIR:
    return ScoreIR(parts=tuple(_part(i, *staves) for i, staves in enumerate(parts)))


def _anchor(part: int = 0, measure: int = 1, staff: int = 0) -> Anchor:
    return Anchor(
        part=part,
        staff=staff,
        measure=measure,
        voice=0,
        event_index=0,
        staff_id=f"part-{part}-staff-{staff}",
    )


def _edit(score: ScoreIR, anchor: Anchor, after: dict[str, Any], seq: int = 1) -> EditEvent:
    """Una edición como la guarda el servidor: `after` validado y `before` su instantánea."""

    validate_after(score, anchor, EditOp.SET_TIME, after)
    return EditEvent(
        id=f"e{seq}",
        document_id="doc",
        seq=seq,
        anchor=anchor,
        op=EditOp.SET_TIME,
        author="ana",
        created_at=NOW,
        before=snapshot_before(score, anchor, EditOp.SET_TIME, after),
        after=after,
    )


def _undo(score: ScoreIR, edit: EditEvent) -> ScoreIR:
    inverse = create_inverse_edit(edit, id="u", seq=edit.seq + 1, author="ana", created_at=NOW)
    return apply_edit(score, inverse)


def _signatures(score: ScoreIR, part: int, staff: int = 0) -> list[dict[str, Any] | None]:
    return [
        None if m.time_signature is None else m.time_signature.to_primitive()
        for m in score.parts[part].staves[staff].measures
    ]


def _all_parts(signature: dict[str, Any] = THREE_AFTER, **extra: Any) -> dict[str, Any]:
    return {"time_signature": signature, "all_parts": True, **extra}


# --- El significado de lo guardado ---------------------------------------------------------


def test_set_time_without_all_parts_still_changes_only_the_part_of_the_anchor() -> None:
    # Un SetTime guardado antes de #326 (y el candidato de time.signature) no lleva all_parts:
    # materializa como entonces, en la parte del ancla, con la misma instantánea.
    score = _score([[None, None]], [[None, None], [None, None]])
    edit = _edit(score, _anchor(0), {"time_signature": THREE_AFTER})
    assert edit.before == {"time_signature": None, "measures": 2}
    changed = apply_edit(score, edit)
    assert _signatures(changed, 0) == [THREE_AFTER, THREE_AFTER]
    assert _signatures(changed, 1, 0) == [None, None]
    assert _signatures(changed, 1, 1) == [None, None]
    assert materialize(score, [edit]).to_primitive() == changed.to_primitive()


# --- Todas las partes ----------------------------------------------------------------------


def test_all_parts_sets_voice_and_piano_with_one_edit_and_undoes_in_one_step() -> None:
    # Como TS-02 leída por HOMR: la voz y el piano, sin compás.
    score = _score([[None, None, None]], [[None, None, None], [None, None, None]])
    edit = _edit(score, _anchor(0), _all_parts())
    changed = apply_edit(score, edit)
    assert _signatures(changed, 0) == [THREE_AFTER, THREE_AFTER, THREE_AFTER]
    assert _signatures(changed, 1, 0) == [THREE_AFTER, THREE_AFTER, THREE_AFTER]
    assert _signatures(changed, 1, 1) == [THREE_AFTER, THREE_AFTER, THREE_AFTER]
    assert _undo(changed, edit).to_primitive() == score.to_primitive()


def test_all_parts_from_a_note_of_another_part_changes_them_all() -> None:
    score = _score([[FOUR, FOUR]], [[FOUR, FOUR], [FOUR, FOUR]])
    edit = _edit(score, _anchor(1, measure=1, staff=1), _all_parts())
    changed = apply_edit(score, edit)
    for part, staff in ((0, 0), (1, 0), (1, 1)):
        assert _signatures(changed, part, staff) == [THREE_AFTER, THREE_AFTER]
    assert _undo(changed, edit).to_primitive() == score.to_primitive()


def test_all_parts_before_keeps_each_part_and_is_complete() -> None:
    # La voz ya llevaba 3/4 (un SetTime de antes de #326) y el piano, nada.
    score = _score([[THREE, THREE]], [[None, None], [None, None]])
    edit = _edit(score, _anchor(0), _all_parts())
    assert edit.before == {
        "time_signature": THREE_AFTER,
        "measures": 2,
        "all_parts": True,
        "parts": [
            {"time_signature": THREE_AFTER, "measures": 2},
            {"time_signature": None, "measures": 2},
        ],
    }
    assert has_complete_before(edit)
    changed = apply_edit(score, edit)
    assert _signatures(changed, 1, 1) == [THREE_AFTER, THREE_AFTER]
    assert _undo(changed, edit).to_primitive() == score.to_primitive()


def test_all_parts_changes_the_run_of_each_part_and_undoes_exactly() -> None:
    # Cada parte cambia su tramo: la voz hasta el compás 2 y el piano hasta el 3.
    score = _score([[FOUR, FOUR, THREE, THREE]], [[FOUR, FOUR, FOUR, THREE]])
    edit = _edit(score, _anchor(0), _all_parts({"beats": 2, "beat_type": 2, "symbol": "cut"}))
    changed = apply_edit(score, edit)
    cut = {"beats": 2, "beat_type": 2, "symbol": "cut"}
    three = THREE.to_primitive()
    assert _signatures(changed, 0) == [cut, cut, three, three]
    assert _signatures(changed, 1) == [cut, cut, cut, three]
    assert _undo(changed, edit).to_primitive() == score.to_primitive()


def test_all_parts_with_measures_changes_only_those_in_every_part() -> None:
    score = _score([[FOUR, FOUR, FOUR]], [[FOUR, FOUR, FOUR]])
    edit = _edit(score, _anchor(0), _all_parts(measures=2))
    changed = apply_edit(score, edit)
    for part in (0, 1):
        assert _signatures(changed, part) == [THREE_AFTER, THREE_AFTER, FOUR.to_primitive()]
    assert _undo(changed, edit).to_primitive() == score.to_primitive()


def test_all_parts_skips_a_part_without_that_measure() -> None:
    score = _score([[FOUR, FOUR, FOUR]], [[FOUR]])
    edit = _edit(score, _anchor(0, measure=3), _all_parts())
    assert edit.before is not None
    assert edit.before["parts"] == [{"time_signature": FOUR.to_primitive(), "measures": 1}, None]
    changed = apply_edit(score, edit)
    assert _signatures(changed, 0) == [FOUR.to_primitive(), FOUR.to_primitive(), THREE_AFTER]
    assert _signatures(changed, 1) == [FOUR.to_primitive()]
    assert _undo(changed, edit).to_primitive() == score.to_primitive()


def test_all_parts_redo_after_undo_gives_the_same_state() -> None:
    score = _score([[FOUR, FOUR]], [[None, None]])
    after = _all_parts()
    edit = _edit(score, _anchor(0), after)
    inverse = create_inverse_edit(edit, id="u", seq=2, author="ana", created_at=NOW)
    redo = _edit(materialize(score, [edit, inverse]), _anchor(0), after, seq=3)
    assert materialize(score, [edit, inverse, redo]).to_primitive() == (
        apply_edit(score, edit).to_primitive()
    )


def test_all_parts_rejects_a_part_whose_staves_disagree() -> None:
    score = _score([[FOUR, FOUR]], [[FOUR, FOUR], [THREE, THREE]])
    with pytest.raises(InvalidEditPayload, match="parte 2"):
        validate_after(score, _anchor(0), EditOp.SET_TIME, _all_parts())


def test_all_parts_rejects_measures_past_the_next_change_of_any_part() -> None:
    score = _score([[FOUR, FOUR, FOUR]], [[FOUR, THREE, THREE]])
    with pytest.raises(InvalidEditPayload, match="siguiente cambio"):
        validate_after(score, _anchor(0), EditOp.SET_TIME, _all_parts(measures=2))


@pytest.mark.parametrize(
    "after, message",
    [
        ({"time_signature": THREE_AFTER, "all_parts": 1}, "'all_parts'"),
        ({"time_signature": THREE_AFTER, "all_parts": "yes"}, "'all_parts'"),
        # La forma por partes solo la escribe la compensatoria.
        ({"time_signature": THREE_AFTER, "parts": []}, "no admite parts"),
    ],
)
def test_set_time_rejects_invalid_all_parts(after: dict[str, Any], message: str) -> None:
    score = _score([[FOUR]], [[FOUR]])
    with pytest.raises(InvalidEditPayload, match=message):
        validate_after(score, _anchor(0), EditOp.SET_TIME, after)


def test_all_parts_false_is_the_part_of_the_anchor() -> None:
    score = _score([[FOUR]], [[FOUR]])
    edit = _edit(score, _anchor(0), {"time_signature": THREE_AFTER, "all_parts": False})
    assert edit.before == {"time_signature": FOUR.to_primitive(), "measures": 1}
    changed = apply_edit(score, edit)
    assert _signatures(changed, 1) == [FOUR.to_primitive()]


def test_all_parts_before_without_its_parts_is_not_complete() -> None:
    partial = EditEvent(
        id="p",
        document_id="doc",
        seq=1,
        anchor=_anchor(0),
        op=EditOp.SET_TIME,
        author="ana",
        created_at=NOW,
        before={"time_signature": None, "measures": 1, "all_parts": True},
        after=_all_parts(),
    )
    assert not has_complete_before(partial)


def test_all_parts_six_eight_on_score_without_meter_fills_all_and_undoes_and_redoes() -> None:
    score = _score([[None, None, None]], [[None, None, None], [None, None, None]])
    six_eight = {"beats": 6, "beat_type": 8}
    after = _all_parts(six_eight)
    edit = _edit(score, _anchor(0), after)
    changed = apply_edit(score, edit)
    for part, staff in ((0, 0), (1, 0), (1, 1)):
        assert _signatures(changed, part, staff) == [six_eight, six_eight, six_eight]
    undone = _undo(changed, edit)
    for part, staff in ((0, 0), (1, 0), (1, 1)):
        assert _signatures(undone, part, staff) == [None, None, None]
    inverse = create_inverse_edit(edit, id="u", seq=2, author="ana", created_at=NOW)
    redo = _edit(undone, _anchor(0), after, seq=3)
    assert materialize(score, [edit, inverse, redo]).to_primitive() == changed.to_primitive()


def test_all_parts_rejects_partial_measures_when_a_part_has_no_signature() -> None:
    score = _score([[FOUR, FOUR, FOUR]], [[None, None, None], [None, None, None]])
    with pytest.raises(InvalidEditPayload, match="debe cubrir todo el tramo"):
        validate_after(score, _anchor(0), EditOp.SET_TIME, _all_parts(measures=2))
