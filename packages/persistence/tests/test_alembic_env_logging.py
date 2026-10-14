"""El entorno de Alembic no desactiva los registradores existentes (#119).

`migrations/env.py` configura el registro desde `alembic.ini` con `fileConfig`. Con el valor
por defecto (`disable_existing_loggers=True`) desactivaba los registradores ya creados en el
proceso, como `cadenza.api`, y la API dejaba de emitir sus registros; en los tests, los de
arranque de `apps/api` fallaban si corrían después de una migración.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


@pytest.fixture
def preserved_logging() -> Iterator[None]:
    """Restaura los manejadores y el nivel del registrador raíz que `fileConfig` reescribe."""

    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    try:
        yield
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)
        logging.getLogger("cadenza.api").disabled = False


@pytest.mark.usefixtures("preserved_logging")
def test_running_migrations_keeps_existing_loggers_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CADENZA_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    api_logger = logging.getLogger("cadenza.api")
    assert api_logger.disabled is False

    # Modo offline: genera el SQL de PostgreSQL sin conectarse a ningún servidor.
    config = Config(str(ALEMBIC_INI), stdout=io.StringIO())
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg2://cadenza@localhost/cadenza")
    command.upgrade(config, "head", sql=True)

    assert api_logger.disabled is False
