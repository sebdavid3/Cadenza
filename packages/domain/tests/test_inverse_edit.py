"""Pruebas unitarias de inversión de eventos y rastreo de ediciones activas (#35, ADR-0007)."""

from datetime import UTC, datetime
from fractions import Fraction

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
    apply_edit,
    create_inverse_edit,
    get_last_active_edit,
    materialize,
)


def _base_score() -> ScoreIR:
    events = (
        Event(kind=EventKind.NOTE, voice=0, pitch="C4", duration_beats=Fraction(1, 1)),
        Event(kind=EventKind.NOTE, voice=0, pitch="D4", duration_beats=Fraction(1, 1)),
    )
    measure = Measure(
        number=1,
        time_signature=TimeSignature(4, 4),
        clef=Clef.treble(),
        key_signature=KeySignature(fifths=0, mode="major"),
        events=events,
    )
    staff = Staff(id="staff-1", measures=(measure,))
    part = Part(id="part-1", staves=(staff,))
    return ScoreIR(parts=(part,))


def test_inverse_set_pitch() -> None:
    score = _base_score()
    anchor = Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="staff-1")

    edit = EditEvent(
        id="e1",
        document_id="doc-1",
        seq=1,
        anchor=anchor,
        op=EditOp.SET_PITCH,
        author="user1",
        created_at=datetime.now(UTC),
        before={"pitch": "C4"},
        after={"pitch": "E4"},
    )
    inverse = create_inverse_edit(
        edit, id="inv-1", seq=2, author="user1", created_at=datetime.now(UTC)
    )

    assert inverse.op is EditOp.SET_PITCH
    assert inverse.before == {"pitch": "E4"}
    assert inverse.after == {"pitch": "C4"}
    assert inverse.reverts_edit_id == "e1"
    assert inverse.is_reversion

    # Proyección: editar y luego deshacer debe restaurar el score exactamente
    edited_score = apply_edit(score, edit)
    assert edited_score.parts[0].staves[0].measures[0].events[0].pitch == "E4"

    restored_score = apply_edit(edited_score, inverse)
    assert restored_score == score
    assert materialize(score, [edit, inverse]) == score


def test_inverse_set_duration() -> None:
    score = _base_score()
    anchor = Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="staff-1")

    edit = EditEvent(
        id="e1",
        document_id="doc-1",
        seq=1,
        anchor=anchor,
        op=EditOp.SET_DURATION,
        author="user1",
        created_at=datetime.now(UTC),
        before={"duration_beats": "1"},
        after={"duration_beats": "2"},
    )
    inverse = create_inverse_edit(
        edit, id="inv-1", seq=2, author="user1", created_at=datetime.now(UTC)
    )

    assert inverse.op is EditOp.SET_DURATION
    assert inverse.before == {"duration_beats": "2"}
    assert inverse.after == {"duration_beats": "1"}

    assert materialize(score, [edit, inverse]) == score


def test_inverse_set_accidental() -> None:
    score = _base_score()
    anchor = Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="staff-1")

    edit = EditEvent(
        id="e1",
        document_id="doc-1",
        seq=1,
        anchor=anchor,
        op=EditOp.SET_ACCIDENTAL,
        author="user1",
        created_at=datetime.now(UTC),
        before={"pitch": "C4"},
        after={"pitch": "C#4"},
    )
    inverse = create_inverse_edit(
        edit, id="inv-1", seq=2, author="user1", created_at=datetime.now(UTC)
    )

    assert inverse.op is EditOp.SET_ACCIDENTAL
    assert inverse.before == {"pitch": "C#4"}
    assert inverse.after == {"pitch": "C4"}

    assert materialize(score, [edit, inverse]) == score


def test_inverse_set_clef() -> None:
    score = _base_score()
    anchor = Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="staff-1")

    edit = EditEvent(
        id="e1",
        document_id="doc-1",
        seq=1,
        anchor=anchor,
        op=EditOp.SET_CLEF,
        author="user1",
        created_at=datetime.now(UTC),
        before={"clef": "treble"},
        after={"clef": "bass"},
    )
    inverse = create_inverse_edit(
        edit, id="inv-1", seq=2, author="user1", created_at=datetime.now(UTC)
    )

    assert inverse.op is EditOp.SET_CLEF
    assert inverse.before == {"clef": "bass"}
    assert inverse.after == {"clef": "treble"}

    assert materialize(score, [edit, inverse]) == score


def test_inverse_set_key() -> None:
    score = _base_score()
    anchor = Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="staff-1")

    edit = EditEvent(
        id="e1",
        document_id="doc-1",
        seq=1,
        anchor=anchor,
        op=EditOp.SET_KEY,
        author="user1",
        created_at=datetime.now(UTC),
        before={"key_signature": {"fifths": 0, "mode": "major"}},
        after={"key_signature": {"fifths": 2, "mode": "major"}},
    )
    inverse = create_inverse_edit(
        edit, id="inv-1", seq=2, author="user1", created_at=datetime.now(UTC)
    )

    assert inverse.op is EditOp.SET_KEY
    assert inverse.before == {"key_signature": {"fifths": 2, "mode": "major"}}
    assert inverse.after == {"key_signature": {"fifths": 0, "mode": "major"}}

    assert materialize(score, [edit, inverse]) == score


def test_inverse_insert_event_is_delete_event() -> None:
    score = _base_score()
    # Inserción al final de la voz (event_index = 2)
    anchor = Anchor(part=0, staff=0, measure=1, voice=0, event_index=2, staff_id="staff-1")

    inserted_event_data = {
        "kind": "note",
        "voice": 0,
        "pitch": "E4",
        "duration_beats": "1",
    }
    edit = EditEvent(
        id="e1",
        document_id="doc-1",
        seq=1,
        anchor=anchor,
        op=EditOp.INSERT_EVENT,
        author="user1",
        created_at=datetime.now(UTC),
        before=None,
        after=inserted_event_data,
    )
    inverse = create_inverse_edit(
        edit, id="inv-1", seq=2, author="user1", created_at=datetime.now(UTC)
    )

    assert inverse.op is EditOp.DELETE_EVENT
    assert inverse.before == inserted_event_data
    assert inverse.after is None
    assert inverse.reverts_edit_id == "e1"

    assert materialize(score, [edit, inverse]) == score


def test_inverse_delete_event_is_insert_event() -> None:
    score = _base_score()
    # Borrado del segundo evento (event_index = 1: D4)
    anchor = Anchor(part=0, staff=0, measure=1, voice=0, event_index=1, staff_id="staff-1")

    deleted_event_data = {
        "kind": "note",
        "voice": 0,
        "pitch": "D4",
        "duration_beats": "1",
    }
    edit = EditEvent(
        id="e1",
        document_id="doc-1",
        seq=1,
        anchor=anchor,
        op=EditOp.DELETE_EVENT,
        author="user1",
        created_at=datetime.now(UTC),
        before=deleted_event_data,
        after=None,
    )
    inverse = create_inverse_edit(
        edit, id="inv-1", seq=2, author="user1", created_at=datetime.now(UTC)
    )

    assert inverse.op is EditOp.INSERT_EVENT
    assert inverse.before is None
    assert inverse.after == deleted_event_data
    assert inverse.reverts_edit_id == "e1"

    assert materialize(score, [edit, inverse]) == score


def test_edit_event_serialization_preserves_reverts_edit_id() -> None:
    anchor = Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="staff-1")
    event = EditEvent(
        id="inv-1",
        document_id="doc-1",
        seq=2,
        anchor=anchor,
        op=EditOp.SET_PITCH,
        author="user1",
        created_at=datetime.now(UTC),
        before={"pitch": "E4"},
        after={"pitch": "C4"},
        reverts_edit_id="e1",
    )
    primitive = event.to_primitive()
    assert primitive["reverts_edit_id"] == "e1"

    deserialized = EditEvent.from_primitive(primitive)
    assert deserialized.reverts_edit_id == "e1"
    assert deserialized == event


def test_get_last_active_edit() -> None:
    anchor = Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="staff-1")

    # 1. Sin ediciones -> None
    assert get_last_active_edit([]) is None

    # 2. Dos ediciones consecutivas -> la última activa es e2
    e1 = EditEvent(
        id="e1",
        document_id="d1",
        seq=1,
        anchor=anchor,
        op=EditOp.SET_PITCH,
        author="u",
        created_at=datetime.now(UTC),
        before={"pitch": "C4"},
        after={"pitch": "D4"},
    )
    e2 = EditEvent(
        id="e2",
        document_id="d1",
        seq=2,
        anchor=anchor,
        op=EditOp.SET_PITCH,
        author="u",
        created_at=datetime.now(UTC),
        before={"pitch": "D4"},
        after={"pitch": "E4"},
    )
    assert get_last_active_edit([e1, e2]) == e2

    # 3. e2 es revertida por inv_e2 -> la última activa pasa a ser e1
    inv_e2 = create_inverse_edit(e2, id="inv2", seq=3, author="u", created_at=datetime.now(UTC))
    assert get_last_active_edit([e1, e2, inv_e2]) == e1

    # 4. e1 también es revertida por inv_e1 -> no quedan ediciones activas
    inv_e1 = create_inverse_edit(e1, id="inv1", seq=4, author="u", created_at=datetime.now(UTC))
    assert get_last_active_edit([e1, e2, inv_e2, inv_e1]) is None

    # 5. Se añade e3 posteriormente -> activa es e3
    e3 = EditEvent(
        id="e3",
        document_id="d1",
        seq=5,
        anchor=anchor,
        op=EditOp.SET_PITCH,
        author="u",
        created_at=datetime.now(UTC),
        before={"pitch": "C4"},
        after={"pitch": "F4"},
    )
    assert get_last_active_edit([e1, e2, inv_e2, inv_e1, e3]) == e3
