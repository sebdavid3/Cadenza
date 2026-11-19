"""Tests unitarios para el caso de uso record_effort y análisis de esfuerzo (#13, ADR-0012)."""

from datetime import UTC, datetime

import pytest
from cadenza.application import (
    InMemoryEffortRepository,
    InMemorySessionRepository,
    SessionData,
    SessionNotFound,
    User,
    compute_interventions_from_edits,
    get_effort,
    record_effort,
)
from cadenza.domain import Anchor, EditEvent, EditOp


@pytest.fixture
def session_repo() -> InMemorySessionRepository:
    repo = InMemorySessionRepository()
    repo.add(
        SessionData(
            id="session-user1",
            document_id="doc-1",
            omr_engine="fake",
            document={"score": {"parts": []}},
            owner_id="user1",
        ),
        findings=(),
    )
    return repo


@pytest.fixture
def effort_repo() -> InMemoryEffortRepository:
    return InMemoryEffortRepository()


@pytest.fixture
def owner_user() -> User:
    return User(
        id="user1",
        username="transcriptor1",
        password_hash="hash1",
    )


@pytest.fixture
def other_transcriptor() -> User:
    return User(
        id="user2",
        username="transcriptor2",
        password_hash="hash2",
    )


def test_record_effort_success(
    session_repo: InMemorySessionRepository,
    effort_repo: InMemoryEffortRepository,
    owner_user: User,
) -> None:
    result = record_effort(
        session_repo,
        effort_repo,
        session_id="session-user1",
        duration_ms=45000,
        time_to_first_edit_ms=12000,
        interventions={"1": 3, 2: 1},
        current_user=owner_user,
    )

    assert result.session_id == "session-user1"
    assert result.duration_ms == 45000
    assert result.time_to_first_edit_ms == 12000
    assert result.interventions == {"1": 3, "2": 1}
    assert result.id is not None
    assert result.created_at is not None

    (stored,) = effort_repo.list_by_session("session-user1")
    assert stored.id == result.id
    assert stored.duration_ms == 45000


def test_record_effort_session_not_found(
    session_repo: InMemorySessionRepository,
    effort_repo: InMemoryEffortRepository,
    owner_user: User,
) -> None:
    with pytest.raises(SessionNotFound):
        record_effort(
            session_repo,
            effort_repo,
            session_id="non-existent",
            duration_ms=1000,
            current_user=owner_user,
        )


def test_record_effort_transcriptor_other_session_returns_not_found(
    session_repo: InMemorySessionRepository,
    effort_repo: InMemoryEffortRepository,
    other_transcriptor: User,
) -> None:
    with pytest.raises(SessionNotFound):
        record_effort(
            session_repo,
            effort_repo,
            session_id="session-user1",
            duration_ms=1000,
            current_user=other_transcriptor,
        )


def test_record_effort_negative_duration_raises_value_error(
    session_repo: InMemorySessionRepository,
    effort_repo: InMemoryEffortRepository,
    owner_user: User,
) -> None:
    with pytest.raises(ValueError, match="duration_ms"):
        record_effort(
            session_repo,
            effort_repo,
            session_id="session-user1",
            duration_ms=-1,
            current_user=owner_user,
        )


def test_record_effort_negative_time_to_first_edit_raises_value_error(
    session_repo: InMemorySessionRepository,
    effort_repo: InMemoryEffortRepository,
    owner_user: User,
) -> None:
    with pytest.raises(ValueError, match="time_to_first_edit_ms"):
        record_effort(
            session_repo,
            effort_repo,
            session_id="session-user1",
            duration_ms=1000,
            time_to_first_edit_ms=-5,
            current_user=owner_user,
        )


def test_compute_interventions_from_edits() -> None:
    anchor_m1 = Anchor(part=0, staff=0, measure=1, voice=1, event_index=0, staff_id="s1")
    anchor_m2 = Anchor(part=0, staff=0, measure=2, voice=1, event_index=0, staff_id="s1")

    edits = [
        EditEvent(
            id="e1",
            document_id="doc-1",
            seq=1,
            op=EditOp.SET_PITCH,
            author="u1",
            anchor=anchor_m1,
            after={"pitch": "C4"},
            created_at=datetime.now(UTC),
        ),
        EditEvent(
            id="e2",
            document_id="doc-1",
            seq=2,
            op=EditOp.SET_PITCH,
            author="u1",
            anchor=anchor_m1,
            after={"pitch": "D4"},
            created_at=datetime.now(UTC),
        ),
        EditEvent(
            id="e3",
            document_id="doc-1",
            seq=3,
            op=EditOp.SET_DURATION,
            author="u1",
            anchor=anchor_m2,
            after={"duration_beats": "1"},
            created_at=datetime.now(UTC),
        ),
    ]

    computed = compute_interventions_from_edits(edits)
    assert computed == {"1": 2, "2": 1}


def test_get_effort_only_owner(
    session_repo: InMemorySessionRepository,
    effort_repo: InMemoryEffortRepository,
    owner_user: User,
    other_transcriptor: User,
) -> None:
    # 1. Registrar una medición
    record_effort(
        session_repo,
        effort_repo,
        session_id="session-user1",
        duration_ms=30000,
        current_user=owner_user,
    )

    # 2. Dueño consulta -> 200 con resultados
    res_owner = get_effort(
        session_repo,
        effort_repo,
        session_id="session-user1",
        current_user=owner_user,
    )
    assert len(res_owner) == 1
    assert res_owner[0].duration_ms == 30000

    # 3. Cuenta ajena consulta -> SessionNotFound (ADR-0012)
    with pytest.raises(SessionNotFound):
        get_effort(
            session_repo,
            effort_repo,
            session_id="session-user1",
            current_user=other_transcriptor,
        )

    # 5. Sesión inexistente -> SessionNotFound
    with pytest.raises(SessionNotFound):
        get_effort(
            session_repo,
            effort_repo,
            session_id="non-existent",
            current_user=owner_user,
        )


def test_effort_distinguishes_reversions_and_undone_corrections() -> None:
    edits = [
        EditEvent(
            id="e1",
            document_id="doc-1",
            seq=1,
            op=EditOp.SET_PITCH,
            anchor=Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="staff-1"),
            author="tester",
            created_at=datetime.now(UTC),
            before={"pitch": "C4"},
            after={"pitch": "D4"},
        ),
        EditEvent(
            id="e2",
            document_id="doc-1",
            seq=2,
            op=EditOp.SET_PITCH,
            anchor=Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="staff-1"),
            author="tester",
            created_at=datetime.now(UTC),
            before={"pitch": "D4"},
            after={"pitch": "C4"},
            reverts_edit_id="e1",
        ),
        EditEvent(
            id="e3",
            document_id="doc-1",
            seq=3,
            op=EditOp.SET_PITCH,
            anchor=Anchor(part=0, staff=0, measure=2, voice=0, event_index=0, staff_id="staff-1"),
            author="tester",
            created_at=datetime.now(UTC),
            before={"pitch": "E4"},
            after={"pitch": "F4"},
        ),
    ]

    # Total de eventos registrados: 2 en compás 1, 1 en compás 2
    raw_counts = compute_interventions_from_edits(edits)
    assert raw_counts == {"1": 2, "2": 1}

    # Solo correcciones activas (descartando e1 y su reversión e2)
    active_counts = compute_interventions_from_edits(edits, active_only=True)
    assert active_counts == {"2": 1}
