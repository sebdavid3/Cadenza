"""Pruebas de la configuración tipada con pydantic-settings y factories (ADR-0005, #8, #44)."""

from __future__ import annotations

from pathlib import Path

import pytest
from cadenza.api import Settings, create_app, create_default_app
from cadenza.omr import HOMREngine
from cadenza.persistence import create_memory_engine, create_session_factory
from pydantic import ValidationError


def test_default_settings() -> None:
    settings = Settings()
    assert settings.database_url == "sqlite+pysqlite:///./cadenza.db"
    assert settings.omr_use_gpu is False
    assert settings.artifacts_dir == Path("./data/artifacts")
    assert settings.auth_secret_key == ""
    assert settings.auth_token_expire_minutes == 30
    assert settings.auto_create_schema is False


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CADENZA_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("CADENZA_OMR_USE_GPU", "true")
    monkeypatch.setenv("CADENZA_ARTIFACTS_DIR", "/custom/artifacts")
    monkeypatch.setenv("CADENZA_AUTH_SECRET_KEY", "super-secret-from-env")
    monkeypatch.setenv("CADENZA_AUTH_TOKEN_EXPIRE_MINUTES", "45")
    monkeypatch.setenv("CADENZA_AUTO_CREATE_SCHEMA", "true")

    settings = Settings()
    assert settings.database_url == "sqlite+pysqlite:///:memory:"
    assert settings.omr_use_gpu is True
    assert settings.artifacts_dir == Path("/custom/artifacts")
    assert settings.auth_secret_key == "super-secret-from-env"
    assert settings.auth_token_expire_minutes == 45
    assert settings.auto_create_schema is True


def test_create_app_fails_without_auth_secret_key() -> None:
    engine = create_memory_engine()
    with pytest.raises(RuntimeError, match="CADENZA_AUTH_SECRET_KEY no configurada"):
        create_app(create_session_factory(engine), settings=Settings(auth_secret_key=""))


def test_settings_have_no_engine_selector() -> None:
    """HOMR es el único motor (ADR-0018): no hay selector de motor en la configuración."""
    assert "omr_engine" not in Settings.model_fields


def test_obsolete_engine_variable_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CADENZA_OMR_ENGINE", "fake")
    app = create_default_app(
        Settings(database_url="sqlite+pysqlite:///:memory:", auth_secret_key="test-key-legacy")
    )
    assert isinstance(app.state.omr_engine, HOMREngine)


def test_create_default_app_uses_homr() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        omr_use_gpu=False,
        auth_secret_key="test-key-homr",
    )
    app = create_default_app(settings)
    assert isinstance(app.state.omr_engine, HOMREngine)
    assert app.state.settings.omr_use_gpu is False


def test_create_app_without_injected_engine_uses_homr() -> None:
    app = create_app(
        create_session_factory(create_memory_engine()),
        settings=Settings(auth_secret_key="test-key-homr"),
    )
    assert isinstance(app.state.omr_engine, HOMREngine)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("*", ["*"]),
        ("http://localhost:5174", ["http://localhost:5174"]),
        ("http://a.test, http://b.test", ["http://a.test", "http://b.test"]),
        ('["http://a.test", "http://b.test"]', ["http://a.test", "http://b.test"]),
        ("", []),
    ],
)
def test_cors_origins_from_env_accepts_documented_forms(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: list[str]
) -> None:
    """`*`, un origen, una lista separada por comas o JSON (`.env.example`, #123)."""
    monkeypatch.setenv("CADENZA_CORS_ORIGINS", raw)
    assert Settings().cors_origins == expected


def test_env_example_builds_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """La configuración de ejemplo del despliegue construye `Settings` sin errores (#123)."""
    env_example = Path(__file__).resolve().parents[3] / ".env.example"
    for line in env_example.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            monkeypatch.setenv(key.strip(), value.strip())
    settings = Settings()
    assert settings.cors_origins == ["*"]
    assert settings.login_rate_limit_max_attempts == 5


@pytest.mark.parametrize(
    "raw",
    [
        '"*"',
        '{"a": 1}',
        "http://a.test/",
        "localhost:5174",
        "*, http://a.test",
        '["*", "http://a.test"]',
    ],
)
def test_cors_origins_rejects_values_a_browser_never_sends(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """Un origen mal escrito falla al arrancar en lugar de desactivar CORS en silencio (#123)."""
    monkeypatch.setenv("CADENZA_CORS_ORIGINS", raw)
    with pytest.raises(ValidationError):
        Settings()


def test_registration_is_closed_by_default_and_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El registro público (ADR-0022) solo se abre si se pide expresamente."""
    for name in (
        "CADENZA_REGISTRATION_ENABLED",
        "CADENZA_REGISTRATION_RATE_LIMIT_MAX_ATTEMPTS",
        "CADENZA_REGISTRATION_RATE_LIMIT_WINDOW_SECONDS",
        "CADENZA_CORS_ORIGINS",
    ):
        monkeypatch.delenv(name, raising=False)
    defaults = Settings()
    assert defaults.registration_enabled is False
    assert defaults.registration_rate_limit_max_attempts == 5
    assert defaults.registration_rate_limit_window_seconds == 3600

    monkeypatch.setenv("CADENZA_CORS_ORIGINS", "https://cadenza.test")
    monkeypatch.setenv("CADENZA_REGISTRATION_ENABLED", "true")
    monkeypatch.setenv("CADENZA_REGISTRATION_RATE_LIMIT_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("CADENZA_REGISTRATION_RATE_LIMIT_WINDOW_SECONDS", "600")
    configured = Settings()
    assert configured.registration_enabled is True
    assert configured.registration_rate_limit_max_attempts == 3
    assert configured.registration_rate_limit_window_seconds == 600
    # El tope de cuentas pendientes desapareció con el registro abierto (ADR-0025).
    assert not hasattr(configured, "registration_max_pending")
