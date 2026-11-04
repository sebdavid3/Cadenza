"""Los huecos de una voz (ADR-0058, #317).

Un hueco es un silencio invisible (ADR-0032). Se borra con `DeleteEvent`, como cualquier evento,
y `SetEventKind`, de tipo «fijar», lo convierte en un silencio que se ve o en una nota en su
lugar, con la misma figura y sin mover ningún evento; `before` es la instantánea del servidor y la
compensatoria intercambia `before` y `after`, así que deshacer devuelve el hueco.
"""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction
from typing import Any

import pytest
from cadenza.domain import (
    CONTENT_EDIT_OPS,
    GAP_EDIT_OPS,
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
    snapshot_before,
    translate_anchor,
    validate_after,
)

NOW = datetime(2026, 11, 2, tzinfo=UTC)
KIND = EditOp.SET_EVENT_KIND


def _note(pitch: str, beats: Fraction | int | str | None = 1, **kwargs: Any) -> Event:
    duration = None if beats is None else Fraction(beats)
    return Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=duration, **kwargs)


def _rest(beats: Fraction | int | str = 1, **kwargs: Any) -> Event:
    return Event(kind=EventKind.REST, duration_beats=Fraction(beats), **kwargs)


def _gap(beats: Fraction | int | str = 1, voice: int = 0) -> Event:
    return _rest(beats, hidden=True, voice=voice)


def _score(*measures: tuple[Event, ...]) -> ScoreIR:
    built = tuple(
        Measure(number=number, events=events, time_signature=TimeSignature(6, 8))
        for number, events in enumerate(measures, start=1)
    )
    return ScoreIR(parts=(Part(id="part-0", staves=(Staff(id="part-0-staff-0", measures=built),)),))


def _anchor(event_index: int = 0, *, measure: int = 1, voice: int = 0) -> Anchor:
    return Anchor(
        part=0,
        staff=0,
        measure=measure,
        voice=voice,
        event_index=event_index,
        staff_id="part-0-staff-0",
    )


def _edit(
    score: ScoreIR, anchor: Anchor, op: EditOp, after: dict[str, Any] | None, seq: int = 1
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


def _events(score: ScoreIR, measure: int = 1) -> tuple[Event, ...]:
    return score.parts[0].staves[0].measures[measure - 1].events


def _rejected(score: ScoreIR, anchor: Anchor, after: Any, match: str) -> None:
    with pytest.raises(InvalidEditPayload, match=match):
        validate_after(score, anchor, KIND, after)


NOTE_F4 = {"kind": "note", "pitch": "F#4", "hidden": False}
SHOWN_REST = {"kind": "rest", "pitch": None, "hidden": False}
GAP = {"kind": "rest", "pitch": None, "hidden": True}

# La voz del compás 1 de TS-03 tal como la importa HOMR: Sol#4 corchea con puntillo, un hueco de
# semicorchea donde va el Fa#4, Fa#4 corchea, Re5 corchea con puntillo, otro hueco de semicorchea
# que sobra, Sol#4 semicorchea y Sol#4 corchea.
TS03_VOICE = (
    _note("G#4", "3/4"),
    _gap("1/4"),
    _note("F#4", "1/2"),
    _note("D5", "3/4"),
    _gap("1/4"),
    _note("G#4", "1/4"),
    _note("G#4", "1/2"),
)


# --- La política de EditOp ---------------------------------------------------------------


def test_set_event_kind_is_a_gap_op_and_content_stays_at_seven() -> None:
    assert KIND.value == "SetEventKind"
    assert {KIND} == GAP_EDIT_OPS
    for other in (CONTENT_EDIT_OPS, MARK_EDIT_OPS, METER_EDIT_OPS):
        assert other.isdisjoint(GAP_EDIT_OPS)
    assert set(EditOp) == CONTENT_EDIT_OPS | MARK_EDIT_OPS | METER_EDIT_OPS | GAP_EDIT_OPS
    # Borrar un hueco es un DeleteEvent: la cobertura de exp_02 sigue siendo sobre siete
    # operaciones (ADR-0039 §3, ADR-0058).
    assert len(CONTENT_EDIT_OPS) == 7


# --- Escribir una nota en el hueco y hacerlo visible --------------------------------------


def test_a_note_in_the_gap_keeps_its_figure_and_one_undo_brings_the_gap_back() -> None:
    score = _score(TS03_VOICE)
    edit = _edit(score, _anchor(1), KIND, NOTE_F4)
    # La instantánea tiene la forma del `after`, con lo que era: un hueco.
    assert edit.before == GAP
    filled = apply_edit(score, edit)
    note = _events(filled)[1]
    assert (note.kind, note.pitch, note.duration_beats, note.hidden) == (
        EventKind.NOTE,
        "F#4",
        Fraction(1, 4),
        False,
    )
    assert _undo(filled, edit).to_primitive() == score.to_primitive()


def test_a_shown_rest_in_the_gap() -> None:
    score = _score(TS03_VOICE)
    edit = _edit(score, _anchor(1), KIND, SHOWN_REST)
    shown = apply_edit(score, edit)
    rest = _events(shown)[1]
    assert (rest.kind, rest.pitch, rest.duration_beats, rest.hidden) == (
        EventKind.REST,
        None,
        Fraction(1, 4),
        False,
    )
    # Un silencio que se ve no serializa `hidden` (ADR-0032 §1).
    assert "hidden" not in rest.to_primitive()
    assert _undo(shown, edit).to_primitive() == score.to_primitive()


def test_filling_the_gap_moves_no_event_and_no_anchor() -> None:
    score = _score(TS03_VOICE)
    filled = apply_edit(score, _edit(score, _anchor(1), KIND, NOTE_F4))
    # Ningún ataque cambia: el hueco ya ocupaba su tiempo; solo cambia lo que es.
    before_map = compute_timing_map(score).events
    after_map = compute_timing_map(filled).events
    assert [(e.anchor, e.offset_beats, e.duration_beats) for e in before_map] == [
        (e.anchor, e.offset_beats, e.duration_beats) for e in after_map
    ]
    assert after_map[1].kind is EventKind.NOTE
    edit = _edit(score, _anchor(1), KIND, NOTE_F4)
    for index in range(len(TS03_VOICE)):
        assert translate_anchor(_anchor(index), 0, 1, [edit]) == _anchor(index)


def test_ts03_voice_is_corrected_with_a_fill_and_a_delete() -> None:
    score = _score(TS03_VOICE)
    filled = apply_edit(score, _edit(score, _anchor(1), KIND, NOTE_F4))
    # El segundo hueco sobra: se borra y Sol#4 vuelve a su sitio.
    deleted = apply_edit(filled, _edit(filled, _anchor(4), EditOp.DELETE_EVENT, None, seq=2))
    assert [(e.pitch, e.duration_beats) for e in _events(deleted)] == [
        ("G#4", Fraction(3, 4)),
        ("F#4", Fraction(1, 4)),
        ("F#4", Fraction(1, 2)),
        ("D5", Fraction(3, 4)),
        ("G#4", Fraction(1, 4)),
        ("G#4", Fraction(1, 2)),
    ]
    assert sum(e.duration_beats or 0 for e in _events(deleted)) == 3


def test_deleting_a_gap_keeps_it_hidden_on_undo() -> None:
    score = _score(TS03_VOICE)
    edit = _edit(score, _anchor(4), EditOp.DELETE_EVENT, None)
    assert edit.before is not None and edit.before["hidden"] is True
    deleted = apply_edit(score, edit)
    assert _undo(deleted, edit).to_primitive() == score.to_primitive()


def test_a_voice_that_starts_with_a_gap_is_written_from_it() -> None:
    # La voz inferior de la mano derecha del compás 2 de TS-03: un hueco de negra y un Mi4 que
    # HOMR puso ahí. Se escribe desde el hueco, en la segunda voz.
    score = _score(
        (
            _note("C#4", "1/2"),
            _note("E4", "1/2"),
            _rest(2),
            _gap(1, voice=1),
            _note("E4", "1/2", voice=1),
        )
    )
    after = {"kind": "note", "pitch": "C#4", "hidden": False}
    filled = apply_edit(score, _edit(score, _anchor(0, voice=1), KIND, after))
    lower = [e for e in _events(filled) if e.voice == 1]
    assert [(e.kind, e.pitch, e.duration_beats) for e in lower] == [
        (EventKind.NOTE, "C#4", Fraction(1)),
        (EventKind.NOTE, "E4", Fraction(1, 2)),
    ]


# --- Validación (ADR-0017) ---------------------------------------------------------------


def test_only_a_gap_changes_its_kind() -> None:
    score = _score((_note("C4"), _rest(1), _gap(1)))
    _rejected(score, _anchor(0), SHOWN_REST, "hueco")
    _rejected(score, _anchor(1), NOTE_F4, "hueco")
    # El hueco que sigue siendo hueco no cambia nada.
    _rejected(score, _anchor(2), GAP, "no cambia nada")


@pytest.mark.parametrize(
    ("after", "match"),
    [
        (None, "requiere"),
        ({"kind": "note", "pitch": "F#4"}, "hidden"),
        ({"kind": "note", "pitch": "F#4", "hidden": False, "tie": None}, "tie"),
        ({"kind": "chord", "pitch": None, "hidden": False}, "kind"),
        ({"kind": "note", "pitch": "fa#4", "hidden": False}, "altura"),
        ({"kind": "note", "pitch": None, "hidden": False}, "altura"),
        ({"kind": "note", "pitch": "F#4", "hidden": True}, "invisible"),
        ({"kind": "rest", "pitch": "F#4", "hidden": False}, "silencio no lleva"),
        ({"kind": "rest", "pitch": None, "hidden": 0}, "booleano"),
    ],
)
def test_the_after_has_exactly_kind_pitch_and_hidden(after: Any, match: str) -> None:
    _rejected(_score(TS03_VOICE), _anchor(1), after, match)


def test_the_anchor_must_exist() -> None:
    with pytest.raises(IndexError):
        validate_after(_score(TS03_VOICE), _anchor(9), KIND, NOTE_F4)


def test_a_note_in_the_gap_does_not_join_a_chord_note_that_follows_it() -> None:
    # Tras un silencio, una nota con `is_chord` empieza su propio grupo; si el hueco pasara a
    # ser una nota, se uniría a su acorde (ADR-0055 §2).
    score = _score((_gap(1), _note("E4", 1, is_chord=True), _note("G4", 1, is_chord=True)))
    _rejected(score, _anchor(0), NOTE_F4, "acorde")
    # Un silencio que se ve, sí.
    validate_after(score, _anchor(0), KIND, SHOWN_REST)


# --- Instantánea y compensatoria ---------------------------------------------------------


def test_has_complete_before_needs_kind_pitch_and_hidden() -> None:
    score = _score(TS03_VOICE)
    edit = _edit(score, _anchor(1), KIND, NOTE_F4)
    assert has_complete_before(edit)
    for missing in ("kind", "pitch", "hidden"):
        before = {key: value for key, value in GAP.items() if key != missing}
        incomplete = EditEvent(
            id="x",
            document_id="doc",
            seq=1,
            anchor=_anchor(1),
            op=KIND,
            author="ana",
            created_at=NOW,
            before=before,
            after=NOTE_F4,
        )
        assert not has_complete_before(incomplete)


def test_the_compensation_turns_the_note_back_into_the_gap_it_was() -> None:
    score = _score(TS03_VOICE)
    edit = _edit(score, _anchor(1), KIND, NOTE_F4)
    inverse = create_inverse_edit(edit, id="u", seq=2, author="ana", created_at=NOW)
    assert inverse.op is KIND
    assert inverse.before == NOTE_F4 and inverse.after == GAP
    # Rehacer reenvía el mismo `after` sobre el hueco que devolvió deshacer.
    back = apply_edit(apply_edit(score, edit), inverse)
    validate_after(back, _anchor(1), KIND, NOTE_F4)


def test_a_gap_with_a_figure_no_edit_admits_is_not_filled() -> None:
    # Un hueco importado de más de una longa: se acorta antes con su figura.
    score = _score((_gap(17), _note("C4", 1)))
    _rejected(score, _anchor(0), NOTE_F4, "figura del hueco")
    _rejected(score, _anchor(0), SHOWN_REST, "figura del hueco")


def test_the_marks_a_gap_brings_stay_with_the_event_and_undo_is_exact() -> None:
    # La importación conserva el calderón de un silencio invisible; la nota escrita lo conserva y
    # deshacer devuelve el hueco con él.
    score = _score((_note("C4", 2), _rest(1, hidden=True, fermata=True), _note("D4", 3)))
    edit = _edit(score, _anchor(1), KIND, NOTE_F4)
    filled = apply_edit(score, edit)
    assert _events(filled)[1].fermata is True
    assert _undo(filled, edit).to_primitive() == score.to_primitive()
