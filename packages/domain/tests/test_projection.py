"""Proyección del log de eventos sobre el `ScoreIR` (ADR-0007)."""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction

import pytest
from cadenza.domain import (
    Anchor,
    Clef,
    EditEvent,
    EditOp,
    Event,
    EventKind,
    KeySignature,
    Measure,
    Part,
    ScoreIR,
    Staff,
    TimeSignature,
    UnsupportedEditOpError,
    apply_edit,
    materialize,
)


def _score() -> ScoreIR:
    measure = Measure(
        number=1,
        events=(
            Event(kind=EventKind.NOTE, voice=0, pitch="C4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=0, pitch="D4", duration_beats=Fraction(1)),
        ),
        time_signature=TimeSignature(4, 4),
    )
    staff = Staff(id="part-0-staff-0", measures=(measure,))
    return ScoreIR(parts=(Part(id="part-0", staves=(staff,)),))


def _anchor(event_index: int = 0) -> Anchor:
    return Anchor(
        part=0,
        staff=0,
        measure=1,
        voice=0,
        event_index=event_index,
        staff_id="part-0-staff-0",
    )


def _edit(
    op: EditOp,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
    *,
    seq: int = 1,
    event_index: int = 0,
) -> EditEvent:
    return EditEvent(
        id=f"edit-{seq}",
        document_id="doc-1",
        seq=seq,
        anchor=_anchor(event_index),
        op=op,
        author="tester",
        created_at=datetime(2026, 9, 20, tzinfo=UTC),
        before=before,
        after=after,
    )


def _pitches(score: ScoreIR) -> list[str | None]:
    return [event.pitch for event in score.parts[0].staves[0].measures[0].events]


def test_set_pitch_updates_without_mutating_original() -> None:
    score = _score()
    updated = apply_edit(score, _edit(EditOp.SET_PITCH, {"pitch": "C4"}, {"pitch": "F#4"}))
    assert _pitches(updated) == ["F#4", "D4"]
    assert _pitches(score) == ["C4", "D4"]


def test_set_duration_updates_without_mutating_original() -> None:
    score = _score()
    updated = apply_edit(
        score,
        _edit(EditOp.SET_DURATION, {"duration_beats": "1"}, {"duration_beats": "2"}),
    )
    assert updated.parts[0].staves[0].measures[0].events[0].duration_beats == Fraction(2)
    assert score.parts[0].staves[0].measures[0].events[0].duration_beats == Fraction(1)


def test_materialize_applies_events_in_seq_order() -> None:
    score = _score()
    first = _edit(EditOp.SET_PITCH, {"pitch": "C4"}, {"pitch": "D4"}, seq=1)
    second = _edit(EditOp.SET_PITCH, {"pitch": "D4"}, {"pitch": "E4"}, seq=2)
    assert _pitches(materialize(score, [second, first])) == ["E4", "D4"]


def test_delete_event_removes_target() -> None:
    updated = apply_edit(_score(), _edit(EditOp.DELETE_EVENT, {"pitch": "C4"}, None))
    assert _pitches(updated) == ["D4"]


def test_insert_event_adds_target() -> None:
    edit = _edit(
        EditOp.INSERT_EVENT,
        None,
        {"kind": "note", "pitch": "A4", "duration_beats": "2"},
    )
    updated = apply_edit(_score(), edit)
    assert _pitches(updated) == ["A4", "C4", "D4"]


def test_set_clef_updates_measure_without_mutating_original() -> None:
    score = _score()
    edit = _edit(EditOp.SET_CLEF, None, {"clef": {"sign": "F", "line": 4}})
    updated = apply_edit(score, edit)
    assert updated.parts[0].staves[0].measures[0].clef == Clef.bass()
    assert score.parts[0].staves[0].measures[0].clef is None


def test_set_clef_supports_named_strings_and_primitives() -> None:
    score = _score()
    updated_treble = apply_edit(score, _edit(EditOp.SET_CLEF, None, {"clef": "treble"}))
    assert updated_treble.parts[0].staves[0].measures[0].clef == Clef.treble()

    updated_alto = apply_edit(score, _edit(EditOp.SET_CLEF, None, {"clef": "alto"}))
    assert updated_alto.parts[0].staves[0].measures[0].clef == Clef.alto()


def test_set_key_updates_measure_without_mutating_original() -> None:
    score = _score()
    edit = _edit(
        EditOp.SET_KEY,
        None,
        {"key_signature": {"fifths": 2, "mode": "major"}},
    )
    updated = apply_edit(score, edit)
    assert updated.parts[0].staves[0].measures[0].key_signature == KeySignature(2, "major")
    assert score.parts[0].staves[0].measures[0].key_signature is None


def test_set_key_supports_fifths_primitive_and_integer() -> None:
    score = _score()
    updated_flats = apply_edit(score, _edit(EditOp.SET_KEY, None, {"fifths": -3}))
    assert updated_flats.parts[0].staves[0].measures[0].key_signature == KeySignature(-3, None)


def test_set_accidental_updates_pitch_preserving_letter_and_octave() -> None:
    score = _score()
    # C4 con '#' -> C#4
    up_sharp = apply_edit(score, _edit(EditOp.SET_ACCIDENTAL, None, {"accidental": "#"}))
    assert _pitches(up_sharp) == ["C#4", "D4"]
    assert _pitches(score) == ["C4", "D4"]

    # D4 (index 1) con 'b' -> Db4
    up_flat = apply_edit(
        score,
        _edit(EditOp.SET_ACCIDENTAL, None, {"accidental": "b"}, event_index=1),
    )
    assert _pitches(up_flat) == ["C4", "Db4"]

    # F#4 con natural -> F4
    score_sharp = apply_edit(score, _edit(EditOp.SET_PITCH, None, {"pitch": "F#4"}))
    up_natural = apply_edit(
        score_sharp,
        _edit(EditOp.SET_ACCIDENTAL, None, {"accidental": "natural"}),
    )
    assert _pitches(up_natural) == ["F4", "D4"]

    # Eb5 con '#' -> E#5
    score_eb5 = apply_edit(score, _edit(EditOp.SET_PITCH, None, {"pitch": "Eb5"}))
    up_sharp5 = apply_edit(
        score_eb5,
        _edit(EditOp.SET_ACCIDENTAL, None, {"accidental": "sharp"}),
    )
    assert _pitches(up_sharp5) == ["E#5", "D4"]

    # Doble sostenido '##' y doble bemol 'bb'
    up_dbl_sharp = apply_edit(
        score,
        _edit(EditOp.SET_ACCIDENTAL, None, {"accidental": "##"}),
    )
    assert _pitches(up_dbl_sharp) == ["C##4", "D4"]

    up_dbl_flat = apply_edit(
        score,
        _edit(EditOp.SET_ACCIDENTAL, None, {"accidental": "bb"}),
    )
    assert _pitches(up_dbl_flat) == ["Cbb4", "D4"]


def test_set_accidental_on_rest_raises_value_error() -> None:
    measure = Measure(
        number=1,
        events=(Event(kind=EventKind.REST, voice=0, duration_beats=Fraction(1)),),
    )
    score = ScoreIR(parts=(Part(id="p0", staves=(Staff(id="s0", measures=(measure,)),)),))
    with pytest.raises(ValueError, match="without pitch"):
        apply_edit(score, _edit(EditOp.SET_ACCIDENTAL, None, {"accidental": "#"}))


def test_materialize_combines_insert_delete_accidental_clef_and_key() -> None:
    score = _score()  # C4, D4 en compás 1
    events = [
        _edit(
            EditOp.INSERT_EVENT,
            None,
            {"kind": "note", "pitch": "B3", "duration_beats": "1"},
            seq=1,
            event_index=0,
        ),  # -> B3, C4, D4
        _edit(
            EditOp.SET_ACCIDENTAL,
            None,
            {"accidental": "#"},
            seq=2,
            event_index=0,
        ),  # B3 -> B#3
        _edit(
            EditOp.DELETE_EVENT,
            None,
            None,
            seq=3,
            event_index=2,
        ),  # borra D4 -> B#3, C4
        _edit(
            EditOp.SET_CLEF,
            None,
            {"clef": "bass"},
            seq=4,
        ),
        _edit(
            EditOp.SET_KEY,
            None,
            {"fifths": 3, "mode": "major"},
            seq=5,
        ),
    ]

    materialized = materialize(score, events)
    meas = materialized.parts[0].staves[0].measures[0]
    assert [e.pitch for e in meas.events] == ["B#3", "C4"]
    assert meas.clef == Clef.bass()
    assert meas.key_signature == KeySignature(3, "major")
    # Original intacto
    assert _pitches(score) == ["C4", "D4"]
    assert score.parts[0].staves[0].measures[0].clef is None


def test_unsupported_op_is_explicit() -> None:
    from typing import cast

    invalid_op = cast(EditOp, "InvalidOp")
    with pytest.raises(UnsupportedEditOpError):
        apply_edit(_score(), _edit(invalid_op, None, {}))
