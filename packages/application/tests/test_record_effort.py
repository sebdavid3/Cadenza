"""Tests unitarios para el caso de uso record_effort y análisis de esfuerzo (#13, ADR-0012)."""

from datetime import UTC, datetime

import pytest
from cadenza.application import (
    Forbidden,
    InMemoryEffortRepository,
    InMemorySessionRepository,
    Role,
    SessionData,
    SessionNotFound,
    User,
    compute_interventions_from_edits,
    contrast_interventions,
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
        role=Role.TRANSCRIPTOR,
    )


@pytest.fixture
def other_transcriptor() -> User:
    return User(
        id="user2",
        username="transcriptor2",
        password_hash="hash2",
        role=Role.TRANSCRIPTOR,
    )


@pytest.fixture
def investigator() -> User:
    return User(
        id="inv1",
        username="investigador1",
        password_hash="hash3",
        role=Role.INVESTIGADOR,
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

    stored = effort_repo.get_latest("session-user1")
    assert stored is not None
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


def test_record_effort_investigator_other_session_returns_forbidden(
    session_repo: InMemorySessionRepository,
    effort_repo: InMemoryEffortRepository,
    investigator: User,
) -> None:
    with pytest.raises(Forbidden) as exc_info:
        record_effort(
            session_repo,
            effort_repo,
            session_id="session-user1",
            duration_ms=1000,
            current_user=investigator,
        )
    assert "investigador" in str(exc_info.value).lower()


def test_record_effort_investigator_own_session_allowed(
    session_repo: InMemorySessionRepository,
    effort_repo: InMemoryEffortRepository,
    investigator: User,
) -> None:
    session_repo.add(
        SessionData(
            id="session-inv",
            document_id="doc-2",
            omr_engine="fake",
            document={"score": {"parts": []}},
            owner_id="inv1",
        ),
        findings=(),
    )
    result = record_effort(
        session_repo,
        effort_repo,
        session_id="session-inv",
        duration_ms=15000,
        current_user=investigator,
    )
    assert result.session_id == "session-inv"
    assert result.duration_ms == 15000


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


def test_compute_interventions_and_contrast() -> None:
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

    # Contrastar con reporte coincidente
    comparison = contrast_interventions({"1": 2, "2": 1}, edits)
    assert len(comparison) == 2
    assert comparison[0].measure == "1"
    assert comparison[0].matches
    assert comparison[0].difference == 0
    assert comparison[1].measure == "2"
    assert comparison[1].matches

    # Contrastar con reporte discrepante (ej. compás 1 reportó 3 y compás 3 reportó 1)
    diff_comparison = contrast_interventions({"1": 3, "3": 1}, edits)
    diff_map = {c.measure: c for c in diff_comparison}
    assert diff_map["1"].reported_count == 3
    assert diff_map["1"].logged_count == 2
    assert diff_map["1"].difference == 1
    assert not diff_map["1"].matches

    assert diff_map["2"].reported_count == 0
    assert diff_map["2"].logged_count == 1
    assert diff_map["2"].difference == -1

    assert diff_map["3"].reported_count == 1
    assert diff_map["3"].logged_count == 0
    assert diff_map["3"].difference == 1


def test_get_effort_owner_and_investigator(
    session_repo: InMemorySessionRepository,
    effort_repo: InMemoryEffortRepository,
    owner_user: User,
    other_transcriptor: User,
    investigator: User,
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

    # 3. Investigador consulta sesión ajena -> permitido (ADR-0012)
    res_inv = get_effort(
        session_repo,
        effort_repo,
        session_id="session-user1",
        current_user=investigator,
    )
    assert len(res_inv) == 1
    assert res_inv[0].duration_ms == 30000

    # 4. Transcriptor ajeno consulta -> SessionNotFound (ADR-0012)
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
