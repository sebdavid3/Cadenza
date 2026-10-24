"""Tests de integración para operaciones del backend (#40, D44)."""

import os
import secrets
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cadenza.api import Settings, create_app
from cadenza.application import Role, User
from cadenza.omr.testing import FakeOMREngine
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


@pytest.mark.parametrize("injected_store", [True, False])
def test_health_is_unhealthy_when_the_api_cannot_write_its_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, injected_store: bool
) -> None:
    # La API corre sin root (D57, #192): un volumen de artefactos de antes, de root, existe pero
    # no admite escritura, y la API arrancaría sana para fallar en la primera transcripción. En
    # producción el almacén no se inyecta: cada petición crea uno sobre `artifacts_dir`, y antes
    # de #192 /health no comprobaba esa carpeta.
    engine = create_memory_engine()
    create_schema(engine)
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    client = TestClient(
        create_app(
            create_session_factory(engine),
            omr_engine=FakeOMREngine(),
            artifact_store=FilesystemArtifactStore(artifacts_dir) if injected_store else None,
            settings=Settings(auth_secret_key=secrets.token_hex(32), artifacts_dir=artifacts_dir),
        )
    )
    assert client.get("/health").status_code == 200
    real_access = os.access

    def access(path: str | os.PathLike[str], mode: int) -> bool:
        if Path(path).resolve() == artifacts_dir.resolve() and mode & os.W_OK:
            return False
        return real_access(path, mode)

    monkeypatch.setattr(os, "access", access)

    resp = client.get("/health")

    assert resp.status_code == 503
    assert resp.json()["status"] == "unhealthy"
    assert resp.json()["artifact_store"] == "error"


def test_health_reports_homr_with_default_engine(tmp_path: Path) -> None:
    """Sin motor inyectado la API usa HOMR, el único motor de producción (ADR-0018)."""
    engine = create_memory_engine()
    create_schema(engine)
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        auth_secret_key="secret-key-at-least-32-bytes-long-for-testing",
        artifacts_dir=artifacts_dir,
    )
    app = create_app(
        create_session_factory(engine),
        artifact_store=FilesystemArtifactStore(artifacts_dir),
        settings=settings,
    )
    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    assert resp.json()["omr_engine"] == "homr"


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
    assert opt_resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_wildcard_does_not_allow_credentials(tmp_path: Path) -> None:
    """Con `*`, CORS no reenvía el origen ajeno junto con `Allow-Credentials` (#123)."""
    engine = create_memory_engine()
    create_schema(engine)
    settings = Settings(
        auth_secret_key="secret-key-at-least-32-bytes-long-for-testing",
        artifacts_dir=tmp_path / "artifacts",
        cors_origins=["*"],
    )
    client = TestClient(
        create_app(create_session_factory(engine), omr_engine=FakeOMREngine(), settings=settings)
    )
    resp = client.options(
        "/version",
        headers={"Origin": "http://evil.test", "Access-Control-Request-Method": "GET"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "*"
    assert "access-control-allow-credentials" not in resp.headers


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


def test_startup_disables_power_throttling_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Verifica que create_app llama a disable_power_throttling si está configurado."""
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)

    mock_disable = MagicMock(return_value=True)
    monkeypatch.setattr("cadenza.api.main.disable_power_throttling", mock_disable)

    settings = Settings(
        auth_secret_key="secret-key-at-least-32-bytes-long-for-testing",
        artifacts_dir=tmp_path / "artifacts",
        disable_power_throttling=True,
    )
    with caplog.at_level("INFO", logger="cadenza.api"):
        create_app(session_factory, omr_engine=FakeOMREngine(), settings=settings)

    assert mock_disable.called
    assert "power_throttling_disabled requested=True applied=True" in caplog.text


def test_startup_skips_power_throttling_when_disabled_by_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Verifica que create_app no llama a disable_power_throttling si se desactiva."""
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)

    mock_disable = MagicMock(return_value=True)
    monkeypatch.setattr("cadenza.api.main.disable_power_throttling", mock_disable)

    settings = Settings(
        auth_secret_key="secret-key-at-least-32-bytes-long-for-testing",
        artifacts_dir=tmp_path / "artifacts",
        disable_power_throttling=False,
    )
    with caplog.at_level("INFO", logger="cadenza.api"):
        create_app(session_factory, omr_engine=FakeOMREngine(), settings=settings)

    assert not mock_disable.called
    assert "power_throttling_disabled requested=False applied=False" in caplog.text


def test_cadenza_logging_configured_when_no_handlers_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifica que create_app configura un manejador para cadenza.* si no hay ninguno."""
    import logging

    cadenza_logger = logging.getLogger("cadenza")
    root_logger = logging.getLogger()
    old_cadenza_handlers = list(cadenza_logger.handlers)
    old_cadenza_level = cadenza_logger.level
    old_root_handlers = list(root_logger.handlers)
    old_root_level = root_logger.level

    cadenza_logger.handlers.clear()
    cadenza_logger.setLevel(logging.NOTSET)
    root_logger.handlers.clear()
    root_logger.setLevel(logging.WARNING)

    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)
    settings = Settings(
        auth_secret_key="secret-key-at-least-32-bytes-long-for-testing",
        artifacts_dir=tmp_path / "artifacts",
    )

    try:
        assert not cadenza_logger.hasHandlers()
        create_app(session_factory, omr_engine=FakeOMREngine(), settings=settings)
        assert len(cadenza_logger.handlers) == 1
        assert cadenza_logger.level == logging.INFO

        # Idempotencia: una segunda llamada no debe duplicar handlers
        create_app(session_factory, omr_engine=FakeOMREngine(), settings=settings)
        assert len(cadenza_logger.handlers) == 1
    finally:
        cadenza_logger.handlers = old_cadenza_handlers
        cadenza_logger.setLevel(old_cadenza_level)
        root_logger.handlers = old_root_handlers
        root_logger.setLevel(old_root_level)


def test_cadenza_logging_preserves_existing_handlers(tmp_path: Path) -> None:
    """Verifica que create_app no pisa ni duplica si cadenza ya tiene handlers."""
    import logging

    cadenza_logger = logging.getLogger("cadenza")
    old_handlers = list(cadenza_logger.handlers)
    old_level = cadenza_logger.level
    custom_handler = logging.NullHandler()
    cadenza_logger.handlers = [custom_handler]
    cadenza_logger.setLevel(logging.DEBUG)

    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)
    settings = Settings(
        auth_secret_key="secret-key-at-least-32-bytes-long-for-testing",
        artifacts_dir=tmp_path / "artifacts",
    )

    try:
        create_app(session_factory, omr_engine=FakeOMREngine(), settings=settings)
        assert cadenza_logger.handlers == [custom_handler]
        assert cadenza_logger.level == logging.DEBUG
    finally:
        cadenza_logger.handlers = old_handlers
        cadenza_logger.setLevel(old_level)
