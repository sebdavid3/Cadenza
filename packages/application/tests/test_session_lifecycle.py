"""Pruebas unitarias del ciclo de vida de la sesión (Issue #34, ADR-0014)."""

from __future__ import annotations

import tempfile
from fractions import Fraction
from pathlib import Path

import pytest
from cadenza.application import (
    Forbidden,
    InMemoryArtifactStore,
    InMemoryEditEventRepository,
    InMemorySessionRepository,
    Role,
    SessionClosed,
    SessionNotFound,
    SessionStatus,
    User,
    append_edit,
    finalize_session,
    reopen_session,
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


class DummyOMREngine(OMREngine):
    """Motor sintético que genera un compás de 4/4 con 3 negras (desbalanceado)."""

    @property
    def engine_id(self) -> str:
        return "dummy-omr"

    @property
    def model_version(self) -> str:
        return "1.0.0"

    def transcribe(self, image_path: Path) -> ScoreDocument:
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
            id="doc-lifecycle-test",
            score=score,
            anchors=build_anchor_index(score),
            provenance=Provenance(omr_engine=self.engine_id, model_version=self.model_version),
        )


@pytest.fixture
def users() -> tuple[User, User, User]:
    owner = User(
        id="user-owner",
        username="owner",
        password_hash="h",
        role=Role.TRANSCRIPTOR,
        active=True,
    )
    other = User(
        id="user-other",
        username="other",
        password_hash="h",
        role=Role.TRANSCRIPTOR,
        active=True,
    )
    researcher = User(
        id="user-researcher",
        username="investigador",
        password_hash="h",
        role=Role.INVESTIGADOR,
        active=True,
    )
    return owner, other, researcher


@pytest.fixture
def validator() -> ValidationEngine:
    return ValidationEngine([MeasureBalanceRule()])


def _create_session(
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
            omr_engine=DummyOMREngine(),
            validator=validator,
            session_repository=session_repo,
            current_user=owner,
            artifact_store=store,
        )
        return res.session_id
    finally:
        if img_path.is_file():
            img_path.unlink()


def test_initial_session_status_is_transcribed(
    users: tuple[User, User, User], validator: ValidationEngine
) -> None:
    owner, _, _ = users
    session_repo = InMemorySessionRepository()
    store = InMemoryArtifactStore()

    session_id = _create_session(owner, validator, session_repo, store)
    session_data = session_repo.get(session_id)
    assert session_data is not None
    assert session_data.status == SessionStatus.TRANSCRIBED


def test_first_edit_transitions_status_to_correcting(
    users: tuple[User, User, User],
    validator: ValidationEngine,
) -> None:
    owner, _, _ = users
    session_repo = InMemorySessionRepository()
    edit_repo = InMemoryEditEventRepository()
    store = InMemoryArtifactStore()

    session_id = _create_session(owner, validator, session_repo, store)
    init_data = session_repo.get(session_id)
    assert init_data is not None
    assert init_data.status == SessionStatus.TRANSCRIBED

    # Añadir primera edición (cambiar tono del primer evento de C4 a C#4)
    target_anchor = Anchor(
        part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="part-0-staff-0"
    )
    append_edit(
        session_id,
        anchor=target_anchor,
        op=EditOp.SET_PITCH,
        base_seq=0,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=owner,
        before={"pitch": "C4"},
        after={"pitch": "C#4"},
    )

    session_data = session_repo.get(session_id)
    assert session_data is not None
    assert session_data.status == SessionStatus.CORRECTING


def test_finalize_revalidates_and_marks_session_finalized(
    users: tuple[User, User, User],
    validator: ValidationEngine,
) -> None:
    owner, _, _ = users
    session_repo = InMemorySessionRepository()
    edit_repo = InMemoryEditEventRepository()
    store = InMemoryArtifactStore()

    session_id = _create_session(owner, validator, session_repo, store)

    # Añadir una nota para balancear el compás (seq=1)
    insert_anchor = Anchor(
        part=0, staff=0, measure=1, voice=0, event_index=3, staff_id="part-0-staff-0"
    )
    append_edit(
        session_id,
        anchor=insert_anchor,
        op=EditOp.INSERT_EVENT,
        base_seq=0,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=owner,
        after={"pitch": "F4", "duration_beats": Fraction(1), "kind": "note"},
    )

    # Finalizar la sesión
    result = finalize_session(
        session_id,
        validator=validator,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=owner,
    )

    assert result.session_id == session_id
    assert result.status == SessionStatus.FINALIZED
    assert result.final_seq == 1
    # Tras insertar la 4ta negra, el compás 4/4 está balanceado (0 hallazgos)
    assert len(result.findings) == 0

    session_data = session_repo.get(session_id)
    assert session_data is not None
    assert session_data.status == SessionStatus.FINALIZED
    assert session_data.validated_at_seq == 1


def test_append_edit_on_finalized_session_raises_session_closed(
    users: tuple[User, User, User],
    validator: ValidationEngine,
) -> None:
    owner, _, _ = users
    session_repo = InMemorySessionRepository()
    edit_repo = InMemoryEditEventRepository()
    store = InMemoryArtifactStore()

    session_id = _create_session(owner, validator, session_repo, store)

    finalize_session(
        session_id,
        validator=validator,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=owner,
    )

    # Intento de editar una sesión finalizada
    target_anchor = Anchor(
        part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="part-0-staff-0"
    )
    with pytest.raises(SessionClosed, match="finalizada"):
        append_edit(
            session_id,
            anchor=target_anchor,
            op=EditOp.SET_PITCH,
            base_seq=0,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=owner,
            before={"pitch": "C4"},
            after={"pitch": "D4"},
        )


def test_reopen_session_allows_further_edits(
    users: tuple[User, User, User],
    validator: ValidationEngine,
) -> None:
    owner, _, _ = users
    session_repo = InMemorySessionRepository()
    edit_repo = InMemoryEditEventRepository()
    store = InMemoryArtifactStore()

    session_id = _create_session(owner, validator, session_repo, store)

    # Finalizar
    finalize_session(
        session_id,
        validator=validator,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=owner,
    )
    final_data = session_repo.get(session_id)
    assert final_data is not None
    assert final_data.status == SessionStatus.FINALIZED

    # Reabrir
    reopen_res = reopen_session(
        session_id,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=owner,
    )
    assert reopen_res.status in (SessionStatus.CORRECTING, SessionStatus.TRANSCRIBED)
    reopened_data = session_repo.get(session_id)
    assert reopened_data is not None
    assert reopened_data.status != SessionStatus.FINALIZED

    # Ahora sí debe permitir editar
    target_anchor = Anchor(
        part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="part-0-staff-0"
    )
    edit = append_edit(
        session_id,
        anchor=target_anchor,
        op=EditOp.SET_PITCH,
        base_seq=0,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=owner,
        before={"pitch": "C4"},
        after={"pitch": "D4"},
    )
    assert edit.seq == 1
    post_edit_data = session_repo.get(session_id)
    assert post_edit_data is not None
    assert post_edit_data.status == SessionStatus.CORRECTING


def test_permissions_on_finalize_and_reopen(
    users: tuple[User, User, User],
    validator: ValidationEngine,
) -> None:
    owner, other, researcher = users
    session_repo = InMemorySessionRepository()
    edit_repo = InMemoryEditEventRepository()
    store = InMemoryArtifactStore()

    session_id = _create_session(owner, validator, session_repo, store)

    # Transcriptor ajeno -> SessionNotFound (404)
    with pytest.raises(SessionNotFound):
        finalize_session(
            session_id,
            validator=validator,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=other,
        )
    with pytest.raises(SessionNotFound):
        reopen_session(
            session_id,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=other,
        )

    # Investigador sobre sesión ajena -> Forbidden (403)
    with pytest.raises(Forbidden):
        finalize_session(
            session_id,
            validator=validator,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=researcher,
        )
    with pytest.raises(Forbidden):
        reopen_session(
            session_id,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=researcher,
        )

    # Sesión inexistente -> SessionNotFound
    with pytest.raises(SessionNotFound):
        finalize_session(
            "unknown-id",
            validator=validator,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=owner,
        )
    with pytest.raises(SessionNotFound):
        reopen_session(
            "unknown-id",
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=owner,
        )


def test_session_repository_filter_by_status(
    users: tuple[User, User, User],
    validator: ValidationEngine,
) -> None:
    owner, _, _ = users
    session_repo = InMemorySessionRepository()
    store = InMemoryArtifactStore()
    edit_repo = InMemoryEditEventRepository()

    s1 = _create_session(owner, validator, session_repo, store)
    s2 = _create_session(owner, validator, session_repo, store)

    # Ambas inician en transcribed
    assert len(session_repo.list(status=SessionStatus.TRANSCRIBED)) == 2
    assert len(session_repo.list(status=SessionStatus.FINALIZED)) == 0

    # Finalizar s1
    finalize_session(
        s1,
        validator=validator,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=owner,
    )

    assert len(session_repo.list(status=SessionStatus.TRANSCRIBED)) == 1
    assert session_repo.list(status=SessionStatus.TRANSCRIBED)[0].id == s2
    assert len(session_repo.list(status=SessionStatus.FINALIZED)) == 1
    assert session_repo.list(status=SessionStatus.FINALIZED)[0].id == s1
