"""Pruebas de validación de ediciones antes de añadirlas al log (Issue #10, ADR-0007, ADR-0011)."""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from pathlib import Path

import pytest
from cadenza.application import (
    InvalidEdit,
    Role,
    SequenceConflict,
    User,
    append_edit,
    get_session,
    transcribe_score,
)
from cadenza.application.ports import (
    EditEventRepository,
    InMemoryArtifactStore,
    PersistedFinding,
    SessionData,
    SessionRepository,
)
from cadenza.domain import Anchor, EditEvent, EditOp, Finding
from cadenza.omr import FakeOMREngine
from cadenza.validation import ValidationEngine


class InMemorySessionRepo(SessionRepository):
    def __init__(self) -> None:
        self.sessions: dict[str, SessionData] = {}
        self.findings: dict[str, list[PersistedFinding]] = {}

    def add(self, session: SessionData, findings: Sequence[Finding]) -> SessionData:
        self.sessions[session.id] = session
        self.findings[session.id] = []
        return session

    def get(self, session_id: str) -> SessionData | None:
        return self.sessions.get(session_id)

    def list_findings(self, session_id: str) -> tuple[PersistedFinding, ...]:
        return tuple(self.findings.get(session_id, []))

    def list(self, owner_id: str | None = None) -> tuple[SessionData, ...]:
        if owner_id is not None:
            return tuple(s for s in self.sessions.values() if s.owner_id == owner_id)
        return tuple(self.sessions.values())


class InMemoryEditRepo(EditEventRepository):
    def __init__(self) -> None:
        self.events: dict[str, list[EditEvent]] = {}

    def next_seq(self, session_id: str) -> int:
        return len(self.events.get(session_id, [])) + 1

    def append(self, session_id: str, edit: EditEvent) -> EditEvent:
        events = self.events.setdefault(session_id, [])
        if any(e.seq == edit.seq for e in events):
            raise SequenceConflict(
                expected_seq=edit.seq,
                actual_seq=edit.seq,
                message=(
                    f"Conflicto de secuencia: ya existe seq={edit.seq} "
                    f"en la sesión '{session_id}'"
                ),
            )

        events.append(edit)
        return edit

    def list_events(self, session_id: str) -> tuple[EditEvent, ...]:
        return tuple(self.events.get(session_id, []))


PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20


@pytest.fixture
def test_setup() -> tuple[str, User, InMemorySessionRepo, InMemoryEditRepo]:
    owner = User(
        id="u1", username="transcriptor1", password_hash="h", role=Role.TRANSCRIPTOR, active=True
    )
    session_repo = InMemorySessionRepo()
    edit_repo = InMemoryEditRepo()
    store = InMemoryArtifactStore()

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(PNG_HEADER)
        img_path = Path(f.name)

    try:
        result = transcribe_score(
            img_path,
            omr_engine=FakeOMREngine(),
            validator=ValidationEngine([]),
            session_repository=session_repo,
            current_user=owner,
            artifact_store=store,
        )
    finally:
        if img_path.is_file():
            img_path.unlink()

    return result.session_id, owner, session_repo, edit_repo


def _anchor(measure: int, event_index: int) -> Anchor:
    return Anchor(
        part=0,
        staff=0,
        staff_id="part-0-staff-0",
        measure=measure,
        voice=0,
        event_index=event_index,
    )


def test_append_edit_rejects_non_existent_anchor(
    test_setup: tuple[str, User, InMemorySessionRepo, InMemoryEditRepo],
) -> None:
    session_id, user, session_repo, edit_repo = test_setup

    # Compás 99 no existe en el documento
    invalid_anchor = _anchor(measure=99, event_index=0)
    with pytest.raises(InvalidEdit) as exc_info:
        append_edit(
            session_id,
            anchor=invalid_anchor,
            op=EditOp.SET_PITCH,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=user,
            after={"pitch": "D4"},
        )

    assert (
        "compás inexistente" in str(exc_info.value).lower()
        or "no aplicable" in str(exc_info.value).lower()
    )
    # No se guardó nada en el log
    assert len(edit_repo.list_events(session_id)) == 0


def test_append_edit_rejects_out_of_range_event_index(
    test_setup: tuple[str, User, InMemorySessionRepo, InMemoryEditRepo],
) -> None:
    session_id, user, session_repo, edit_repo = test_setup

    # Compás 1 sólo tiene 3 eventos (índices 0, 1, 2)
    invalid_anchor = _anchor(measure=1, event_index=99)
    with pytest.raises(InvalidEdit) as exc_info:
        append_edit(
            session_id,
            anchor=invalid_anchor,
            op=EditOp.SET_PITCH,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=user,
            after={"pitch": "D4"},
        )

    assert (
        "inexistente" in str(exc_info.value).lower()
        or "fuera de rango" in str(exc_info.value).lower()
    )
    assert len(edit_repo.list_events(session_id)) == 0


def test_append_edit_rejects_mismatched_before(
    test_setup: tuple[str, User, InMemorySessionRepo, InMemoryEditRepo],
) -> None:
    session_id, user, session_repo, edit_repo = test_setup

    # El evento en measure=1, event_index=0 es "C4"
    anchor = _anchor(measure=1, event_index=0)

    # Cliente envía before="E4" (desfasado respecto al estado actual "C4")
    with pytest.raises(InvalidEdit) as exc_info:
        append_edit(
            session_id,
            anchor=anchor,
            op=EditOp.SET_PITCH,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=user,
            before={"pitch": "E4"},
            after={"pitch": "D4"},
        )

    assert "before" in str(exc_info.value).lower()
    assert "no coincide" in str(exc_info.value).lower()
    assert len(edit_repo.list_events(session_id)) == 0


def test_append_edit_success_with_matching_before(
    test_setup: tuple[str, User, InMemorySessionRepo, InMemoryEditRepo],
) -> None:
    session_id, user, session_repo, edit_repo = test_setup

    anchor = _anchor(measure=1, event_index=0)

    # Enviando before coincidente "C4"
    edit = append_edit(
        session_id,
        anchor=anchor,
        op=EditOp.SET_PITCH,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=user,
        before={"pitch": "C4"},
        after={"pitch": "D4"},
    )

    assert edit.seq == 1
    assert len(edit_repo.list_events(session_id)) == 1

    # Al consultar la sesión, el estado se proyecta con current_seq y anchor_index
    detail = get_session(
        session_id,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=user,
    )
    assert detail.current_seq == 1
    assert detail.current_score is not None
    assert detail.anchor_index is not None
    # El evento 0 ahora tiene pitch D4
    projected_pitch = detail.current_score["parts"][0]["staves"][0]["measures"][0]["events"][0][
        "pitch"
    ]
    assert projected_pitch == "D4"


def test_append_edit_sequence_conflict(
    test_setup: tuple[str, User, InMemorySessionRepo, InMemoryEditRepo],
) -> None:
    session_id, user, session_repo, edit_repo = test_setup
    anchor = _anchor(measure=1, event_index=0)

    # Primera edición normal (base_seq=0)
    append_edit(
        session_id,
        base_seq=0,
        anchor=anchor,
        op=EditOp.SET_PITCH,
        session_repository=session_repo,
        edit_repository=edit_repo,
        current_user=user,
        after={"pitch": "D4"},
    )

    # Intento de edición con base_seq obsoleto (base_seq=0 cuando la sesión ya está en seq=1)
    with pytest.raises(SequenceConflict) as exc_info:
        append_edit(
            session_id,
            base_seq=0,
            anchor=anchor,
            op=EditOp.SET_PITCH,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=user,
            before={"pitch": "D4"},
            after={"pitch": "E4"},
        )
    assert exc_info.value.expected_seq == 1
    assert exc_info.value.actual_seq == 0

    # Simular intento concurrente de insertar con seq duplicado en el repositorio (seq=1)
    from datetime import UTC, datetime

    conflicting_edit = EditEvent(
        id="edit-conflict",
        document_id="fake-doc-0001",
        seq=1,
        anchor=anchor,
        op=EditOp.SET_PITCH,
        author=user.username,
        created_at=datetime.now(UTC),
        after={"pitch": "E4"},
    )
    with pytest.raises(SequenceConflict):
        edit_repo.append(session_id, conflicting_edit)


def test_get_session_does_not_silence_projection_errors(
    test_setup: tuple[str, User, InMemorySessionRepo, InMemoryEditRepo],
) -> None:
    session_id, user, session_repo, edit_repo = test_setup

    # Inyectar directamente en el repositorio una edición corrupta que no pasó por append_edit
    from datetime import UTC, datetime

    corrupt_anchor = _anchor(measure=999, event_index=0)
    corrupt_edit = EditEvent(
        id="corrupt-1",
        document_id="fake-doc-0001",
        seq=1,
        anchor=corrupt_anchor,
        op=EditOp.SET_PITCH,
        author=user.username,
        created_at=datetime.now(UTC),
        after={"pitch": "D4"},
    )
    edit_repo.append(session_id, corrupt_edit)

    # get_session no silencia el fallo devolviendo current_score=None, sino que lanza IndexError
    with pytest.raises(IndexError):
        get_session(
            session_id,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=user,
        )
