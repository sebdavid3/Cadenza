"""Pruebas de la configuración tipada con pydantic-settings y factories (ADR-0005, #8)."""

from __future__ import annotations

from pathlib import Path

from cadenza.api import Settings, create_default_app
from cadenza.omr import FakeOMREngine, HOMREngine


def test_default_settings() -> None:
    settings = Settings()
    assert settings.database_url == "sqlite+pysqlite:///./cadenza.db"
    assert settings.omr_engine == "fake"
    assert settings.omr_use_gpu is False
    assert settings.artifacts_dir == Path("./data/artifacts")


def test_settings_from_env(monkeypatch: object) -> None:
    import pytest

    mp = pytest.MonkeyPatch()
    mp.setenv("CADENZA_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    mp.setenv("CADENZA_OMR_ENGINE", "homr")
    mp.setenv("CADENZA_OMR_USE_GPU", "true")
    mp.setenv("CADENZA_ARTIFACTS_DIR", "/custom/artifacts")

    settings = Settings()
    assert settings.database_url == "sqlite+pysqlite:///:memory:"
    assert settings.omr_engine == "homr"
    assert settings.omr_use_gpu is True
    assert settings.artifacts_dir == Path("/custom/artifacts")
    mp.undo()


def test_create_default_app_with_fake_engine() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        omr_engine="fake",
    )
    app = create_default_app(settings)
    assert isinstance(app.state.omr_engine, FakeOMREngine)
    assert app.state.settings.omr_engine == "fake"


def test_create_default_app_with_homr_engine() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        omr_engine="homr",
        omr_use_gpu=False,
    )
    app = create_default_app(settings)
    assert isinstance(app.state.omr_engine, HOMREngine)
    assert app.state.settings.omr_engine == "homr"
    assert app.state.settings.omr_use_gpu is False
