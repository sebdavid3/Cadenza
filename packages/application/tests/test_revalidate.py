"""Pruebas unitarias del caso de uso revalidate (Issue #11, ADR-0013)."""

from __future__ import annotations

import tempfile
from fractions import Fraction
from pathlib import Path

import pytest
from cadenza.application import (
    InMemoryArtifactStore,
    InMemoryEditEventRepository,
    InMemorySessionRepository,
    Role,
    SessionNotFound,
    User,
    append_edit,
    list_findings,
    revalidate,
    transcribe_score,
)
from cadenza.domain import (
    Anchor,
    EditOp,
    Event,
    EventKind,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Staff,
    TimeSignature,
    build_anchor_index,
)
from cadenza.omr import OMREngine
from cadenza.validation import MeasureBalanceRule, ValidationEngine

PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20


class UnbalancedOMREngine(OMREngine):
    """Motor OMR sintético que genera un compás desbalanceado inicialmente."""

    @property
    def engine_id(self) -> str:
        return "unbalanced-fake"

    @property
    def model_version(self) -> str:
        return "1.0.0"

    def transcribe(self, image_path: Path) -> ScoreDocument:
        # 4/4 pero compás con 3 negras (3 tiempos en vez de 4)
        m1 = Measure(
            number=1,
            events=(
                Event(kind=EventKind.NOTE, voice=0, pitch="C4", duration_beats=Fraction(1)),
                Event(kind=EventKind.NOTE, voice=0, pitch="D4", duration_beats=Fraction(1)),
                Event(kind=EventKind.NOTE, voice=0, pitch="E4", duration_beats=Fraction(1)),
            ),
            time_signature=TimeSignature(4, 4),
        )
        score = ScoreIR(
            parts=(Part(id="part-0", staves=(Staff(id="part-0-staff-0", measures=(m1,)),)),)
        )
        return ScoreDocument(
            id="doc-unbalanced",
            score=score,
            anchors=build_anchor_index(score),
            provenance=Provenance(omr_engine=self.engine_id, model_version=self.model_version),
        )


@pytest.fixture
def users() -> tuple[User, User, User]:
    owner = User(
        id="u1", username="transcriptor1", password_hash="h", role=Role.TRANSCRIPTOR, active=True
    )
    other = User(
        id="u2", username="transcriptor2", password_hash="h", role=Role.TRANSCRIPTOR, active=True
    )
    researcher = User(
        id="u3", username="investigador1", password_hash="h", role=Role.INVESTIGADOR, active=True
    )
    return owner, other, researcher


@pytest.fixture
def validator() -> ValidationEngine:
    return ValidationEngine([MeasureBalanceRule()])


def _transcribe_initial(
    engine: OMREngine,
    owner: User,
    validator: ValidationEngine,
    session_repo: InMemorySessionRepository,
    store: InMemoryArtifactStore,
) -> str:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(PNG_HEADER)
        img_path = Path(f.name)
    try:
        res = transcribe_score(
            img_path,
            omr_engine=engine,
            validator=validator,
            session_repository=session_repo,
            current_user=owner,
            artifact_store=store,
        )
        return res.session_id
    finally:
        if img_path.is_file():
            img_path.unlink()


def test_revalidate_resolves_error_and_preserves_history(
    users: tuple[User, User, User],
    validator: ValidationEngine,
) -> None:
    owner, _, _ = users
    session_repo = InMemorySessionRepository()
    edit_repo = InMemoryEditEventRepository()
    store = InMemoryArtifactStore()

    session_id = _transcribe_initial(
        UnbalancedOMREngine(),
        owner,
        validator,
        session_repo,
        store,
    )

    # 1. Al inicio hay 1 hallazgo de desbalance en at_seq = 0
    initial_findings = list_findings(
        session_id, session_repository=session_repo, current_user=owner
    )
    assert len(initial_findings) == 1
    assert initial_findings[0].at_seq == 0
    assert initial_findings[0].rule_id == "measure.balance"

    # 2. Corregir el compás insertando 1 tiempo faltante (SetDuration de C4 de 1 a 2 tiempos)
    anchor = Anchor(part=0, staff=0, staff_id="part-0-staff-0", measure=1, voice=0, event_index=0)
    append_edit(
        session_id,
        base_seq=0,
        anchor=anchor,
        op=EditOp.SET_DURATION,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=owner,
        after={"duration_beats": "2"},
    )

    # Antes de revalidar, los hallazgos vigentes siguen siendo los de at_seq = 0
    findings_before = list_findings(session_id, session_repository=session_repo, current_user=owner)
    assert len(findings_before) == 1

    # 3. Ejecutar revalidación
    result = revalidate(
        session_id,
        validator=validator,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=owner,
    )

    assert result.session_id == session_id
    assert result.current_seq == 1
    assert len(result.findings) == 0  # El error fue corregido

    # 4. Los hallazgos vigentes ahora están vacíos
    current_findings = list_findings(
        session_id,
        session_repository=session_repo,
        current_user=owner,
        latest_only=True,
    )
    assert len(current_findings) == 0

    # 5. El hallazgo histórico previo se conserva para análisis de esfuerzo (ADR-0013)
    historical_all = list_findings(
        session_id,
        session_repository=session_repo,
        current_user=owner,
        latest_only=False,
    )
    assert len(historical_all) == 1
    assert historical_all[0].at_seq == 0

    seq0_findings = list_findings(
        session_id,
        session_repository=session_repo,
        current_user=owner,
        at_seq=0,
    )
    assert len(seq0_findings) == 1


def test_revalidate_detects_new_error_introduced_by_edit(
    users: tuple[User, User, User],
    validator: ValidationEngine,
) -> None:
    owner, _, _ = users
    session_repo = InMemorySessionRepository()
    edit_repo = InMemoryEditEventRepository()
    store = InMemoryArtifactStore()

    # Empezamos con un documento balanceado (FakeOMREngine)
    from cadenza.omr import FakeOMREngine

    session_id = _transcribe_initial(
        FakeOMREngine(),
        owner,
        validator,
        session_repo,
        store,
    )

    # 1. Inicialmente 0 hallazgos
    initial_findings = list_findings(
        session_id, session_repository=session_repo, current_user=owner
    )
    assert len(initial_findings) == 0

    # 2. Edición que desbalancea el compás 1 (SetDuration C4 a 3 tiempos -> 6 de 4)
    anchor = Anchor(part=0, staff=0, staff_id="part-0-staff-0", measure=1, voice=0, event_index=0)
    append_edit(
        session_id,
        base_seq=0,
        anchor=anchor,
        op=EditOp.SET_DURATION,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=owner,
        after={"duration_beats": "3"},
    )

    # 3. Revalidar
    result = revalidate(
        session_id,
        validator=validator,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=owner,
    )

    assert result.current_seq == 1
    assert len(result.findings) == 1
    assert result.findings[0].at_seq == 1
    assert result.findings[0].rule_id == "measure.balance"

    # 4. Los hallazgos vigentes ahora muestran este nuevo hallazgo
    vigentes = list_findings(session_id, session_repository=session_repo, current_user=owner)
    assert len(vigentes) == 1
    assert vigentes[0].at_seq == 1


def test_revalidate_permissions(
    users: tuple[User, User, User],
    validator: ValidationEngine,
) -> None:
    owner, other, researcher = users
    session_repo = InMemorySessionRepository()
    edit_repo = InMemoryEditEventRepository()
    store = InMemoryArtifactStore()

    session_id = _transcribe_initial(
        UnbalancedOMREngine(),
        owner,
        validator,
        session_repo,
        store,
    )

    # Otro transcriptor no puede revalidar (SessionNotFound según ADR-0012)
    with pytest.raises(SessionNotFound):
        revalidate(
            session_id,
            validator=validator,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=other,
        )

    # Un investigador sí puede revalidar
    res = revalidate(
        session_id,
        validator=validator,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=researcher,
    )
    assert res.session_id == session_id

    # Sesión inexistente lanza SessionNotFound
    with pytest.raises(SessionNotFound):
        revalidate(
            "non-existent-session",
            validator=validator,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=owner,
        )


def test_revalidate_is_idempotent_on_same_seq(
    users: tuple[User, User, User],
    validator: ValidationEngine,
) -> None:
    owner, _, _ = users
    session_repo = InMemorySessionRepository()
    edit_repo = InMemoryEditEventRepository()
    store = InMemoryArtifactStore()

    session_id = _transcribe_initial(
        UnbalancedOMREngine(),
        owner,
        validator,
        session_repo,
        store,
    )

    # 1. Revalidar en seq=0 dos veces consecutivas sin ediciones
    res1 = revalidate(
        session_id,
        validator=validator,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=owner,
    )
    res2 = revalidate(
        session_id,
        validator=validator,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=owner,
    )

    assert len(res1.findings) == 1
    assert len(res2.findings) == 1

    # Los hallazgos vigentes no se duplican
    vigentes = list_findings(session_id, session_repository=session_repo, current_user=owner)
    assert len(vigentes) == 1

    # Y en el historial completo tampoco hay duplicados
    historico = list_findings(
        session_id,
        session_repository=session_repo,
        current_user=owner,
        latest_only=False,
    )
    assert len(historico) == 1
