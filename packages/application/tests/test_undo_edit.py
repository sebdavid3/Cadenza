"""Pruebas unitarias del caso de uso undo_edit (#35, ADR-0007, ADR-0012, ADR-0014)."""

from __future__ import annotations

from fractions import Fraction

import pytest
from cadenza.application import (
    Forbidden,
    InMemoryEditEventRepository,
    InMemorySessionRepository,
    NoEditsToUndo,
    Role,
    SequenceConflict,
    SessionClosed,
    SessionData,
    SessionNotFound,
    SessionStatus,
    User,
    append_edit,
    undo_edit,
)
from cadenza.domain import (
    Anchor,
    Clef,
    EditOp,
    Event,
    EventKind,
    KeySignature,
    Measure,
    Part,
    ScoreIR,
    Staff,
    TimeSignature,
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


def _setup_session(
    owner_id: str = "user-1",
    status: str = SessionStatus.TRANSCRIBED,
) -> tuple[InMemorySessionRepository, InMemoryEditEventRepository, SessionData]:
    score = _base_score()
    session_repo = InMemorySessionRepository()
    edit_repo = InMemoryEditEventRepository()
    session_data = SessionData(
        id="sess-1",
        document_id="doc-1",
        omr_engine="fake",
        model_version=None,
        status=status,
        image_artifact="art-1",
        document={"score": score.to_primitive()},
        validated_at_seq=0,
        owner_id=owner_id,
    )
    session_repo.add(session_data, findings=())
    return session_repo, edit_repo, session_data


def _user(
    id: str = "user-1",
    username: str = "transcriptor1",
    role: Role = Role.TRANSCRIPTOR,
) -> User:
    return User(id=id, username=username, password_hash="hash", role=role)


def test_undo_success_restores_score_and_records_compensatory_event() -> None:
    session_repo, edit_repo, _ = _setup_session()
    user = _user()
    anchor = Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="staff-1")

    # 1. Aplicar edición: cambiar C4 a E4
    edit1 = append_edit(
        "sess-1",
        anchor=anchor,
        op=EditOp.SET_PITCH,
        before={"pitch": "C4"},
        after={"pitch": "E4"},
        base_seq=0,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=user,
    )
    assert edit1.seq == 1
    session = session_repo.get("sess-1")
    assert session is not None
    assert session.status == SessionStatus.CORRECTING

    # 2. Deshacer edición
    result = undo_edit(
        "sess-1",
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=user,
    )

    assert result.session_id == "sess-1"
    assert result.current_seq == 2
    assert result.undone_edit_id == edit1.id
    assert result.compensatory_edit.seq == 2
    assert result.compensatory_edit.reverts_edit_id == edit1.id
    assert result.compensatory_edit.is_reversion is True

    # 3. La partitura vuelve exactamente a su estado previo (C4, D4)
    expected_score = _base_score().to_primitive()
    assert result.current_score == expected_score

    # 4. El log tiene 2 eventos inmutables
    events = edit_repo.list_events("sess-1")
    assert len(events) == 2
    assert events[0].id == edit1.id
    assert events[1].reverts_edit_id == edit1.id


def test_undo_consecutive_edits() -> None:
    session_repo, edit_repo, _ = _setup_session()
    user = _user()
    anchor0 = Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="staff-1")
    anchor1 = Anchor(part=0, staff=0, measure=1, voice=0, event_index=1, staff_id="staff-1")

    # Edición 1: C4 -> E4
    e1 = append_edit(
        "sess-1",
        anchor=anchor0,
        op=EditOp.SET_PITCH,
        before={"pitch": "C4"},
        after={"pitch": "E4"},
        base_seq=0,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=user,
    )
    # Edición 2: D4 -> F4
    e2 = append_edit(
        "sess-1",
        anchor=anchor1,
        op=EditOp.SET_PITCH,
        before={"pitch": "D4"},
        after={"pitch": "F4"},
        base_seq=1,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=user,
    )

    # Primer undo: revierte e2
    res1 = undo_edit(
        "sess-1",
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=user,
    )
    assert res1.undone_edit_id == e2.id
    assert res1.current_seq == 3
    # Nota 0 es E4, nota 1 es D4
    pitches1 = [
        ev["pitch"] for ev in res1.current_score["parts"][0]["staves"][0]["measures"][0]["events"]
    ]
    assert pitches1 == ["E4", "D4"]

    # Segundo undo: revierte e1
    res2 = undo_edit(
        "sess-1",
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=user,
    )
    assert res2.undone_edit_id == e1.id
    assert res2.current_seq == 4
    # Partitura vuelve a C4, D4
    pitches2 = [
        ev["pitch"] for ev in res2.current_score["parts"][0]["staves"][0]["measures"][0]["events"]
    ]
    assert pitches2 == ["C4", "D4"]

    # Tercer undo: no quedan ediciones activas
    with pytest.raises(NoEditsToUndo):
        undo_edit(
            "sess-1",
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=user,
        )


def test_undo_on_empty_edits_raises_no_edits_to_undo() -> None:
    session_repo, edit_repo, _ = _setup_session()
    user = _user()

    with pytest.raises(NoEditsToUndo):
        undo_edit(
            "sess-1",
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=user,
        )


def test_undo_with_base_seq_validation() -> None:
    session_repo, edit_repo, _ = _setup_session()
    user = _user()
    anchor = Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="staff-1")

    append_edit(
        "sess-1",
        anchor=anchor,
        op=EditOp.SET_PITCH,
        before={"pitch": "C4"},
        after={"pitch": "E4"},
        base_seq=0,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=user,
    )

    # base_seq=0 cuando current_seq=1 -> SequenceConflict
    with pytest.raises(SequenceConflict):
        undo_edit(
            "sess-1",
            base_seq=0,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=user,
        )

    # base_seq=1 coincide -> éxito
    res = undo_edit(
        "sess-1",
        base_seq=1,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=user,
    )
    assert res.current_seq == 2


def test_undo_authorization_rules_adr0012() -> None:
    session_repo, edit_repo, _ = _setup_session(owner_id="owner-user")
    anchor = Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="staff-1")
    owner = _user(id="owner-user", username="owner", role=Role.TRANSCRIPTOR)

    append_edit(
        "sess-1",
        anchor=anchor,
        op=EditOp.SET_PITCH,
        before={"pitch": "C4"},
        after={"pitch": "E4"},
        base_seq=0,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=owner,
    )

    other_transcriptor = _user(id="other-user", username="other", role=Role.TRANSCRIPTOR)
    with pytest.raises(SessionNotFound):
        undo_edit(
            "sess-1",
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=other_transcriptor,
        )

    other_investigator = _user(id="investigator-user", username="inv", role=Role.INVESTIGADOR)
    with pytest.raises(Forbidden):
        undo_edit(
            "sess-1",
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=other_investigator,
        )

    # Sesión inexistente
    with pytest.raises(SessionNotFound):
        undo_edit(
            "non-existent",
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=owner,
        )


def test_undo_on_finalized_session_raises_session_closed() -> None:
    session_repo, edit_repo, _ = _setup_session(status=SessionStatus.FINALIZED)
    user = _user()

    with pytest.raises(SessionClosed):
        undo_edit(
            "sess-1",
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=user,
        )


def test_undo_insert_event_applies_delete() -> None:
    session_repo, edit_repo, _ = _setup_session()
    user = _user()
    anchor = Anchor(part=0, staff=0, measure=1, voice=0, event_index=2, staff_id="staff-1")

    # Inserción al final de la voz
    e1 = append_edit(
        "sess-1",
        anchor=anchor,
        op=EditOp.INSERT_EVENT,
        after={"kind": "note", "voice": 0, "pitch": "G4", "duration_beats": "1"},
        base_seq=0,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=user,
    )
    assert e1.seq == 1

    # Deshacer
    result = undo_edit(
        "sess-1",
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=user,
    )
    assert result.compensatory_edit.op is EditOp.DELETE_EVENT
    # Vuelve a 2 notas
    events = result.current_score["parts"][0]["staves"][0]["measures"][0]["events"]
    assert len(events) == 2
    assert [ev["pitch"] for ev in events] == ["C4", "D4"]
