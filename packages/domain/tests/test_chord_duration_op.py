"""Cambiar la figura de un acorde entero (ADR-0049, #243, D61).

`SetChordDuration` fija la figura de todas las notas de un acorde en una edición, anclada en su
primera nota: `{"durations": [d, ..., d]}`, una por nota. Es de tipo «fijar», como `SetTuplet`
(ADR-0044): `before` es la instantánea del servidor y la compensatoria intercambia `before` y
`after`, así que se deshace de un paso y exactamente.
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
    Articulation,
    EditEvent,
    EditOp,
    Event,
    EventKind,
    InvalidEditPayload,
    Measure,
    Part,
    ScoreIR,
    Staff,
    Tie,
    TimeSignature,
    apply_edit,
    compute_timing_map,
    create_inverse_edit,
    has_complete_before,
    snapshot_before,
    translate_anchor,
    validate_after,
)

NOW = datetime(2026, 11, 1, tzinfo=UTC)
OP = EditOp.SET_CHORD_DURATION


def _note(pitch: str, beats: Fraction | int | None = 1, **kwargs: Any) -> Event:
    duration = None if beats is None else Fraction(beats)
    return Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=duration, **kwargs)


def _rest(beats: Fraction | int = 1, **kwargs: Any) -> Event:
    return Event(kind=EventKind.REST, duration_beats=Fraction(beats), **kwargs)


def _score(*events: Event) -> ScoreIR:
    measure = Measure(number=1, events=events, time_signature=TimeSignature(4, 4))
    return ScoreIR(
        parts=(Part(id="part-0", staves=(Staff(id="part-0-staff-0", measures=(measure,)),)),)
    )


def _anchor(event_index: int = 0, voice: int = 0) -> Anchor:
    return Anchor(
        part=0, staff=0, measure=1, voice=voice, event_index=event_index, staff_id="part-0-staff-0"
    )


def _edit(score: ScoreIR, anchor: Anchor, after: dict[str, Any], seq: int = 1) -> EditEvent:
    """Una edición como la guarda el servidor: `after` validado y `before` su instantánea."""

    validate_after(score, anchor, OP, after)
    return EditEvent(
        id=f"e{seq}",
        document_id="doc",
        seq=seq,
        anchor=anchor,
        op=OP,
        author="ana",
        created_at=NOW,
        before=snapshot_before(score, anchor, OP, after),
        after=after,
    )


def _undo(score: ScoreIR, edit: EditEvent) -> ScoreIR:
    inverse = create_inverse_edit(edit, id="u", seq=edit.seq + 1, author="ana", created_at=NOW)
    return apply_edit(score, inverse)


def _durations(score: ScoreIR) -> list[str | None]:
    return [
        None if e.duration_beats is None else str(e.duration_beats)
        for e in score.parts[0].staves[0].measures[0].events
    ]


# Un compás de 4/4: un acorde de tres negras (Do, Mi, Sol), un Re negra y una blanca.
TRIAD = (
    _note("C4"),
    _note("E4", is_chord=True),
    _note("G4", is_chord=True),
    _note("D4"),
    _note("F4", 2),
)


# --- La política de EditOp ---------------------------------------------------------------


def test_chord_duration_is_a_meter_op_and_content_stays_at_seven() -> None:
    assert OP.value == "SetChordDuration"
    assert OP in METER_EDIT_OPS
    # Con la ligadura de prolongación (ADR-0055, `test_tie_and_chord_edits.py`).
    assert {EditOp.SET_TIME, EditOp.SET_TUPLET, OP, EditOp.SET_TIE} == METER_EDIT_OPS
    assert OP not in CONTENT_EDIT_OPS and OP not in MARK_EDIT_OPS
    assert set(EditOp) == CONTENT_EDIT_OPS | MARK_EDIT_OPS | METER_EDIT_OPS
    # La cobertura de exp_02 se calcula sobre las siete de contenido: no cambia (ADR-0039 §3).
    assert len(CONTENT_EDIT_OPS) == 7


# --- Cambiar la figura del acorde --------------------------------------------------------


def test_one_edit_changes_every_note_of_the_chord_and_one_undo_restores_it() -> None:
    score = _score(*TRIAD)
    edit = _edit(score, _anchor(), {"durations": ["1/2", "1/2", "1/2"]})
    assert edit.before == {"durations": ["1", "1", "1"]}
    changed = apply_edit(score, edit)
    assert _durations(changed) == ["1/2", "1/2", "1/2", "1", "2"]
    assert _undo(changed, edit).to_primitive() == score.to_primitive()


def test_the_timing_map_gives_every_note_of_the_chord_its_new_figure() -> None:
    score = _score(*TRIAD)
    changed = apply_edit(score, _edit(score, _anchor(), {"durations": ["2", "2", "2"]}))
    timings = {t.anchor.event_index: t for t in compute_timing_map(changed).events}
    # Las tres notas atacan juntas y duran una blanca; el Re entra en el tiempo 3.
    assert [timings[i].offset_beats for i in range(3)] == [0, 0, 0]
    assert [timings[i].duration_beats for i in range(3)] == [2, 2, 2]
    assert timings[3].offset_beats == 2
    # Ahora el compás tiene cinco negras: el mapa de tiempos lo alarga, como con SetDuration.
    assert compute_timing_map(changed).total_beats == 5


def test_undo_is_exact_even_if_the_notes_had_different_figures() -> None:
    # Un acorde con figuras distintas solo sale de ediciones hechas con la API (la importación
    # da a todas la del acorde): deshacer devuelve a cada nota la suya.
    score = _score(_note("C4", 1), _note("E4", Fraction(1, 2), is_chord=True), _note("D4", 3))
    edit = _edit(score, _anchor(), {"durations": ["2", "2"]})
    assert edit.before == {"durations": ["1", "1/2"]}
    changed = apply_edit(score, edit)
    assert _durations(changed) == ["2", "2", "3"]
    assert _undo(changed, edit).to_primitive() == score.to_primitive()


def test_redo_after_undo_gives_the_same_state() -> None:
    score = _score(*TRIAD)
    edit = _edit(score, _anchor(), {"durations": ["3/2"] * 3})
    changed = apply_edit(score, edit)
    redone = apply_edit(_undo(changed, edit), edit)
    assert redone.to_primitive() == changed.to_primitive()


def test_a_grace_chord_takes_a_figure_and_undoing_returns_it_to_grace() -> None:
    score = _score(_note("C5", None), _note("E5", None, is_chord=True), _note("D5", 4))
    edit = _edit(score, _anchor(), {"durations": ["1/4", "1/4"]})
    assert edit.before == {"durations": [None, None]}
    changed = apply_edit(score, edit)
    assert _durations(changed) == ["1/4", "1/4", "4"]
    assert _undo(changed, edit).to_primitive() == score.to_primitive()


def test_marks_ties_and_pitches_of_the_chord_do_not_change() -> None:
    score = _score(
        _note("C4", articulations=(Articulation.ACCENT,), fermata=True, tie=Tie.START),
        _note("E4", is_chord=True),
        _note("D4", 3),
    )
    changed = apply_edit(score, _edit(score, _anchor(), {"durations": ["1/2", "1/2"]}))
    head, second = changed.parts[0].staves[0].measures[0].events[:2]
    assert head.articulations == (Articulation.ACCENT,) and head.fermata and head.tie is Tie.START
    assert (head.pitch, second.pitch, second.is_chord) == ("C4", "E4", True)


def test_a_chord_of_a_second_voice_changes_only_in_its_voice() -> None:
    score = _score(
        _note("C5", 4),
        _note("E4", 2, voice=1),
        _note("G4", 2, voice=1, is_chord=True),
        _note("F4", 2, voice=1),
    )
    anchor = _anchor(voice=1)
    changed = apply_edit(score, _edit(score, anchor, {"durations": ["1", "1"]}))
    assert _durations(changed) == ["4", "1", "1", "2"]


def test_set_chord_duration_does_not_move_anchors() -> None:
    score = _score(*TRIAD)
    edit = _edit(score, _anchor(), {"durations": ["1/2"] * 3})
    for index in range(5):
        assert translate_anchor(_anchor(index), 0, 1, [edit]) == _anchor(index)


def test_the_before_is_complete_with_its_durations() -> None:
    score = _score(*TRIAD)
    edit = _edit(score, _anchor(), {"durations": ["1/2"] * 3})
    assert has_complete_before(edit)
    partial = EditEvent(
        id="p",
        document_id="doc",
        seq=1,
        anchor=_anchor(),
        op=OP,
        author="ana",
        created_at=NOW,
        before={},
        after={"durations": ["1/2"] * 3},
    )
    assert not has_complete_before(partial)


# --- Lo que se rechaza -------------------------------------------------------------------


@pytest.mark.parametrize(
    "after, message",
    [
        (None, "objeto 'after'"),
        ({"durations": []}, "no vacía"),
        ({"durations": "1/2"}, "no vacía"),
        ({"durations": ["1/2"] * 3, "x": 1}, "exactamente 'durations'"),
        ({"duration_beats": "1/2"}, "exactamente 'durations'"),
        ({"durations": ["1/2"] * 2}, "tiene 3 notas"),
        ({"durations": ["1/2"] * 4}, "tiene 3 notas"),
        ({"durations": ["1/2", "1/2", "1"]}, "una sola figura"),
        ({"durations": ["1/2", None, "1/2"]}, "null"),
        ({"durations": ["abc"] * 3}, "duración no válida"),
        ({"durations": ["1/17"] * 3}, "no representable"),
        ({"durations": ["0"] * 3}, "entre 0"),
    ],
)
def test_rejects_an_invalid_after(after: dict[str, Any] | None, message: str) -> None:
    with pytest.raises(InvalidEditPayload, match=message):
        validate_after(_score(*TRIAD), _anchor(), OP, after)


def test_the_anchor_is_the_first_note_of_the_chord() -> None:
    score = _score(*TRIAD)
    with pytest.raises(InvalidEditPayload, match="primera nota"):
        validate_after(score, _anchor(1), OP, {"durations": ["1/2"] * 2})


def test_a_single_note_or_a_rest_is_not_a_chord() -> None:
    score = _score(*TRIAD, _rest(1))
    with pytest.raises(InvalidEditPayload, match="SetDuration"):
        validate_after(score, _anchor(3), OP, {"durations": ["1/2"]})
    with pytest.raises(InvalidEditPayload, match="SetDuration"):
        validate_after(score, _anchor(5), OP, {"durations": ["1/2"]})


def test_a_chord_after_a_rest_starts_where_the_exporter_starts_it() -> None:
    # El exportador agrupa una nota con las siguientes marcadas `is_chord`: tras un silencio,
    # una nota marcada `is_chord` (solo de la API) empieza su acorde.
    score = _score(_rest(1), _note("C4", is_chord=True), _note("E4", is_chord=True), _note("D4", 2))
    changed = apply_edit(score, _edit(score, _anchor(1), {"durations": ["1/2", "1/2"]}))
    assert _durations(changed) == ["1", "1/2", "1/2", "2"]


def test_needs_an_existing_event() -> None:
    with pytest.raises(IndexError):
        validate_after(_score(*TRIAD), _anchor(9), OP, {"durations": ["1/2"] * 3})
