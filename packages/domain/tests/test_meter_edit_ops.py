"""Cambiar el compás y poner o quitar tresillos (ADR-0044, #236).

`SetTime` cambia la indicación de compás desde un compás hasta el siguiente cambio, en toda la
parte; `SetTuplet` pone o quita el tresillo a los eventos seguidos de una voz. Las dos son de
tipo «fijar»: `before` es la instantánea del servidor y la compensatoria intercambia `before` y
`after` (ADR-0007, ADR-0017), así que deshacer es exacto.
"""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction
from typing import Any

import pytest
from cadenza.domain import (
    CONTENT_EDIT_OPS,
    MARK_EDIT_OPS,
    METER_EDIT_OPS,
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
    compute_timing_map,
    create_inverse_edit,
    has_complete_before,
    materialize,
    snapshot_before,
    translate_anchor,
    validate_after,
)

NOW = datetime(2026, 10, 31, tzinfo=UTC)
FOUR = TimeSignature(4, 4)
THREE = TimeSignature(3, 4)


def _note(pitch: str, beats: Fraction | int | None = 1, **kwargs: Any) -> Event:
    duration = None if beats is None else Fraction(beats)
    return Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=duration, **kwargs)


def _rest(beats: Fraction | int = 1, **kwargs: Any) -> Event:
    return Event(kind=EventKind.REST, duration_beats=Fraction(beats), **kwargs)


def _staff(index: int, signatures: list[TimeSignature | None]) -> Staff:
    return Staff(
        id=f"part-0-staff-{index}",
        measures=tuple(
            Measure(number=n, events=(_note("C5", 4),), time_signature=signature)
            for n, signature in enumerate(signatures, start=1)
        ),
    )


def _score(*staves: list[TimeSignature | None]) -> ScoreIR:
    return ScoreIR(
        parts=(Part(id="part-0", staves=tuple(_staff(i, s) for i, s in enumerate(staves))),)
    )


def _anchor(measure: int = 1, event_index: int = 0, voice: int = 0, staff: int = 0) -> Anchor:
    return Anchor(
        part=0,
        staff=staff,
        measure=measure,
        voice=voice,
        event_index=event_index,
        staff_id=f"part-0-staff-{staff}",
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


def _signatures(score: ScoreIR, staff: int = 0) -> list[dict[str, Any] | None]:
    return [
        None if m.time_signature is None else m.time_signature.to_primitive()
        for m in score.parts[0].staves[staff].measures
    ]


def _durations(score: ScoreIR, measure: int = 1) -> list[str | None]:
    return [
        None if e.duration_beats is None else str(e.duration_beats)
        for e in score.parts[0].staves[0].measures[measure - 1].events
    ]


# --- La política de EditOp ---------------------------------------------------------------


def test_meter_ops_are_their_own_class_and_content_stays_at_seven() -> None:
    # Y la figura de un acorde (ADR-0049, `test_chord_duration_op.py`).
    # Y la ligadura de prolongación (ADR-0055, `test_tie_and_chord_edits.py`).
    assert {
        EditOp.SET_TIME,
        EditOp.SET_TUPLET,
        EditOp.SET_CHORD_DURATION,
        EditOp.SET_TIE,
    } == METER_EDIT_OPS
    assert CONTENT_EDIT_OPS.isdisjoint(METER_EDIT_OPS)
    assert MARK_EDIT_OPS.isdisjoint(METER_EDIT_OPS)
    assert set(EditOp) == CONTENT_EDIT_OPS | MARK_EDIT_OPS | METER_EDIT_OPS
    # La cobertura de exp_02 se calcula sobre las siete de contenido: no cambia (ADR-0039 §3).
    assert len(CONTENT_EDIT_OPS) == 7


# --- TimeSignature.symbol ----------------------------------------------------------------


def test_symbol_is_notation_and_does_not_change_the_meter() -> None:
    common = TimeSignature(4, 4, "common")
    cut = TimeSignature(2, 2, "cut")
    assert common == FOUR
    assert hash(common) == hash(FOUR)
    assert not common.same_notation(FOUR)
    assert common.same_notation(TimeSignature(4, 4, "common"))
    assert str(common) == "4/4"
    assert str(cut) == "2/2"
    assert cut.quarter_length == Fraction(4)


def test_symbol_roundtrips_and_is_omitted_without_it() -> None:
    assert FOUR.to_primitive() == {"beats": 4, "beat_type": 4}
    common = TimeSignature(4, 4, "common")
    assert common.to_primitive() == {"beats": 4, "beat_type": 4, "symbol": "common"}
    restored = TimeSignature.from_primitive(common.to_primitive())
    assert restored.same_notation(common)
    assert TimeSignature.from_primitive({"beats": 3, "beat_type": 4}).symbol is None


@pytest.mark.parametrize(
    "beats, beat_type, symbol", [(3, 4, "common"), (4, 4, "cut"), (2, 2, "common"), (4, 4, "x")]
)
def test_symbol_must_match_its_meter(beats: int, beat_type: int, symbol: str) -> None:
    with pytest.raises(ValueError, match="symbol"):
        TimeSignature(beats, beat_type, symbol)


# --- SetTime -----------------------------------------------------------------------------


def test_set_time_changes_until_the_next_change_and_undoes_exactly() -> None:
    # Como la importación: cada compás lleva su métrica efectiva.
    score = _score([FOUR, FOUR, FOUR, THREE, THREE])
    edit = _edit(
        score, EditOp.SET_TIME, _anchor(2), {"time_signature": {"beats": 2, "beat_type": 4}}
    )
    assert edit.before == {"time_signature": {"beats": 4, "beat_type": 4}, "measures": 2}
    changed = apply_edit(score, edit)
    two = {"beats": 2, "beat_type": 4}
    three = {"beats": 3, "beat_type": 4}
    assert _signatures(changed) == [FOUR.to_primitive(), two, two, three, three]
    assert _undo(changed, edit).to_primitive() == score.to_primitive()


def test_set_time_writes_the_symbol_and_undoing_restores_the_numbers() -> None:
    score = _score([FOUR, FOUR])
    after = {"time_signature": {"beats": 4, "beat_type": 4, "symbol": "common"}}
    edit = _edit(score, EditOp.SET_TIME, _anchor(1), after)
    changed = apply_edit(score, edit)
    common = {"beats": 4, "beat_type": 4, "symbol": "common"}
    assert _signatures(changed) == [common, common]
    assert _undo(changed, edit).to_primitive() == score.to_primitive()


def test_set_time_changes_every_staff_of_the_part() -> None:
    score = _score([FOUR, FOUR, FOUR], [FOUR, FOUR, FOUR])
    edit = _edit(
        score,
        EditOp.SET_TIME,
        _anchor(2, staff=1),
        {"time_signature": {"beats": 3, "beat_type": 4}},
    )
    changed = apply_edit(score, edit)
    for staff in (0, 1):
        assert _signatures(changed, staff) == [FOUR.to_primitive(), *[THREE.to_primitive()] * 2]
    assert _undo(changed, edit).to_primitive() == score.to_primitive()


def test_set_time_keeps_measures_without_signature_inheriting() -> None:
    # Compases que heredan (sin indicación): siguen sin ella y heredan la nueva.
    score = _score([FOUR, None, FOUR, THREE])
    edit = _edit(
        score, EditOp.SET_TIME, _anchor(1), {"time_signature": {"beats": 2, "beat_type": 2}}
    )
    assert edit.before == {"time_signature": FOUR.to_primitive(), "measures": 3}
    changed = apply_edit(score, edit)
    cut = {"beats": 2, "beat_type": 2}
    assert _signatures(changed) == [cut, None, cut, THREE.to_primitive()]
    assert _undo(changed, edit).to_primitive() == score.to_primitive()


def test_undoing_set_time_on_a_measure_without_signature_leaves_it_without_one() -> None:
    # La compensatoria escribe null: el compás 2 heredaba y vuelve a heredar.
    score = _score([FOUR, None, FOUR, THREE])
    after = {"time_signature": {"beats": 3, "beat_type": 8}}
    edit = _edit(score, EditOp.SET_TIME, _anchor(2), after)
    assert edit.before == {"time_signature": None, "measures": 2}
    changed = apply_edit(score, edit)
    eight = {"beats": 3, "beat_type": 8}
    assert _signatures(changed) == [FOUR.to_primitive(), eight, eight, THREE.to_primitive()]
    assert _undo(changed, edit).to_primitive() == score.to_primitive()


def test_undoing_set_time_uses_the_length_it_changed() -> None:
    # Tras el cambio, el compás 4 lleva la misma indicación que el tramo cambiado: deshacer
    # devuelve solo los compases 2 y 3, los que cambió.
    score = _score([FOUR, THREE, THREE, FOUR, FOUR])
    edit = _edit(
        score, EditOp.SET_TIME, _anchor(2), {"time_signature": {"beats": 4, "beat_type": 4}}
    )
    changed = apply_edit(score, edit)
    assert _signatures(changed) == [FOUR.to_primitive()] * 5
    assert _undo(changed, edit).to_primitive() == score.to_primitive()


def test_set_time_redo_after_undo_gives_the_same_state() -> None:
    score = _score([FOUR, FOUR, THREE])
    after = {"time_signature": {"beats": 6, "beat_type": 8}}
    edit = _edit(score, EditOp.SET_TIME, _anchor(1), after)
    inverse = create_inverse_edit(edit, id="u", seq=2, author="ana", created_at=NOW)
    redo = _edit(materialize(score, [edit, inverse]), EditOp.SET_TIME, _anchor(1), after, seq=3)
    assert materialize(score, [edit, inverse, redo]).to_primitive() == (
        apply_edit(score, edit).to_primitive()
    )


def test_set_time_with_explicit_measures_changes_only_those() -> None:
    score = _score([FOUR, FOUR, FOUR, FOUR])
    after = {"time_signature": {"beats": 3, "beat_type": 4}, "measures": 2}
    edit = _edit(score, EditOp.SET_TIME, _anchor(1), after)
    # La instantánea tiene la forma del `after`: los compases que cambia.
    assert edit.before == {"time_signature": FOUR.to_primitive(), "measures": 2}
    changed = apply_edit(score, edit)
    assert _signatures(changed) == [THREE.to_primitive()] * 2 + [FOUR.to_primitive()] * 2
    assert _undo(changed, edit).to_primitive() == score.to_primitive()


def test_set_time_does_not_move_anchors() -> None:
    score = _score([FOUR, FOUR])
    edit = _edit(
        score, EditOp.SET_TIME, _anchor(1), {"time_signature": {"beats": 3, "beat_type": 4}}
    )
    assert translate_anchor(_anchor(1), 0, 1, [edit]) == _anchor(1)


@pytest.mark.parametrize(
    "after, message",
    [
        ({}, "requiere time_signature"),
        ({"time_signature": {"beats": 4, "beat_type": 4}, "x": 1}, "no admite x"),
        ({"time_signature": {"beats": 4}}, "requiere beat_type"),
        ({"time_signature": {"beats": 0, "beat_type": 4}}, "'beats'"),
        ({"time_signature": {"beats": True, "beat_type": 4}}, "'beats'"),
        ({"time_signature": {"beats": 33, "beat_type": 4}}, "'beats'"),
        ({"time_signature": {"beats": 3, "beat_type": 3}}, "'beat_type'"),
        ({"time_signature": {"beats": 3, "beat_type": 64}}, "'beat_type'"),
        ({"time_signature": {"beats": 3, "beat_type": 4, "symbol": "common"}}, "símbolo"),
        ({"time_signature": {"beats": 4, "beat_type": 4, "symbol": "C"}}, "'symbol'"),
        ({"time_signature": {"beats": 4, "beat_type": 4, "mode": 1}}, "no admite mode"),
        ({"time_signature": "4/4"}, "'time_signature'"),
        ({"time_signature": {"beats": 3, "beat_type": 4}, "measures": 0}, "'measures'"),
        ({"time_signature": {"beats": 3, "beat_type": 4}, "measures": True}, "'measures'"),
        ({"time_signature": {"beats": 3, "beat_type": 4}, "measures": 3}, "siguiente cambio"),
        ({"time_signature": None}, "requiere un compás"),
        (None, "objeto 'after'"),
    ],
)
def test_set_time_rejects_invalid_after(after: dict[str, Any] | None, message: str) -> None:
    score = _score([FOUR, FOUR, THREE])
    with pytest.raises(InvalidEditPayload, match=message):
        validate_after(score, _anchor(1), EditOp.SET_TIME, after)


def test_set_time_rejects_staves_with_different_signatures() -> None:
    score = _score([FOUR, FOUR], [THREE, THREE])
    with pytest.raises(InvalidEditPayload, match="misma indicación"):
        validate_after(
            score, _anchor(1), EditOp.SET_TIME, {"time_signature": {"beats": 2, "beat_type": 4}}
        )


def test_set_time_needs_an_existing_measure() -> None:
    with pytest.raises(IndexError):
        validate_after(
            _score([FOUR]),
            _anchor(9),
            EditOp.SET_TIME,
            {"time_signature": {"beats": 2, "beat_type": 4}},
        )


def test_set_time_before_is_complete_with_signature_and_length() -> None:
    score = _score([FOUR])
    edit = _edit(
        score, EditOp.SET_TIME, _anchor(1), {"time_signature": {"beats": 2, "beat_type": 4}}
    )
    assert has_complete_before(edit)
    partial = EditEvent(
        id="p",
        document_id="doc",
        seq=1,
        anchor=_anchor(1),
        op=EditOp.SET_TIME,
        author="ana",
        created_at=NOW,
        before={"time_signature": None},
        after={"time_signature": {"beats": 2, "beat_type": 4}},
    )
    assert not has_complete_before(partial)


# --- SetTuplet ---------------------------------------------------------------------------


def _measure_score(events: tuple[Event, ...]) -> ScoreIR:
    measure = Measure(number=1, events=events, time_signature=FOUR)
    return ScoreIR(
        parts=(Part(id="part-0", staves=(Staff(id="part-0-staff-0", measures=(measure,)),)),)
    )


def test_twelve_eighths_become_four_triplets_in_one_edit_and_one_undo() -> None:
    pitches = ["C5", "D5", "E5", "F5", "G5", "A5", "B5", "C6", "B5", "A5", "G5", "F5"]
    score = _measure_score(tuple(_note(p, Fraction(1, 2)) for p in pitches))
    after = {"durations": ["1/3"] * 12}
    edit = _edit(score, EditOp.SET_TUPLET, _anchor(), after)
    assert edit.before == {"durations": ["1/2"] * 12}
    changed = apply_edit(score, edit)
    assert _durations(changed) == ["1/3"] * 12
    # El compás de 4/4 queda lleno: cuatro tresillos de corcheas.
    assert compute_timing_map(changed).total_beats == 4
    assert _undo(changed, edit).to_primitive() == score.to_primitive()


def test_set_tuplet_removes_triplets_and_keeps_the_rest_of_the_voice() -> None:
    events = (
        _note("C5", Fraction(1, 3)),
        _note("D5", Fraction(1, 3)),
        _note("E5", Fraction(1, 3)),
        _note("F5", 3),
    )
    score = _measure_score(events)
    edit = _edit(score, EditOp.SET_TUPLET, _anchor(), {"durations": ["1/2", "1/2", "1/2"]})
    changed = apply_edit(score, edit)
    assert _durations(changed) == ["1/2", "1/2", "1/2", "3"]
    assert _undo(changed, edit).to_primitive() == score.to_primitive()


def test_set_tuplet_covers_chords_rests_and_grace_notes() -> None:
    events = (
        _note("C5", Fraction(1, 2)),
        _note("E5", Fraction(1, 2), is_chord=True),
        _note("D5", None),  # nota de adorno
        _rest(Fraction(1, 2)),
        _note("F5", Fraction(1, 2)),
        _note("G5", 2),
    )
    score = _measure_score(events)
    after = {"durations": ["1/3", "1/3", None, "1/3", "1/3"]}
    edit = _edit(score, EditOp.SET_TUPLET, _anchor(), after)
    changed = apply_edit(score, edit)
    assert _durations(changed) == ["1/3", "1/3", None, "1/3", "1/3", "2"]
    assert _undo(changed, edit).to_primitive() == score.to_primitive()


def test_set_tuplet_starts_at_the_anchor_of_its_voice() -> None:
    events = (
        _note("C5", 1),
        _note("A4", 2, voice=1),
        _note("D5", Fraction(1, 2)),
        _note("E5", Fraction(1, 2)),
        _note("F5", Fraction(1, 2)),
        _note("B4", 2, voice=1),
    )
    score = _measure_score(events)
    edit = _edit(score, EditOp.SET_TUPLET, _anchor(event_index=1), {"durations": ["1/3"] * 3})
    changed = apply_edit(score, edit)
    assert _durations(changed) == ["1", "2", "1/3", "1/3", "1/3", "2"]
    assert translate_anchor(_anchor(event_index=2), 0, 1, [edit]) == _anchor(event_index=2)


@pytest.mark.parametrize(
    "after, message",
    [
        ({"durations": []}, "no vacía"),
        ({"durations": "1/3"}, "no vacía"),
        ({"durations": ["1/3"], "x": 1}, "exactamente 'durations'"),
        ({"durations": ["1/3"] * 5}, "solo tiene 4"),
        ({"durations": ["1/4", "1/4"]}, "2/3"),
        ({"durations": ["1/3", "3/4"]}, "solo se quita"),
        ({"durations": ["1/3", None]}, "nota de adorno"),
        ({"durations": ["abc"]}, "duración no válida"),
        (None, "objeto 'after'"),
    ],
)
def test_set_tuplet_rejects_invalid_after(after: dict[str, Any] | None, message: str) -> None:
    score = _measure_score(tuple(_note("C5", Fraction(1, 2)) for _ in range(4)))
    with pytest.raises(InvalidEditPayload, match=message):
        validate_after(score, _anchor(), EditOp.SET_TUPLET, after)


def test_set_tuplet_rejects_putting_a_triplet_twice_or_removing_a_missing_one() -> None:
    triplets = _measure_score(tuple(_note("C5", Fraction(1, 3)) for _ in range(3)))
    # 1/3 · 2/3 = 2/9: un tresillo dentro de otro no es representable.
    with pytest.raises(InvalidEditPayload, match="no representable"):
        validate_after(triplets, _anchor(), EditOp.SET_TUPLET, {"durations": ["2/9"] * 3})
    eighths = _measure_score(tuple(_note("C5", Fraction(1, 2)) for _ in range(3)))
    with pytest.raises(InvalidEditPayload, match="solo se quita"):
        validate_after(eighths, _anchor(), EditOp.SET_TUPLET, {"durations": ["3/4"] * 3})


def test_set_tuplet_puts_or_removes_the_triplet_in_the_whole_range() -> None:
    score = _measure_score((_note("C5", Fraction(1, 2)), _note("D5", Fraction(1, 3))))
    with pytest.raises(InvalidEditPayload, match="no las dos cosas"):
        validate_after(score, _anchor(), EditOp.SET_TUPLET, {"durations": ["1/3", "1/2"]})


def test_set_tuplet_rejects_dotted_figures_that_would_not_be_triplets() -> None:
    # Una negra con puntillo por 2/3 es una negra: no un tresillo.
    dotted = _measure_score(tuple(_note("C5", Fraction(3, 2)) for _ in range(2)))
    with pytest.raises(InvalidEditPayload, match="pasan a llevarlo"):
        validate_after(dotted, _anchor(), EditOp.SET_TUPLET, {"durations": ["1", "1"]})


def test_set_tuplet_needs_a_figure_with_duration() -> None:
    grace = _measure_score((_note("C5", None), _note("D5", 4)))
    with pytest.raises(InvalidEditPayload, match="solo tiene notas de adorno"):
        validate_after(grace, _anchor(), EditOp.SET_TUPLET, {"durations": [None]})


def test_set_tuplet_does_not_split_a_chord() -> None:
    score = _measure_score(
        (
            _note("C5", Fraction(1, 2)),
            _note("E5", Fraction(1, 2), is_chord=True),
            _note("D5", Fraction(1, 2)),
        )
    )
    with pytest.raises(InvalidEditPayload, match="acaba a mitad de un acorde"):
        validate_after(score, _anchor(), EditOp.SET_TUPLET, {"durations": ["1/3"]})
    with pytest.raises(InvalidEditPayload, match="empieza a mitad de un acorde"):
        validate_after(score, _anchor(event_index=1), EditOp.SET_TUPLET, {"durations": ["1/3"]})


def test_set_tuplet_needs_an_existing_event() -> None:
    score = _measure_score((_note("C5", Fraction(1, 2)),))
    with pytest.raises(IndexError):
        validate_after(score, _anchor(event_index=3), EditOp.SET_TUPLET, {"durations": ["1/3"]})


def test_set_tuplet_before_is_complete_with_its_durations() -> None:
    score = _measure_score(tuple(_note("C5", Fraction(1, 2)) for _ in range(3)))
    edit = _edit(score, EditOp.SET_TUPLET, _anchor(), {"durations": ["1/3"] * 3})
    assert has_complete_before(edit)
