"""Pruebas unitarias del caso de uso list_sessions (Issue #27, ADR-0009, ADR-0012)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from cadenza.application import (
    InMemoryEditEventRepository,
    InMemorySessionRepository,
    Role,
    SessionData,
    User,
    list_sessions,
)
from cadenza.domain import Anchor, EditEvent, EditOp, Finding, Severity


@pytest.fixture
def users() -> tuple[User, User, User]:
    t1 = User(
        id="user-t1",
        username="transcriptor1",
        password_hash="h1",
        role=Role.TRANSCRIPTOR,
        active=True,
    )
    t2 = User(
        id="user-t2",
        username="transcriptor2",
        password_hash="h2",
        role=Role.TRANSCRIPTOR,
        active=True,
    )
    inv = User(
        id="user-inv",
        username="investigador1",
        password_hash="h3",
        role=Role.INVESTIGADOR,
        active=True,
    )
    return t1, t2, inv


def test_list_sessions_empty(users: tuple[User, User, User]) -> None:
    t1, _, _ = users
    repo = InMemorySessionRepository()
    results = list_sessions(session_repository=repo, current_user=t1)
    assert results == ()


def test_list_sessions_filters_by_owner_for_transcriptor(users: tuple[User, User, User]) -> None:
    t1, t2, inv = users
    repo = InMemorySessionRepository()

    now = datetime.now(UTC)
    s1 = SessionData(
        id="s1",
        document_id="doc1",
        omr_engine="fake",
        document={"score": {}},
        owner_id=t1.id,
        created_at=now,
    )
    s2 = SessionData(
        id="s2",
        document_id="doc2",
        omr_engine="fake",
        document={"score": {}},
        owner_id=t2.id,
        created_at=now + timedelta(seconds=1),
    )
    repo.add(s1, findings=[])
    repo.add(s2, findings=[])

    # t1 solo ve s1
    res_t1 = list_sessions(session_repository=repo, current_user=t1)
    assert len(res_t1) == 1
    assert res_t1[0].session_id == "s1"
    assert res_t1[0].owner_id == t1.id

    # t2 solo ve s2
    res_t2 = list_sessions(session_repository=repo, current_user=t2)
    assert len(res_t2) == 1
    assert res_t2[0].session_id == "s2"
    assert res_t2[0].owner_id == t2.id

    # Investigador ve ambas
    res_inv = list_sessions(session_repository=repo, current_user=inv)
    assert len(res_inv) == 2
    # Orden descendente por fecha: s2 más reciente que s1
    assert [r.session_id for r in res_inv] == ["s2", "s1"]


def test_list_sessions_pagination_and_sorting(users: tuple[User, User, User]) -> None:
    _, _, inv = users
    repo = InMemorySessionRepository()

    base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    for i in range(5):
        s = SessionData(
            id=f"session-{i}",
            document_id=f"doc-{i}",
            omr_engine="fake",
            document={"score": {}},
            owner_id="any",
            created_at=base_time + timedelta(hours=i),
        )
        repo.add(s, findings=[])

    # Página 1: limit=2, offset=0 -> session-4, session-3 (más recientes)
    page1 = list_sessions(session_repository=repo, current_user=inv, limit=2, offset=0)
    assert [r.session_id for r in page1] == ["session-4", "session-3"]

    # Página 2: limit=2, offset=2 -> session-2, session-1
    page2 = list_sessions(session_repository=repo, current_user=inv, limit=2, offset=2)
    assert [r.session_id for r in page2] == ["session-2", "session-1"]

    # Página 3: limit=2, offset=4 -> session-0
    page3 = list_sessions(session_repository=repo, current_user=inv, limit=2, offset=4)
    assert [r.session_id for r in page3] == ["session-0"]


def test_list_sessions_filter_by_status(users: tuple[User, User, User]) -> None:
    _, _, inv = users
    repo = InMemorySessionRepository()

    now = datetime.now(UTC)
    s1 = SessionData(
        id="s1",
        document_id="doc1",
        omr_engine="fake",
        document={"score": {}},
        status="transcribed",
        owner_id="u",
        created_at=now,
    )
    s2 = SessionData(
        id="s2",
        document_id="doc2",
        omr_engine="fake",
        document={"score": {}},
        status="finalized",
        owner_id="u",
        created_at=now + timedelta(seconds=1),
    )
    repo.add(s1, findings=[])
    repo.add(s2, findings=[])

    only_finalized = list_sessions(session_repository=repo, current_user=inv, status="finalized")
    assert len(only_finalized) == 1
    assert only_finalized[0].session_id == "s2"

    only_transcribed = list_sessions(
        session_repository=repo, current_user=inv, status="transcribed"
    )
    assert len(only_transcribed) == 1
    assert only_transcribed[0].session_id == "s1"


def test_list_sessions_counts_findings_and_edits(users: tuple[User, User, User]) -> None:
    t1, _, _ = users
    edit_repo = InMemoryEditEventRepository()
    repo = InMemorySessionRepository(edit_repository=edit_repo)

    s1 = SessionData(
        id="s1",
        document_id="doc1",
        omr_engine="fake",
        document={"score": {}},
        status="correcting",
        owner_id=t1.id,
        created_at=datetime.now(UTC),
        validated_at_seq=0,
    )
    anchor = Anchor(part=0, staff=0, staff_id="s0", measure=1, voice=0, event_index=0)
    finding = Finding(
        rule_id="rule.test",
        severity=Severity.ERROR,
        message="err",
        anchor=anchor,
        at_seq=0,
    )
    repo.add(s1, findings=[finding])

    # Añadir 2 ediciones en edit_repo
    edit1 = EditEvent(
        id="e1",
        document_id="doc1",
        seq=1,
        anchor=anchor,
        op=EditOp.SET_PITCH,
        author=t1.username,
        created_at=datetime.now(UTC),
    )
    edit2 = EditEvent(
        id="e2",
        document_id="doc1",
        seq=2,
        anchor=anchor,
        op=EditOp.SET_PITCH,
        author=t1.username,
        created_at=datetime.now(UTC),
    )
    edit_repo.append("s1", edit1)
    edit_repo.append("s1", edit2)

    results = list_sessions(session_repository=repo, current_user=t1)
    assert len(results) == 1
    summary = results[0]
    assert summary.findings_count == 1
    assert summary.edits_count == 2
