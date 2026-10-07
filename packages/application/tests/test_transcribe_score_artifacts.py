"""Pruebas del almacenamiento de imagen en transcribe_score y get_session_image (#9)."""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from pathlib import Path

import pytest
from cadenza.application import (
    InMemoryArtifactStore,
    Role,
    SessionNotFound,
    User,
    detect_image_media_type,
    get_session_image,
    is_image_content,
    transcribe_score,
)
from cadenza.application.ports.session_repository import (
    PersistedFinding,
    SessionData,
    SessionRepository,
)
from cadenza.domain import Finding
from cadenza.omr import FakeOMREngine
from cadenza.validation import ValidationEngine


class InMemorySessionRepository(SessionRepository):
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


PNG_SAMPLE = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
)

JPEG_SAMPLE = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
PDF_SAMPLE = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"


def test_magic_detection_and_validation() -> None:
    assert is_image_content(PNG_SAMPLE) is True
    assert detect_image_media_type(PNG_SAMPLE) == "image/png"

    assert is_image_content(JPEG_SAMPLE) is True
    assert detect_image_media_type(JPEG_SAMPLE) == "image/jpeg"

    assert is_image_content(PDF_SAMPLE) is False
    assert is_image_content(b"not an image") is False
    assert is_image_content(b"") is False


def test_transcribe_score_stores_image_in_artifact_store() -> None:
    artifact_store = InMemoryArtifactStore()
    session_repo = InMemorySessionRepository()
    owner = User(
        id="user-1",
        username="transcriptor1",
        password_hash="h",
        role=Role.TRANSCRIPTOR,
        active=True,
    )

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(PNG_SAMPLE)
        img_path = Path(f.name)

    try:
        result = transcribe_score(
            img_path,
            omr_engine=FakeOMREngine(),
            validator=ValidationEngine([]),
            session_repository=session_repo,
            current_user=owner,
            artifact_store=artifact_store,
        )

        session = session_repo.get(result.session_id)
        assert session is not None
        assert session.image_artifact is not None
        assert artifact_store.exists(session.image_artifact)
        assert artifact_store.get(session.image_artifact) == PNG_SAMPLE

        # Provenance source_image_hash coincide con el sha256
        assert session.document["provenance"]["source_image_hash"] == session.image_artifact
    finally:
        if img_path.is_file():
            img_path.unlink()


def test_get_session_image_success_and_permissions() -> None:
    artifact_store = InMemoryArtifactStore()
    session_repo = InMemorySessionRepository()
    owner = User(
        id="user-1",
        username="transcriptor1",
        password_hash="h",
        role=Role.TRANSCRIPTOR,
        active=True,
    )
    other_transcriptor = User(
        id="user-2",
        username="transcriptor2",
        password_hash="h",
        role=Role.TRANSCRIPTOR,
        active=True,
    )
    investigator = User(
        id="inv-1",
        username="investigador1",
        password_hash="h",
        role=Role.INVESTIGADOR,
        active=True,
    )

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(PNG_SAMPLE)
        img_path = Path(f.name)

    try:
        result = transcribe_score(
            img_path,
            omr_engine=FakeOMREngine(),
            validator=ValidationEngine([]),
            session_repository=session_repo,
            current_user=owner,
            artifact_store=artifact_store,
        )

        # 1. El dueño puede recuperar su imagen
        img_data = get_session_image(
            result.session_id,
            session_repository=session_repo,
            artifact_store=artifact_store,
            current_user=owner,
        )
        assert img_data.content == PNG_SAMPLE
        assert img_data.media_type == "image/png"

        # 2. Investigador puede recuperar imagen de sesión ajena
        inv_data = get_session_image(
            result.session_id,
            session_repository=session_repo,
            artifact_store=artifact_store,
            current_user=investigator,
        )
        assert inv_data.content == PNG_SAMPLE

        # 3. Transcriptor ajeno recibe SessionNotFound (404, no filtra existencia)
        with pytest.raises(SessionNotFound):
            get_session_image(
                result.session_id,
                session_repository=session_repo,
                artifact_store=artifact_store,
                current_user=other_transcriptor,
            )

        # 4. Sesión inexistente
        with pytest.raises(SessionNotFound):
            get_session_image(
                "non-existent-session-id",
                session_repository=session_repo,
                artifact_store=artifact_store,
                current_user=owner,
            )
    finally:
        if img_path.is_file():
            img_path.unlink()
