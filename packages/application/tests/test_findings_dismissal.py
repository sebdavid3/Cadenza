"""Pruebas unitarias de casos de uso y repositorio en memoria para descarte de hallazgos (#36)."""

from __future__ import annotations

import pytest
from cadenza.application import (
    FindingNotFound,
    Forbidden,
    InMemorySessionRepository,
    Role,
    SessionClosed,
    SessionData,
    SessionNotFound,
    SessionStatus,
    User,
    dismiss_finding,
    list_findings,
    restore_finding,
)
from cadenza.domain import Anchor, Finding, Severity


def _sample_anchor() -> Anchor:
    return Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="part-0-staff-0")


def _setup_session_repo() -> tuple[InMemorySessionRepository, str, int]:
    repo = InMemorySessionRepository()
    session = SessionData(
        id="sess-1",
        owner_id="owner-1",
        document_id="doc-1",
        omr_engine="fake",
        document={},
    )
    f1 = Finding(
        rule_id="measure.balance",
        severity=Severity.ERROR,
        message="Compás incompleto",
        suggested_fix=None,
        anchor=_sample_anchor(),
        at_seq=0,
    )
    repo.add(session, [f1])
    findings = repo.list_findings("sess-1", include_dismissed=True)
    return repo, "sess-1", findings[0].id


def test_dismiss_and_restore_use_case_with_in_memory_repo() -> None:
    repo, session_id, finding_id = _setup_session_repo()
    owner = User(id="owner-1", username="alice", password_hash="h", role=Role.TRANSCRIPTOR)

    # 1. Descartar hallazgo
    dismissed = dismiss_finding(
        session_id,
        finding_id,
        session_repository=repo,
        current_user=owner,
        reason="Falso positivo confirmado",
    )
    assert dismissed.status == "dismissed"
    assert dismissed.dismissed_by == "alice"
    assert dismissed.dismissal_reason == "Falso positivo confirmado"
    assert dismissed.dismissed_at is not None

    # 2. list_findings filtra descartados por defecto
    active = list_findings(session_id, session_repository=repo, current_user=owner)
    assert len(active) == 0

    # 3. list_findings incluye descartados si include_dismissed=True
    all_findings = list_findings(
        session_id,
        session_repository=repo,
        current_user=owner,
        include_dismissed=True,
    )
    assert len(all_findings) == 1
    assert all_findings[0].status == "dismissed"

    # 4. list_dismissed_findings devuelve el hallazgo
    dismissed_list = repo.list_dismissed_findings(session_id)
    assert len(dismissed_list) == 1
    assert dismissed_list[0].id == finding_id

    # 5. list_summaries cuenta solo activos
    summaries = repo.list_summaries(owner_id="owner-1")
    assert len(summaries) == 1
    assert summaries[0].findings_count == 0

    # 6. Restaurar hallazgo
    restored = restore_finding(
        session_id,
        finding_id,
        session_repository=repo,
        current_user=owner,
    )
    assert restored.status == "active"
    assert restored.dismissed_at is None
    assert restored.dismissed_by is None
    assert restored.dismissal_reason is None

    # 7. Ahora reaparece en la lista activa
    active_again = list_findings(session_id, session_repository=repo, current_user=owner)
    assert len(active_again) == 1
    assert active_again[0].id == finding_id


def test_dismiss_and_restore_authorization_and_lifecycle_in_memory() -> None:
    repo, session_id, finding_id = _setup_session_repo()
    owner = User(id="owner-1", username="alice", password_hash="h", role=Role.TRANSCRIPTOR)
    other = User(id="other-1", username="bob", password_hash="h", role=Role.TRANSCRIPTOR)
    researcher = User(id="res-1", username="carol", password_hash="h", role=Role.INVESTIGADOR)

    # Transcriptor ajeno -> SessionNotFound (404)
    with pytest.raises(SessionNotFound):
        dismiss_finding(
            session_id,
            finding_id,
            session_repository=repo,
            current_user=other,
        )
    with pytest.raises(SessionNotFound):
        restore_finding(
            session_id,
            finding_id,
            session_repository=repo,
            current_user=other,
        )

    # Investigador ajeno -> Forbidden (403)
    with pytest.raises(Forbidden):
        dismiss_finding(
            session_id,
            finding_id,
            session_repository=repo,
            current_user=researcher,
        )
    with pytest.raises(Forbidden):
        restore_finding(
            session_id,
            finding_id,
            session_repository=repo,
            current_user=researcher,
        )

    # Sesión inexistente -> SessionNotFound
    with pytest.raises(SessionNotFound):
        dismiss_finding(
            "nonexistent",
            finding_id,
            session_repository=repo,
            current_user=owner,
        )

    # Hallazgo inexistente -> FindingNotFound
    with pytest.raises(FindingNotFound):
        dismiss_finding(
            session_id,
            9999,
            session_repository=repo,
            current_user=owner,
        )
    with pytest.raises(FindingNotFound):
        restore_finding(
            session_id,
            9999,
            session_repository=repo,
            current_user=owner,
        )

    # Sesión finalizada -> SessionClosed (409)
    repo.update_status(session_id, SessionStatus.FINALIZED)
    with pytest.raises(SessionClosed):
        dismiss_finding(
            session_id,
            finding_id,
            session_repository=repo,
            current_user=owner,
        )
    with pytest.raises(SessionClosed):
        restore_finding(
            session_id,
            finding_id,
            session_repository=repo,
            current_user=owner,
        )
