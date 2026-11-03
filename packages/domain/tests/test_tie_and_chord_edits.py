"""Ligaduras de prolongación y notas de un acorde (ADR-0055, #312, D61).

- `SetTie`, de tipo «fijar», pone o quita la ligadura de prolongación entre una nota y la que la
  sigue (también al cruzar la barra), o quita la marca suelta de una nota; `before` es la
  instantánea del servidor y la compensatoria intercambia `before` y `after`.
- Añadir una nota a un acorde es un `InsertEvent` con `is_chord`, justo tras otra nota; un evento
  sin `is_chord` no parte un acorde.
- La primera nota de un acorde se borra con `DeleteEvent` y `after: {"keep_chord": true}`: la
  siguiente pasa a ser la primera, con la figura y las marcas del acorde, y deshacer la devuelve.
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
    Articulation,
    EditEvent,
    EditOp,
    Event,
    EventKind,
    InvalidEditPayload,
    Measure,
    Part,
    ScoreIR,
    Slur,
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
TIE = EditOp.SET_TIE


def _note(pitch: str, beats: Fraction | int | str | None = 1, **kwargs: Any) -> Event:
    duration = None if beats is None else Fraction(beats)
    return Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=duration, **kwargs)


def _rest(beats: Fraction | int = 1, **kwargs: Any) -> Event:
    return Event(kind=EventKind.REST, duration_beats=Fraction(beats), **kwargs)


def _score(*measures: tuple[Event, ...]) -> ScoreIR:
    built = tuple(
        Measure(number=number, events=events, time_signature=TimeSignature(4, 4))
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


def _ties(score: ScoreIR, measure: int = 1) -> list[str | None]:
    return [None if e.tie is None else e.tie.value for e in _events(score, measure)]


def _next(event_index: int, tie: str | None, *, measure: int = 1, voice: int = 0) -> dict[str, Any]:
    return {"measure": measure, "voice": voice, "event_index": event_index, "tie": tie}


def _rejected(score: ScoreIR, anchor: Anchor, op: EditOp, after: Any, match: str) -> None:
    with pytest.raises(InvalidEditPayload, match=match):
        validate_after(score, anchor, op, after)


# --- La política de EditOp ---------------------------------------------------------------


def test_set_tie_is_a_meter_op_and_content_stays_at_seven() -> None:
    assert TIE.value == "SetTie"
    assert TIE in METER_EDIT_OPS
    assert TIE not in CONTENT_EDIT_OPS and TIE not in MARK_EDIT_OPS
    # Y los huecos de una voz, la suya (ADR-0058, `test_gap_edits.py`).
    assert set(EditOp) == CONTENT_EDIT_OPS | MARK_EDIT_OPS | METER_EDIT_OPS | GAP_EDIT_OPS
    # Añadir y quitar notas de un acorde son InsertEvent y DeleteEvent: la cobertura de exp_02
    # sigue siendo sobre siete operaciones (ADR-0039 §3, ADR-0055 §4).
    assert len(CONTENT_EDIT_OPS) == 7


# --- SetTie: poner y quitar la ligadura --------------------------------------------------

# Do4 negra, Do4 negra, Re4 blanca.
REPEATED = (_note("C4"), _note("C4"), _note("D4", 2))


def test_one_edit_ties_two_notes_and_one_undo_unties_them() -> None:
    score = _score(REPEATED)
    after = {"tie": "start", "next": _next(1, "stop")}
    edit = _edit(score, _anchor(0), TIE, after)
    # La instantánea tiene la forma del `after`, con los valores que había.
    assert edit.before == {"tie": None, "next": _next(1, None)}
    tied = apply_edit(score, edit)
    assert _ties(tied) == ["start", "stop", None]
    assert _undo(tied, edit).to_primitive() == score.to_primitive()
    # Quitarla es otra SetTie, también de un paso.
    untie = _edit(tied, _anchor(0), TIE, {"tie": None, "next": _next(1, None)}, seq=2)
    assert untie.before == after
    assert apply_edit(tied, untie).to_primitive() == score.to_primitive()


def test_a_tie_crosses_the_barline_into_another_voice() -> None:
    # Al cruzar la barra, las voces se numeran de nuevo (ADR-0032 §3): el Do4 del compás 2 está
    # en la voz 1, tras la que empieza con un silencio en la voz 0.
    score = _score(
        (_note("E4", 3), _note("C4")),
        (_rest(2), _rest(2), _note("C4", 4, voice=1)),
    )
    after = {"tie": "start", "next": _next(0, "stop", measure=2, voice=1)}
    tied = apply_edit(score, _edit(score, _anchor(1), TIE, after))
    assert _ties(tied, 1) == [None, "start"]
    assert _ties(tied, 2) == [None, None, "stop"]


def test_a_chain_of_ties_continues() -> None:
    score = _score((_note("C4", tie=Tie.STOP), _note("C4", tie=Tie.START), _note("D4", 2)))
    # El primero ya recibe una ligadura y el segundo ya empieza otra: los dos pasan a continuar.
    after = {"tie": "continue", "next": _next(1, "continue")}
    tied = apply_edit(score, _edit(score, _anchor(0), TIE, after))
    assert _ties(tied) == ["continue", "continue", None]


def test_a_tie_joins_two_notes_of_two_chords() -> None:
    chords = (
        _note("C4"),
        _note("E4", is_chord=True),
        _note("C4"),
        _note("E4", is_chord=True),
        _note("D4", 2),
    )
    score = _score(chords)
    # El Mi del primer acorde (que no es su primera nota) con el Mi del segundo.
    after = {"tie": "start", "next": _next(3, "stop")}
    tied = apply_edit(score, _edit(score, _anchor(1), TIE, after))
    assert _ties(tied) == [None, "start", None, "stop", None]


def test_the_next_note_skips_grace_notes() -> None:
    score = _score((_note("C4"), _note("B3", None), _note("C4"), _note("D4", 2)))
    after = {"tie": "start", "next": _next(2, "stop")}
    tied = apply_edit(score, _edit(score, _anchor(0), TIE, after))
    assert _ties(tied) == ["start", None, "stop", None]


def test_removing_a_tie_does_not_need_the_same_pitch() -> None:
    # La segunda nota se corrigió después de ligarlas: la ligadura se quita igual.
    score = _score((_note("C4", tie=Tie.START), _note("D4", tie=Tie.STOP), _note("E4", 2)))
    after = {"tie": None, "next": _next(1, None)}
    untied = apply_edit(score, _edit(score, _anchor(0), TIE, after))
    assert _ties(untied) == [None, None, None]


def test_a_lone_mark_is_removed_without_the_other_note() -> None:
    # Una ligadura que no llega a ninguna nota (lo que señala `tie.resolution`).
    score = _score((_note("C4", tie=Tie.START), _note("D4"), _note("E4", 2)))
    edit = _edit(score, _anchor(0), TIE, {"tie": None, "next": None})
    assert edit.before == {"tie": "start", "next": None}
    untied = apply_edit(score, edit)
    assert _ties(untied) == [None, None, None]
    assert _undo(untied, edit).to_primitive() == score.to_primitive()
    # Y una que llega sin salir de ninguna: se quita su marca de llegada y se conserva la otra.
    chained = _score((_note("D4"), _note("C4", tie=Tie.CONTINUE), _note("C4", 2, tie=Tie.STOP)))
    kept = apply_edit(chained, _edit(chained, _anchor(1), TIE, {"tie": "start", "next": None}))
    assert _ties(kept) == [None, "start", "stop"]


def test_set_tie_moves_no_anchor() -> None:
    score = _score(REPEATED)
    edit = _edit(score, _anchor(0), TIE, {"tie": "start", "next": _next(1, "stop")})
    assert translate_anchor(_anchor(2), 0, 1, [edit]) == _anchor(2)


def test_set_tie_has_a_complete_before() -> None:
    score = _score(REPEATED)
    edit = _edit(score, _anchor(0), TIE, {"tie": "start", "next": _next(1, "stop")})
    assert has_complete_before(edit)
    incomplete = EditEvent(
        id="x",
        document_id="doc",
        seq=1,
        anchor=_anchor(0),
        op=TIE,
        author="ana",
        created_at=NOW,
        before={"tie": None},
        after={"tie": "start", "next": None},
    )
    assert not has_complete_before(incomplete)


@pytest.mark.parametrize(
    ("after", "match"),
    [
        (None, "requiere un objeto"),
        ({"tie": "start"}, "exactamente"),
        ({"tie": "start", "next": None, "extra": 1}, "exactamente"),
        ({"tie": "tied", "next": None}, "'tie'"),
        ({"tie": "start", "next": {"measure": 1, "voice": 0, "event_index": 1}}, "'next'"),
        ({"tie": "start", "next": {**_next(1, "stop"), "staff": 0}}, "'next'"),
        ({"tie": "start", "next": _next(True, "stop")}, "'event_index'"),
        ({"tie": "start", "next": _next(1, "begin")}, "'tie'"),
    ],
)
def test_set_tie_rejects_malformed_after(after: Any, match: str) -> None:
    _rejected(_score(REPEATED), _anchor(0), TIE, after, match)


def test_set_tie_rejects_ties_that_are_not_between_a_note_and_the_next() -> None:
    score = _score(REPEATED, (_note("D4", 2), _note("C4", 2)))
    anchor = _anchor(0)
    # Notas de distinta altura.
    _rejected(score, _anchor(1), TIE, {"tie": "start", "next": _next(2, "stop")}, "misma altura")
    # Una nota que no es la siguiente: dos grupos más allá.
    _rejected(score, anchor, TIE, {"tie": "start", "next": _next(2, "stop")}, "no es lo que sigue")
    # A la barra solo llega la última de su voz.
    far = {"tie": "start", "next": _next(1, "stop", measure=2)}
    _rejected(score, anchor, TIE, far, "no es lo que sigue")
    # Ni a una nota que no empieza el compás siguiente.
    late = {"tie": "start", "next": _next(1, "stop", measure=2)}
    _rejected(score, _anchor(2), TIE, late, "no es lo que sigue")
    # La otra nota no existe.
    _rejected(score, anchor, TIE, {"tie": "start", "next": _next(5, "stop")}, "no existe")
    _rejected(
        score, anchor, TIE, {"tie": "start", "next": _next(0, "stop", measure=9)}, "no existe"
    )
    # Poner una ligadura sola, sin la otra nota.
    _rejected(score, anchor, TIE, {"tie": "start", "next": None}, "solo quita")
    # Lo que ya está.
    _rejected(score, anchor, TIE, {"tie": None, "next": _next(1, None)}, "nada")
    _rejected(score, anchor, TIE, {"tie": None, "next": None}, "nada")


def test_set_tie_only_changes_the_marks_of_the_tie_between_the_two_notes() -> None:
    score = _score(REPEATED)
    anchor = _anchor(0)
    # La nota del ancla no gana una llegada ni la otra una salida.
    _rejected(score, anchor, TIE, {"tie": "continue", "next": _next(1, "stop")}, "llega")
    _rejected(score, anchor, TIE, {"tie": "start", "next": _next(1, "continue")}, "sale")
    # Las dos mitades de la ligadura cambian a la vez.
    _rejected(score, anchor, TIE, {"tie": "start", "next": _next(1, None)}, "las dos")
    _rejected(score, anchor, TIE, {"tie": None, "next": _next(1, "stop")}, "las dos")


def test_set_tie_rejects_rests_and_grace_notes() -> None:
    score = _score((_rest(), _note("C4"), _note("C4", None), _note("C4"), _note("C4")))
    # El ancla en un silencio.
    _rejected(score, _anchor(0), TIE, {"tie": "start", "next": _next(1, "stop")}, "nota")
    # Una nota de adorno no se liga.
    _rejected(score, _anchor(2), TIE, {"tie": "start", "next": _next(3, "stop")}, "adorno")
    # Ni la ligadura llega a un silencio.
    rest_next = _score((_note("C4"), _rest(), _note("C4", 2)))
    _rejected(rest_next, _anchor(0), TIE, {"tie": "start", "next": _next(1, "stop")}, "nota")


def test_set_tie_reports_a_missing_anchor_as_an_index_error() -> None:
    with pytest.raises(IndexError):
        validate_after(_score(REPEATED), _anchor(7), TIE, {"tie": None, "next": None})


# --- Añadir una nota a un acorde: InsertEvent con is_chord ------------------------------

TRIAD = (
    _note("C4", articulations=(Articulation.ACCENT,), fermata=True),
    _note("E4", is_chord=True),
    _note("G4", is_chord=True),
    _note("D4"),
    _note("F4", 2),
)


def _chord_note(pitch: str, beats: str = "1") -> dict[str, Any]:
    return {"kind": "note", "pitch": pitch, "duration_beats": beats, "is_chord": True}


def test_a_note_is_added_to_a_chord_after_its_last_note_and_undone_in_one_step() -> None:
    score = _score(TRIAD)
    edit = _edit(score, _anchor(3), EditOp.INSERT_EVENT, _chord_note("B4"))
    grown = apply_edit(score, edit)
    events = _events(grown)
    assert [e.pitch for e in events] == ["C4", "E4", "G4", "B4", "D4", "F4"]
    assert [e.is_chord for e in events] == [False, True, True, True, False, False]
    # Suena con el acorde y el Re sigue en el tiempo 2.
    timings = {t.anchor.event_index: t for t in compute_timing_map(grown).events}
    assert [timings[i].offset_beats for i in range(4)] == [0, 0, 0, 0]
    assert timings[4].offset_beats == 1
    assert _undo(grown, edit).to_primitive() == score.to_primitive()


def test_a_note_added_to_a_lone_note_forms_a_chord() -> None:
    score = _score(TRIAD)
    formed = apply_edit(score, _edit(score, _anchor(4), EditOp.INSERT_EVENT, _chord_note("F4")))
    assert [(e.pitch, e.is_chord) for e in _events(formed)][3:5] == [("D4", False), ("F4", True)]


def test_a_chord_note_goes_right_after_another_note() -> None:
    score = _score((_rest(), _note("C4"), _note("D4", 2)))
    _rejected(score, _anchor(0), EditOp.INSERT_EVENT, _chord_note("E4"), "tras otra nota")
    _rejected(score, _anchor(1), EditOp.INSERT_EVENT, _chord_note("E4"), "tras otra nota")


def test_an_event_without_is_chord_does_not_split_a_chord() -> None:
    score = _score(TRIAD)
    note = {"kind": "note", "pitch": "A4", "duration_beats": "1"}
    rest = {"kind": "rest", "duration_beats": "1"}
    for index in (1, 2):
        _rejected(score, _anchor(index), EditOp.INSERT_EVENT, note, "partiría el acorde")
        _rejected(score, _anchor(index), EditOp.INSERT_EVENT, rest, "partiría el acorde")
    # Antes del acorde entero, y tras él, sí (ADR-0033 §3).
    validate_after(score, _anchor(0), EditOp.INSERT_EVENT, note)
    validate_after(score, _anchor(3), EditOp.INSERT_EVENT, rest)


def test_a_client_does_not_send_the_chord_restoration_of_an_undo() -> None:
    after = {**_chord_note("B4"), "is_chord": False, "next_in_chord": {"duration_beats": "1"}}
    _rejected(_score(TRIAD), _anchor(0), EditOp.INSERT_EVENT, after, "compensatoria")


# --- Quitar la primera nota de un acorde: DeleteEvent con keep_chord --------------------

KEEP = {"keep_chord": True}


def test_the_first_note_of_a_chord_is_removed_and_the_next_keeps_the_chord() -> None:
    score = _score(TRIAD)
    edit = _edit(score, _anchor(0), EditOp.DELETE_EVENT, KEEP)
    # La instantánea guarda la nota borrada y lo que tenía la siguiente como nota del acorde.
    assert edit.before is not None
    assert edit.before["pitch"] == "C4"
    assert edit.before["articulations"] == ["accent"]
    assert edit.before["next_in_chord"] == {
        "duration_beats": "1",
        "articulations": [],
        "fermata": False,
        "slurs": [],
    }
    assert has_complete_before(edit)
    removed = apply_edit(score, edit)
    events = _events(removed)
    assert [e.pitch for e in events] == ["E4", "G4", "D4", "F4"]
    assert [e.is_chord for e in events] == [False, True, False, False]
    # La nueva primera nota lleva las marcas del acorde.
    assert events[0].articulations == (Articulation.ACCENT,) and events[0].fermata
    # El acorde sigue sonando entero en el tiempo 1, y el Re en el 2.
    timings = {t.anchor.event_index: t for t in compute_timing_map(removed).events}
    assert [timings[i].offset_beats for i in range(3)] == [0, 0, 1]
    # Deshacer lo devuelve exacto: la compensatoria es un InsertEvent con la instantánea.
    inverse = create_inverse_edit(edit, id="u", seq=2, author="ana", created_at=NOW)
    assert inverse.op is EditOp.INSERT_EVENT
    assert apply_edit(removed, inverse).to_primitive() == score.to_primitive()


def test_removing_the_first_of_two_notes_leaves_a_note_with_the_chord_figure_and_marks() -> None:
    slur = Slur.from_primitive({"type": "start", "number": 1})
    score = _score(
        (
            _note("C4", 2, slurs=(slur,)),
            _note("E4", 1, is_chord=True, tie=Tie.START),
            _note("E4", 2, slurs=(Slur.from_primitive({"type": "stop", "number": 1}),)),
        )
    )
    edit = _edit(score, _anchor(0), EditOp.DELETE_EVENT, KEEP)
    removed = apply_edit(score, edit)
    head = _events(removed)[0]
    # La que queda lleva la figura del acorde (una blanca), su ligadura de expresión y su propia
    # ligadura de prolongación.
    assert (head.pitch, head.is_chord, head.duration_beats) == ("E4", False, Fraction(2))
    assert head.slurs == (slur,) and head.tie is Tie.START
    assert _undo(removed, edit).to_primitive() == score.to_primitive()


def test_keep_chord_moves_anchors_like_any_delete() -> None:
    score = _score(TRIAD)
    edit = _edit(score, _anchor(0), EditOp.DELETE_EVENT, KEEP)
    # La nota borrada desaparece y las siguientes adelantan una posición (ADR-0011 §2).
    assert translate_anchor(_anchor(0), 0, 1, [edit]) is None
    assert translate_anchor(_anchor(1), 0, 1, [edit]) == _anchor(0)
    assert translate_anchor(_anchor(3), 0, 1, [edit]) == _anchor(2)


def test_keep_chord_is_only_for_the_first_note_of_a_chord() -> None:
    score = _score((*TRIAD, _rest()))
    for index, match in ((1, "primera nota de un acorde"), (3, "primera nota de un acorde")):
        _rejected(score, _anchor(index), EditOp.DELETE_EVENT, KEEP, match)
    _rejected(score, _anchor(5), EditOp.DELETE_EVENT, KEEP, "primera nota de un acorde")
    for after in ({"keep_chord": False}, {"keep_chord": 1}, {"keep_chord": True, "x": 1}, {}):
        _rejected(score, _anchor(0), EditOp.DELETE_EVENT, after, "keep_chord")


def test_the_first_note_of_a_chord_is_not_deleted_without_keep_chord() -> None:
    score = _score(TRIAD)
    _rejected(score, _anchor(0), EditOp.DELETE_EVENT, None, "keep_chord")
    # Las demás notas del acorde se borran como siempre.
    validate_after(score, _anchor(1), EditOp.DELETE_EVENT, None)
    validate_after(score, _anchor(3), EditOp.DELETE_EVENT, None)


def test_a_keep_chord_delete_needs_the_next_note_in_its_before() -> None:
    score = _score(TRIAD)
    edit = _edit(score, _anchor(0), EditOp.DELETE_EVENT, KEEP)
    assert edit.before is not None
    before = {key: value for key, value in edit.before.items() if key != "next_in_chord"}
    incomplete = EditEvent(
        id="x",
        document_id="doc",
        seq=1,
        anchor=_anchor(0),
        op=EditOp.DELETE_EVENT,
        author="ana",
        created_at=NOW,
        before=before,
        after=KEEP,
    )
    assert not has_complete_before(incomplete)


# --- Lo que señaló la revisión -----------------------------------------------------------


def test_a_lone_mark_with_a_partner_is_removed_with_it() -> None:
    # Sin `next` solo se quita una marca suelta: si la ligadura tiene pareja, se quita con ella.
    score = _score((_note("C4", tie=Tie.START), _note("C4", tie=Tie.STOP), _note("E4", 2)))
    _rejected(score, _anchor(0), TIE, {"tie": None, "next": None}, "llega a otra")
    _rejected(score, _anchor(1), TIE, {"tie": None, "next": None}, "sale de otra")


def test_trailing_hidden_rests_do_not_stop_a_tie_crossing_the_barline() -> None:
    # Como en `tie.resolution`: tras el hueco del final de la voz no hay nada.
    score = _score(
        (_note("C4", 2), _rest(2, hidden=True)),
        (_note("C4", 4),),
    )
    after = {"tie": "start", "next": _next(0, "stop", measure=2)}
    tied = apply_edit(score, _edit(score, _anchor(0), TIE, after))
    assert _ties(tied, 2) == ["stop"]


def test_a_chord_note_is_not_added_to_a_grace_note_nor_carries_marks() -> None:
    grace = _score((_note("C4", None), _note("D4", 4)))
    _rejected(grace, _anchor(1), EditOp.INSERT_EVENT, _chord_note("E4"), "adorno")
    score = _score(TRIAD)
    for marks in ({"articulations": ["accent"]}, {"fermata": True}):
        after = {**_chord_note("B4"), **marks}
        _rejected(score, _anchor(3), EditOp.INSERT_EVENT, after, "primera nota")
