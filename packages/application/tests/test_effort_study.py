"""Pruebas del protocolo y registro de esfuerzo con participantes (#33, D38)."""

from __future__ import annotations

from pathlib import Path

import pytest
from cadenza.application import (
    InMemoryEditEventRepository,
    InMemorySessionRepository,
    Role,
    User,
    get_session,
    list_sessions,
    normalize_condition,
    revalidate,
    transcribe_score,
)
from cadenza.domain import Anchor, Finding, Severity
from cadenza.omr import FakeOMREngine
from cadenza.validation import MeasureBalanceRule, ValidationEngine, ValidationRule


class AlwaysFailingRule(ValidationRule):
    """Regla simulada que siempre emite un hallazgo de prueba."""

    @property
    def rule_id(self) -> str:
        return "MOCK-001"

    def evaluate(self, document: object) -> list[Finding]:
        return [
            Finding(
                rule_id=self.rule_id,
                severity=Severity.ERROR,
                message="Error simulado para prueba de validador",
                suggested_fix="Corrección sugerida",
                anchor=Anchor(
                    part=0,
                    staff=0,
                    measure=1,
                    voice=1,
                    event_index=0,
                    staff_id="part-0-staff-0",
                ),
            )
        ]


@pytest.fixture
def session_repo() -> InMemorySessionRepository:
    return InMemorySessionRepository()


@pytest.fixture
def edit_repo() -> InMemoryEditEventRepository:
    return InMemoryEditEventRepository()


@pytest.fixture
def participant() -> User:
    return User(id="usr-p01", username="P01", password_hash="hash", role=Role.TRANSCRIPTOR)


@pytest.fixture
def researcher() -> User:
    return User(id="usr-res", username="investigador", password_hash="hash", role=Role.INVESTIGADOR)


def test_normalize_condition_canonical_values() -> None:
    assert normalize_condition("assisted") == "assisted"
    assert normalize_condition("asistida") == "assisted"
    assert normalize_condition("con_validador") == "assisted"
    assert normalize_condition("con-validador") == "assisted"
    assert normalize_condition(None) == "assisted"
    assert normalize_condition("") == "assisted"

    assert normalize_condition("unassisted") == "unassisted"
    assert normalize_condition("no_asistida") == "unassisted"
    assert normalize_condition("no-asistida") == "unassisted"
    assert normalize_condition("sin_validador") == "unassisted"
    assert normalize_condition("sin-validador") == "unassisted"


def test_normalize_condition_invalid_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Condición inválida"):
        normalize_condition("automatic")

    with pytest.raises(ValueError, match="Condición inválida"):
        normalize_condition("random_condition")


def test_transcribe_score_unassisted_suppresses_validator_findings(
    tmp_path: Path,
    session_repo: InMemorySessionRepository,
    participant: User,
) -> None:
    fake_img = tmp_path / "score.png"
    fake_img.write_bytes(b"dummy")

    result = transcribe_score(
        fake_img,
        omr_engine=FakeOMREngine(),
        validator=ValidationEngine([AlwaysFailingRule()]),
        session_repository=session_repo,
        current_user=participant,
        condition="unassisted",
        test_score_id="TS-01",
    )

    assert result.condition == "unassisted"
    assert result.test_score_id == "TS-01"
    # En condición no asistida, no debe generarse ningún hallazgo
    assert result.findings_count == 0

    session_data = session_repo.get(result.session_id)
    assert session_data is not None
    assert session_data.condition == "unassisted"
    assert session_data.test_score_id == "TS-01"
    assert session_data.owner_id == participant.id
    assert len(session_repo.list_findings(result.session_id)) == 0


def test_transcribe_score_assisted_keeps_validator_findings(
    tmp_path: Path,
    session_repo: InMemorySessionRepository,
    participant: User,
) -> None:
    fake_img = tmp_path / "score.png"
    fake_img.write_bytes(b"dummy")

    result = transcribe_score(
        fake_img,
        omr_engine=FakeOMREngine(),
        validator=ValidationEngine([AlwaysFailingRule()]),
        session_repository=session_repo,
        current_user=participant,
        condition="assisted",
        test_score_id="TS-02",
    )

    assert result.condition == "assisted"
    assert result.test_score_id == "TS-02"
    assert result.findings_count == 1
    assert len(session_repo.list_findings(result.session_id)) == 1


def test_revalidate_unassisted_session_returns_zero_findings(
    tmp_path: Path,
    session_repo: InMemorySessionRepository,
    edit_repo: InMemoryEditEventRepository,
    participant: User,
) -> None:
    fake_img = tmp_path / "score.png"
    fake_img.write_bytes(b"dummy")

    result = transcribe_score(
        fake_img,
        omr_engine=FakeOMREngine(),
        validator=ValidationEngine([AlwaysFailingRule()]),
        session_repository=session_repo,
        current_user=participant,
        condition="unassisted",
        test_score_id="TS-03",
    )

    rev_result = revalidate(
        result.session_id,
        validator=ValidationEngine([AlwaysFailingRule()]),
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=participant,
    )

    assert len(rev_result.findings) == 0
    assert len(session_repo.list_findings(result.session_id)) == 0


def test_get_session_and_list_sessions_filters(
    tmp_path: Path,
    session_repo: InMemorySessionRepository,
    edit_repo: InMemoryEditEventRepository,
    participant: User,
    researcher: User,
) -> None:
    fake_img = tmp_path / "score.png"
    fake_img.write_bytes(b"dummy")

    s1 = transcribe_score(
        fake_img,
        omr_engine=FakeOMREngine(),
        validator=ValidationEngine([MeasureBalanceRule()]),
        session_repository=session_repo,
        current_user=participant,
        condition="assisted",
        test_score_id="TS-01",
    )

    s2 = transcribe_score(
        fake_img,
        omr_engine=FakeOMREngine(),
        validator=ValidationEngine([MeasureBalanceRule()]),
        session_repository=session_repo,
        current_user=participant,
        condition="unassisted",
        test_score_id="TS-02",
    )

    detail1 = get_session(
        s1.session_id,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=participant,
    )
    assert detail1.condition == "assisted"
    assert detail1.test_score_id == "TS-01"
    assert detail1.owner_id == participant.id

    # Listados filtrados
    summaries_ast = list_sessions(
        session_repository=session_repo,
        current_user=researcher,
        condition="assisted",
    )
    assert len(summaries_ast) == 1
    assert summaries_ast[0].session_id == s1.session_id

    summaries_una = list_sessions(
        session_repository=session_repo,
        current_user=researcher,
        condition="unassisted",
    )
    assert len(summaries_una) == 1
    assert summaries_una[0].session_id == s2.session_id

    summaries_ts2 = list_sessions(
        session_repository=session_repo,
        current_user=researcher,
        test_score_id="TS-02",
    )
    assert len(summaries_ts2) == 1
    assert summaries_ts2[0].test_score_id == "TS-02"
