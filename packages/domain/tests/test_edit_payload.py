"""Contenido de las ediciones: validación de `after` y estado previo fijado por el servidor (#117).

ADR-0017: el servidor rechaza un `after` incoherente con su operación y guarda en
`before` una instantánea del estado, de modo que deshacer restaure el estado exacto.
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
    has_complete_before,
    is_canonical_pitch,
    normalize_accidental,
    snapshot_before,
    validate_after,
)


def _score() -> ScoreIR:
    first = Measure(
        number=1,
        events=(
            Event(
                kind=EventKind.NOTE,
                pitch="C#4",
                duration_beats=Fraction(1),
                tie=Tie.START,
                bbox=(20.0, 40.0, 36.0, 60.0),
                confidence=0.9,
            ),
            Event(kind=EventKind.REST, duration_beats=Fraction(3)),
        ),
        time_signature=TimeSignature(4, 4),
        clef=Clef.treble(),
        key_signature=KeySignature(fifths=2, mode="major"),
    )
    second = Measure(number=2, events=(Event(kind=EventKind.NOTE, pitch="E4"),))
    return ScoreIR(parts=(Part(id="p0", staves=(Staff(id="s0", measures=(first, second)),)),))


def _anchor(measure: int = 1, event_index: int = 0) -> Anchor:
    return Anchor(part=0, staff=0, measure=measure, voice=0, event_index=event_index, staff_id="s0")


NOTE = _anchor(event_index=0)
REST = _anchor(event_index=1)


# --- Alturas canónicas ------------------------------------------------------


@pytest.mark.parametrize("pitch", ["C4", "C#4", "C##4", "Bb3", "Ebb5", "A0", "G9", "Cb0"])
def test_canonical_pitches_are_accepted(pitch: str) -> None:
    assert is_canonical_pitch(pitch)


@pytest.mark.parametrize(
    "pitch",
    ["H9", "c4", "Cx4", "C-4", "C10", "C-1", "G#9", "B9", "C", "4", "", " C4", None, 60],
)
def test_non_canonical_pitches_are_rejected(pitch: object) -> None:
    assert not is_canonical_pitch(pitch)


# --- Validación de `after` por operación -------------------------------------


VALID_AFTER: list[tuple[EditOp, Anchor, dict[str, Any] | None]] = [
    (EditOp.SET_PITCH, NOTE, {"pitch": "D4"}),
    (EditOp.SET_PITCH, NOTE, {"pitch": "Bb3"}),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": "1/2"}),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": 2}),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": 0.5}),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": "1/3"}),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": "3/4"}),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": "1/96"}),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": "1/128"}),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": 16}),
    (EditOp.SET_DURATION, REST, {"duration_beats": "3/2"}),
    (EditOp.SET_ACCIDENTAL, NOTE, {"accidental": "b"}),
    (EditOp.SET_ACCIDENTAL, NOTE, {"accidental": None}),
    (EditOp.SET_ACCIDENTAL, NOTE, {"accidental": "natural"}),
    (EditOp.SET_ACCIDENTAL, NOTE, {"accidental": "##"}),
    (EditOp.INSERT_EVENT, NOTE, {"kind": "note", "pitch": "G4", "duration_beats": "1"}),
    (EditOp.INSERT_EVENT, _anchor(event_index=2), {"kind": "rest", "duration_beats": 1}),
    (
        EditOp.INSERT_EVENT,
        NOTE,
        {"kind": "note", "voice": 0, "pitch": "G4", "duration_beats": "1"},
    ),
    (
        EditOp.INSERT_EVENT,
        NOTE,
        {
            "kind": "note",
            "pitch": "G4",
            "duration_beats": "1/2",
            "tie": "stop",
            "is_chord": False,
            "bbox": [1, 2, 3, 4],
            "confidence": 0.5,
        },
    ),
    (EditOp.DELETE_EVENT, NOTE, None),
    (EditOp.SET_CLEF, NOTE, {"sign": "F", "line": 4}),
    (EditOp.SET_CLEF, NOTE, {"sign": "G", "line": 2, "octave_change": -1}),
    (EditOp.SET_CLEF, NOTE, {"clef": "bass"}),
    (EditOp.SET_CLEF, NOTE, {"clef": {"sign": "C", "line": 3}}),
    (EditOp.SET_CLEF, NOTE, {"clef": None}),
    (EditOp.SET_KEY, NOTE, {"fifths": -3}),
    (EditOp.SET_KEY, NOTE, {"fifths": 1, "mode": "minor"}),
    (EditOp.SET_KEY, NOTE, {"key_signature": {"fifths": 7}}),
    (EditOp.SET_KEY, NOTE, {"key_signature": None}),
]


@pytest.mark.parametrize(("op", "anchor", "after"), VALID_AFTER)
def test_valid_after_is_accepted_and_applicable(
    op: EditOp, anchor: Anchor, after: dict[str, Any] | None
) -> None:
    score = _score()
    validate_after(score, anchor, op, after)
    edit = EditEvent(
        id="e1",
        document_id="d1",
        seq=1,
        anchor=anchor,
        op=op,
        author="t",
        created_at=datetime.now(UTC),
        after=after,
    )
    apply_edit(score, edit)


INVALID_AFTER: list[tuple[EditOp, Anchor, dict[str, Any] | None]] = [
    (EditOp.SET_PITCH, NOTE, {}),
    (EditOp.SET_PITCH, NOTE, None),
    (EditOp.SET_PITCH, NOTE, {"pitch": None}),
    (EditOp.SET_PITCH, NOTE, {"pitch": "H9"}),
    (EditOp.SET_PITCH, NOTE, {"pitch": "c4"}),
    (EditOp.SET_PITCH, NOTE, {"pitch": "D4", "duration_beats": "1"}),
    (EditOp.SET_PITCH, REST, {"pitch": "D4"}),
    (EditOp.SET_DURATION, NOTE, {}),
    (EditOp.SET_DURATION, NOTE, None),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": None}),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": 0}),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": "-1/2"}),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": "abc"}),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": True}),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": float("nan")}),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": 17}),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": "1e30"}),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": 10**400}),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": "1/17"}),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": "3/1000"}),
    (EditOp.SET_DURATION, NOTE, {"duration_beats": "1/256"}),
    (EditOp.SET_ACCIDENTAL, NOTE, {}),
    (EditOp.SET_ACCIDENTAL, NOTE, None),
    (EditOp.SET_ACCIDENTAL, NOTE, {"accidental": "###"}),
    (EditOp.SET_ACCIDENTAL, NOTE, {"accidental": 1}),
    (EditOp.SET_ACCIDENTAL, NOTE, {"accidental": "sharp"}),
    (EditOp.SET_ACCIDENTAL, NOTE, {"accidental": ["#"]}),
    (EditOp.SET_ACCIDENTAL, REST, {"accidental": "#"}),
    (EditOp.INSERT_EVENT, NOTE, None),
    (EditOp.INSERT_EVENT, NOTE, {}),
    (EditOp.INSERT_EVENT, NOTE, {"pitch": "G4", "duration_beats": "1"}),
    (EditOp.INSERT_EVENT, NOTE, {"kind": "clef", "duration_beats": "1"}),
    (EditOp.INSERT_EVENT, NOTE, {"kind": "note", "duration_beats": "1"}),
    (EditOp.INSERT_EVENT, NOTE, {"kind": "note", "pitch": "Z4", "duration_beats": "1"}),
    (EditOp.INSERT_EVENT, NOTE, {"kind": "note", "pitch": "G4"}),
    (EditOp.INSERT_EVENT, NOTE, {"kind": "rest", "pitch": "G4", "duration_beats": "1"}),
    (EditOp.INSERT_EVENT, NOTE, {"kind": "rest", "duration_beats": "1", "tie": "start"}),
    (EditOp.INSERT_EVENT, NOTE, {"kind": "note", "pitch": "G4", "duration_beats": "1", "x": 1}),
    (EditOp.INSERT_EVENT, NOTE, {"kind": "note", "voice": 1, "pitch": "G4", "duration_beats": 1}),
    (EditOp.INSERT_EVENT, NOTE, {"kind": "note", "pitch": "G4", "duration_beats": 1, "tie": "x"}),
    (EditOp.INSERT_EVENT, NOTE, {"kind": "note", "pitch": "G4", "duration_beats": 1, "bbox": [1]}),
    (
        EditOp.INSERT_EVENT,
        NOTE,
        {"kind": "note", "pitch": "G4", "duration_beats": 1, "confidence": 2},
    ),
    (EditOp.INSERT_EVENT, NOTE, {"kind": "rest", "duration_beats": 100000}),
    (EditOp.INSERT_EVENT, NOTE, {"kind": "note", "pitch": "C4", "duration_beats": 1, "tie": []}),
    (
        EditOp.INSERT_EVENT,
        NOTE,
        {"kind": "note", "pitch": "C4", "duration_beats": 1, "bbox": [10**400, 0, 1, 1]},
    ),
    (
        EditOp.INSERT_EVENT,
        NOTE,
        {"kind": "note", "pitch": "C4", "duration_beats": 1, "confidence": 10**400},
    ),
    (EditOp.INSERT_EVENT, NOTE, {"kind": [], "duration_beats": 1}),
    (EditOp.DELETE_EVENT, NOTE, {}),
    (EditOp.DELETE_EVENT, NOTE, {"pitch": "C4"}),
    (EditOp.SET_CLEF, NOTE, None),
    (EditOp.SET_CLEF, NOTE, {}),
    (EditOp.SET_CLEF, NOTE, {"sign": "X", "line": 2}),
    (EditOp.SET_CLEF, NOTE, {"sign": "G", "line": 9}),
    (EditOp.SET_CLEF, NOTE, {"sign": "G", "line": "2"}),
    (EditOp.SET_CLEF, NOTE, {"clef": "xyz"}),
    (EditOp.SET_CLEF, NOTE, {"clef": {"line": 2}}),
    (EditOp.SET_CLEF, NOTE, {"clef": None, "sign": "F"}),
    (EditOp.SET_CLEF, NOTE, {"sign": {}}),
    (EditOp.SET_CLEF, NOTE, {"clef": {"sign": ["G"]}}),
    (EditOp.SET_KEY, NOTE, None),
    (EditOp.SET_KEY, NOTE, {}),
    (EditOp.SET_KEY, NOTE, {"fifths": 8}),
    (EditOp.SET_KEY, NOTE, {"fifths": "2"}),
    (EditOp.SET_KEY, NOTE, {"fifths": True}),
    (EditOp.SET_KEY, NOTE, {"fifths": 0, "mode": "xyz"}),
    (EditOp.SET_KEY, NOTE, {"key_signature": {"mode": "major"}}),
    (EditOp.SET_KEY, NOTE, {"fifths": 1, "mode": []}),
]


@pytest.mark.parametrize(("op", "anchor", "after"), INVALID_AFTER)
def test_invalid_after_is_rejected(
    op: EditOp, anchor: Anchor, after: dict[str, Any] | None
) -> None:
    with pytest.raises(InvalidEditPayload):
        validate_after(_score(), anchor, op, after)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("", ""),
        ("natural", ""),
        ("#", "#"),
        ("sharp", "#"),
        ("x", "##"),
        ("-", "b"),
        ("Flat", "b"),
        ("--", "bb"),
        ("###", None),
        (1, None),
    ],
)
def test_normalize_accidental(value: object, expected: str | None) -> None:
    assert normalize_accidental(value) == expected


def test_set_accidental_rejects_result_outside_midi_range() -> None:
    measure = Measure(number=1, events=(Event(kind=EventKind.NOTE, pitch="G9"),))
    score = ScoreIR(parts=(Part(id="p0", staves=(Staff(id="s0", measures=(measure,)),)),))
    with pytest.raises(InvalidEditPayload):
        validate_after(score, NOTE, EditOp.SET_ACCIDENTAL, {"accidental": "#"})


def test_validate_after_reports_missing_target_as_index_error() -> None:
    with pytest.raises(IndexError):
        validate_after(_score(), _anchor(event_index=9), EditOp.SET_PITCH, {"pitch": "D4"})
    with pytest.raises(IndexError):
        validate_after(_score(), _anchor(measure=9), EditOp.SET_PITCH, {"pitch": "D4"})


# --- Instantánea de `before` --------------------------------------------------


def test_snapshot_before_captures_exact_previous_state() -> None:
    score = _score()
    assert snapshot_before(score, NOTE, EditOp.SET_PITCH) == {"pitch": "C#4"}
    assert snapshot_before(score, NOTE, EditOp.SET_DURATION) == {"duration_beats": "1"}
    assert snapshot_before(score, NOTE, EditOp.SET_ACCIDENTAL) == {"accidental": "#"}
    assert snapshot_before(score, NOTE, EditOp.INSERT_EVENT) is None
    assert snapshot_before(score, NOTE, EditOp.DELETE_EVENT) == {
        "kind": "note",
        "pitch": "C#4",
        "duration_beats": "1",
        "tie": "start",
        "is_chord": False,
        "bbox": [20.0, 40.0, 36.0, 60.0],
        "confidence": 0.9,
    }
    assert snapshot_before(score, NOTE, EditOp.SET_CLEF) == {
        "clef": {"sign": "G", "line": 2, "octave_change": 0}
    }
    assert snapshot_before(score, NOTE, EditOp.SET_KEY) == {
        "key_signature": {"fifths": 2, "mode": "major"}
    }
    second = _anchor(measure=2)
    assert snapshot_before(score, second, EditOp.SET_CLEF) == {"clef": None}
    assert snapshot_before(score, second, EditOp.SET_KEY) == {"key_signature": None}
    assert snapshot_before(score, second, EditOp.SET_DURATION) == {"duration_beats": None}


@pytest.mark.parametrize(("op", "anchor", "after"), VALID_AFTER)
def test_undo_with_server_snapshot_restores_exact_state(
    op: EditOp, anchor: Anchor, after: dict[str, Any] | None
) -> None:
    score = _score()
    edit = EditEvent(
        id="e1",
        document_id="d1",
        seq=1,
        anchor=anchor,
        op=op,
        author="t",
        created_at=datetime.now(UTC),
        before=snapshot_before(score, anchor, op),
        after=after,
    )
    assert has_complete_before(edit)
    edited = apply_edit(score, edit)
    inverse = create_inverse_edit(edit, id="e2", seq=2, author="t", created_at=datetime.now(UTC))
    assert apply_edit(edited, inverse) == score


@pytest.mark.parametrize(
    ("op", "before", "complete"),
    [
        (EditOp.SET_PITCH, None, False),
        (EditOp.SET_PITCH, {"pitch": "C4"}, True),
        (EditOp.SET_DURATION, {}, False),
        (EditOp.SET_DURATION, {"duration_beats": "1"}, True),
        (EditOp.SET_ACCIDENTAL, None, False),
        (EditOp.SET_ACCIDENTAL, {"accidental": ""}, True),
        (EditOp.SET_ACCIDENTAL, {"pitch": "C#4"}, True),
        (EditOp.DELETE_EVENT, {"pitch": "C4"}, False),
        (EditOp.DELETE_EVENT, {"kind": "note", "pitch": "C4", "duration_beats": "1"}, True),
        (EditOp.SET_CLEF, None, False),
        (EditOp.SET_CLEF, {"clef": None}, True),
        (EditOp.SET_CLEF, {"sign": "G", "line": 2}, True),
        (EditOp.SET_KEY, None, False),
        (EditOp.SET_KEY, {"key_signature": None}, True),
        (EditOp.SET_KEY, {"fifths": 0}, True),
        (EditOp.INSERT_EVENT, None, True),
    ],
)
def test_has_complete_before(op: EditOp, before: dict[str, Any] | None, complete: bool) -> None:
    edit = EditEvent(
        id="e1",
        document_id="d1",
        seq=1,
        anchor=NOTE,
        op=op,
        author="t",
        created_at=datetime.now(UTC),
        before=before,
    )
    assert has_complete_before(edit) is complete
