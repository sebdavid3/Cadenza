"""Tests de integración para operaciones del backend (#40, D44)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cadenza.api import Settings, create_app
from cadenza.application import Role, User
from cadenza.omr import FakeOMREngine
from cadenza.persistence import (
    FilesystemArtifactStore,
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi.testclient import TestClient


@pytest.fixture
def ops_test_client(tmp_path: Path) -> TestClient:
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    with session_factory() as db:
        user_repo = SqlAlchemyUserRepository(db)
        # Contraseña 'secret123'
        user_repo.add(
            User(
                id="usr-ops-1",
                username="operator_test",
                password_hash="$argon2id$v=19$m=65536,t=3,p=4$anBkd3hhc2Rhc2Q$1oXv1n01gZzZ51g5bZk5Y5",
                role=Role.INVESTIGADOR,
                active=True,
            )
        )
        db.commit()

    settings = Settings(
        auth_secret_key="secret-key-at-least-32-bytes-long-for-testing",
        artifacts_dir=artifacts_dir,
        cors_origins=["http://localhost:5173", "https://cadenza.app"],
        login_rate_limit_max_attempts=3,
        login_rate_limit_window_seconds=60,
    )
    artifact_store = FilesystemArtifactStore(artifacts_dir)
    app = create_app(
        session_factory,
        omr_engine=FakeOMREngine(),
        artifact_store=artifact_store,
        settings=settings,
    )
    return TestClient(app)


def test_health_check_healthy(ops_test_client: TestClient) -> None:
    resp = ops_test_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["artifact_store"] == "accessible"
    assert data["omr_engine"] == "fake"
    assert "device" in data
    assert data["version"] == "1.0.0"


def test_health_check_unhealthy_when_database_fails(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Mock session factory que falla al ejecutar query
    failing_session = MagicMock()
    failing_session.execute.side_effect = RuntimeError("Database down")
    failing_factory = MagicMock(return_value=failing_session)

    settings = Settings(
        auth_secret_key="secret-key-at-least-32-bytes-long-for-testing",
        artifacts_dir=artifacts_dir,
    )
    app = create_app(
        failing_factory,
        omr_engine=FakeOMREngine(),
        settings=settings,
    )
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "unhealthy"
    assert data["database"] == "error"


def test_request_id_middleware(ops_test_client: TestClient) -> None:
    # 1. Petición sin X-Request-ID: debe generarlo
    resp1 = ops_test_client.get("/version")
    assert resp1.status_code == 200
    req_id1 = resp1.headers.get("X-Request-ID")
    assert req_id1 is not None and len(req_id1) > 0

    # 2. Petición con X-Request-ID provisto: debe preservarlo
    custom_id = "req-custom-trace-12345"
    resp2 = ops_test_client.get("/version", headers={"X-Request-ID": custom_id})
    assert resp2.status_code == 200
    assert resp2.headers.get("X-Request-ID") == custom_id


def test_cors_middleware_headers(ops_test_client: TestClient) -> None:
    # Petición con origen permitido
    resp = ops_test_client.get("/version", headers={"Origin": "https://cadenza.app"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "https://cadenza.app"

    # Preflight OPTIONS
    opt_resp = ops_test_client.options(
        "/version",
        headers={
            "Origin": "https://cadenza.app",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert opt_resp.status_code == 200
    assert opt_resp.headers.get("access-control-allow-origin") == "https://cadenza.app"


def test_login_rate_limiting(ops_test_client: TestClient) -> None:
    # 3 intentos fallidos permitidos antes de bloqueo
    for _ in range(3):
        fail_resp = ops_test_client.post(
            "/auth/login",
            data={"username": "operator_test", "password": "wrong_password"},
        )
        assert fail_resp.status_code == 401

    # El 4º intento debe retornar 429 Too Many Requests
    blocked_resp = ops_test_client.post(
        "/auth/login",
        data={"username": "operator_test", "password": "wrong_password"},
    )
    assert blocked_resp.status_code == 429
    assert "Retry-After" in blocked_resp.headers
    assert "Demasiados intentos fallidos" in blocked_resp.json()["detail"]
