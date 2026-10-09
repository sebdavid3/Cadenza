"""Tests de integración para el endpoint GET /sessions/{id}/timing (#42, D12)."""

from io import BytesIO
from pathlib import Path

import pytest
from cadenza.api import Settings, create_app
from cadenza.application import Role, User
from cadenza.omr import FakeOMREngine
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi.testclient import TestClient

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
)


@pytest.fixture
def api_setup(tmp_path: Path) -> tuple[TestClient, dict[str, str]]:
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as db:
        user_repo = SqlAlchemyUserRepository(db)
        user_repo.add(
            User(
                id="usr-inv",
                username="investigador",
                password_hash="hash_inv",
                role=Role.INVESTIGADOR,
                active=True,
            )
        )
        db.commit()

    settings = Settings(
        auth_secret_key="secret-key-at-least-32-bytes-long-for-testing",
        artifacts_dir=tmp_path / "artifacts",
    )
    app = create_app(
        session_factory,
        omr_engine=FakeOMREngine(),
        settings=settings,
    )

    client = TestClient(app)
    token = app.state.token_service.create_access_token(
        user_id="usr-inv",
        role=Role.INVESTIGADOR,
    )
    return client, {"Authorization": f"Bearer {token}"}


def test_get_session_timing_flow(api_setup: tuple[TestClient, dict[str, str]]) -> None:
    client, headers = api_setup

    # 1. Transcribir una imagen
    trans_resp = client.post(
        "/transcribe",
        files={"file": ("sample.png", BytesIO(PNG_BYTES), "image/png")},
        headers=headers,
    )
    assert trans_resp.status_code == 201, trans_resp.text
    session_id = trans_resp.json()["session_id"]

    # 2. Consultar el mapa de tiempos
    timing_resp = client.get(f"/sessions/{session_id}/timing", headers=headers)
    assert timing_resp.status_code == 200, timing_resp.text

    data = timing_resp.json()
    assert data["session_id"] == session_id
    assert "total_beats" in data
    assert "measure_offsets" in data
    assert isinstance(data["events"], list)
    assert len(data["events"]) > 0

    first_event = data["events"][0]
    assert "anchor" in first_event
    assert "kind" in first_event
    assert "measure_number" in first_event
    assert "voice" in first_event
    assert "offset_beats" in first_event
    assert "duration_beats" in first_event
    assert "measure_offset_beats" in first_event


def test_get_session_timing_not_found(api_setup: tuple[TestClient, dict[str, str]]) -> None:
    client, headers = api_setup
    resp = client.get("/sessions/nonexistent-session-id/timing", headers=headers)
    assert resp.status_code == 404


def test_get_session_timing_forbidden_for_other_transcriptor(tmp_path: Path) -> None:
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as db:
        user_repo = SqlAlchemyUserRepository(db)
        user_repo.add(
            User(
                id="usr-tra-a",
                username="transcriptor_a",
                password_hash="hash_a",
                role=Role.TRANSCRIPTOR,
                active=True,
            )
        )
        user_repo.add(
            User(
                id="usr-tra-b",
                username="transcriptor_b",
                password_hash="hash_b",
                role=Role.TRANSCRIPTOR,
                active=True,
            )
        )
        db.commit()

    settings = Settings(
        auth_secret_key="secret-key-at-least-32-bytes-long-for-testing",
        artifacts_dir=tmp_path / "artifacts",
    )
    app = create_app(
        session_factory,
        omr_engine=FakeOMREngine(),
        settings=settings,
    )
    client = TestClient(app)

    token_a = app.state.token_service.create_access_token(
        user_id="usr-tra-a", role=Role.TRANSCRIPTOR
    )
    token_b = app.state.token_service.create_access_token(
        user_id="usr-tra-b", role=Role.TRANSCRIPTOR
    )
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Transcriptor A crea sesión
    trans_resp = client.post(
        "/transcribe",
        files={"file": ("sample.png", BytesIO(PNG_BYTES), "image/png")},
        headers=headers_a,
    )
    assert trans_resp.status_code == 201
    session_id = trans_resp.json()["session_id"]

    # Transcriptor A puede acceder a su propio timing
    resp_a = client.get(f"/sessions/{session_id}/timing", headers=headers_a)
    assert resp_a.status_code == 200

    # Transcriptor B no puede acceder a la sesión ajena (404 bajo ADR-0012)
    resp_b = client.get(f"/sessions/{session_id}/timing", headers=headers_b)
    assert resp_b.status_code == 404
