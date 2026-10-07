"""Pruebas unitarias de los casos de uso de la capa de aplicación con fakes en memoria."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from cadenza.application import (
    EditEventRepository,
    PersistedFinding,
    SessionData,
    SessionNotFound,
    SessionRepository,
    append_edit,
    get_session,
    list_findings,
    transcribe_score,
)
from cadenza.domain import Anchor, EditEvent, EditOp, Finding
from cadenza.omr import FakeOMREngine
from cadenza.validation import MeasureBalanceRule, ValidationEngine


class InMemorySessionRepository(SessionRepository):
    """Fake en memoria para SessionRepository."""

    def __init__(self) -> None:
        self.sessions: dict[str, SessionData] = {}
        self.findings: dict[str, list[PersistedFinding]] = {}
        self._next_finding_id = 1

    def add(self, session: SessionData, findings: Sequence[Finding]) -> SessionData:
        self.sessions[session.id] = session
        persisted = []
        for finding in findings:
            persisted.append(
                PersistedFinding(
                    id=self._next_finding_id,
                    rule_id=finding.rule_id,
                    severity=finding.severity.value,
                    message=finding.message,
                    suggested_fix=finding.suggested_fix,
                    anchor=finding.anchor.to_primitive(),
                )
            )
            self._next_finding_id += 1
        self.findings[session.id] = persisted
        return session

    def get(self, session_id: str) -> SessionData | None:
        return self.sessions.get(session_id)

    def list_findings(self, session_id: str) -> tuple[PersistedFinding, ...]:
        return tuple(self.findings.get(session_id, []))

    def list(self, owner_id: str | None = None) -> tuple[SessionData, ...]:
        sessions = list(self.sessions.values())
        if owner_id is not None:
            sessions = [s for s in sessions if s.owner_id == owner_id]
        return tuple(sessions)


class InMemoryEditEventRepository(EditEventRepository):
    """Fake en memoria para EditEventRepository."""

    def __init__(self) -> None:
        self.events: dict[str, list[EditEvent]] = {}

    def next_seq(self, session_id: str) -> int:
        return len(self.events.get(session_id, [])) + 1

    def append(self, session_id: str, edit: EditEvent) -> EditEvent:
        self.events.setdefault(session_id, []).append(edit)
        return edit

    def list_events(self, session_id: str) -> tuple[EditEvent, ...]:
        return tuple(self.events.get(session_id, []))


@pytest.fixture
def session_repo() -> InMemorySessionRepository:
    return InMemorySessionRepository()


@pytest.fixture
def edit_repo() -> InMemoryEditEventRepository:
    return InMemoryEditEventRepository()


def test_transcribe_score_orchestration(
    tmp_path: Path,
    session_repo: InMemorySessionRepository,
) -> None:
    fake_image = tmp_path / "score.png"
    fake_image.write_bytes(b"dummy")

    result = transcribe_score(
        fake_image,
        omr_engine=FakeOMREngine(),
        validator=ValidationEngine([MeasureBalanceRule()]),
        session_repository=session_repo,
    )

    assert result.session_id in session_repo.sessions
    assert result.omr_engine == "fake"
    assert result.findings_count == 0


def test_get_session_unknown_raises_session_not_found(
    session_repo: InMemorySessionRepository,
    edit_repo: InMemoryEditEventRepository,
) -> None:
    with pytest.raises(SessionNotFound) as exc_info:
        get_session("non-existent", session_repository=session_repo, edit_repository=edit_repo)

    assert exc_info.value.session_id == "non-existent"


def test_append_edit_success(
    tmp_path: Path,
    session_repo: InMemorySessionRepository,
    edit_repo: InMemoryEditEventRepository,
) -> None:
    fake_image = tmp_path / "score.png"
    fake_image.write_bytes(b"dummy")
    result = transcribe_score(
        fake_image,
        omr_engine=FakeOMREngine(),
        validator=ValidationEngine([]),
        session_repository=session_repo,
    )

    anchor = Anchor(
        part=0,
        staff=0,
        measure=1,
        voice=0,
        event_index=0,
        staff_id="part-0-staff-0",
    )
    edit = append_edit(
        result.session_id,
        anchor=anchor,
        op=EditOp.SET_PITCH,
        author="tester",
        session_repository=session_repo,
        edit_repository=edit_repo,
        before={"pitch": "C4"},
        after={"pitch": "D4"},
    )

    assert edit.seq == 1
    assert edit.author == "tester"
    assert edit.op == EditOp.SET_PITCH

    detail = get_session(
        result.session_id,
        session_repository=session_repo,
        edit_repository=edit_repo,
    )
    assert len(detail.edits) == 1
    assert detail.current_score is not None


def test_list_findings_unknown_session_raises(session_repo: InMemorySessionRepository) -> None:
    with pytest.raises(SessionNotFound):
        list_findings("unknown", session_repository=session_repo)
