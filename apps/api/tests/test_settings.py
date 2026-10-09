"""Pruebas de la configuración tipada con pydantic-settings y factories (ADR-0005, #8, #44)."""

from __future__ import annotations

from pathlib import Path

import pytest
from cadenza.api import Settings, create_app, create_default_app
from cadenza.omr import FakeOMREngine, HOMREngine, OemerEngine
from cadenza.persistence import create_memory_engine, create_session_factory


def test_default_settings() -> None:
    settings = Settings()
    assert settings.database_url == "sqlite+pysqlite:///./cadenza.db"
    assert settings.omr_engine == "fake"
    assert settings.omr_use_gpu is False
    assert settings.artifacts_dir == Path("./data/artifacts")
    assert settings.auth_secret_key == ""
    assert settings.auth_token_expire_minutes == 30
    assert settings.auto_create_schema is False


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CADENZA_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("CADENZA_OMR_ENGINE", "homr")
    monkeypatch.setenv("CADENZA_OMR_USE_GPU", "true")
    monkeypatch.setenv("CADENZA_ARTIFACTS_DIR", "/custom/artifacts")
    monkeypatch.setenv("CADENZA_AUTH_SECRET_KEY", "super-secret-from-env")
    monkeypatch.setenv("CADENZA_AUTH_TOKEN_EXPIRE_MINUTES", "45")
    monkeypatch.setenv("CADENZA_AUTO_CREATE_SCHEMA", "true")

    settings = Settings()
    assert settings.database_url == "sqlite+pysqlite:///:memory:"
    assert settings.omr_engine == "homr"
    assert settings.omr_use_gpu is True
    assert settings.artifacts_dir == Path("/custom/artifacts")
    assert settings.auth_secret_key == "super-secret-from-env"
    assert settings.auth_token_expire_minutes == 45
    assert settings.auto_create_schema is True


def test_create_app_fails_without_auth_secret_key() -> None:
    engine = create_memory_engine()
    with pytest.raises(RuntimeError, match="CADENZA_AUTH_SECRET_KEY no configurada"):
        create_app(create_session_factory(engine), settings=Settings(auth_secret_key=""))


def test_create_default_app_with_fake_engine() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        omr_engine="fake",
        auth_secret_key="test-key-fake",
    )
    app = create_default_app(settings)
    assert isinstance(app.state.omr_engine, FakeOMREngine)
    assert app.state.settings.omr_engine == "fake"


def test_create_default_app_with_homr_engine() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        omr_engine="homr",
        omr_use_gpu=False,
        auth_secret_key="test-key-homr",
    )
    app = create_default_app(settings)
    assert isinstance(app.state.omr_engine, HOMREngine)
    assert app.state.settings.omr_engine == "homr"
    assert app.state.settings.omr_use_gpu is False


def test_create_default_app_with_oemer_engine() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        omr_engine="oemer",
        omr_use_gpu=False,
        auth_secret_key="test-key-oemer",
    )
    app = create_default_app(settings)
    assert isinstance(app.state.omr_engine, OemerEngine)
    assert app.state.settings.omr_engine == "oemer"
