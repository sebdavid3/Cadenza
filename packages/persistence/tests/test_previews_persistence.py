"""Transcripciones sin cuenta en la base (#278, ADR-0054): tabla `previews`, migración 0016."""

from __future__ import annotations

import importlib.util
import io
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cadenza.application import PreviewData
from cadenza.domain import Instrument, PartMetadata, ScoreMetadata
from cadenza.persistence import (
    SqlAlchemyPreviewRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from sqlalchemy import inspect
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

MIGRATIONS = Path(__file__).parents[1] / "migrations" / "versions"
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


@pytest.fixture
def factory() -> sessionmaker[DbSession]:
    engine = create_memory_engine()
    create_schema(engine)
    return create_session_factory(engine)


def _preview(preview_id: str, expires_at: datetime) -> PreviewData:
    return PreviewData(
        id=preview_id,
        token_hash="a" * 64,
        document={"id": "d", "score": {"parts": []}},
        image=b"\x89PNG\r\n\x1a\nimagen",
        image_media_type="image/png",
        created_at=NOW,
        expires_at=expires_at,
        metadata=ScoreMetadata(title="Minueto", parts=(PartMetadata(Instrument.VIOLIN),)),
        source_filename="minueto.png",
    )


def test_round_trip_with_the_image_and_the_metadata(factory: sessionmaker[DbSession]) -> None:
    with factory() as db:
        SqlAlchemyPreviewRepository(db).add(_preview("p1", NOW + timedelta(hours=1)))
        db.commit()

    with factory() as db:
        stored = SqlAlchemyPreviewRepository(db).get("p1")

    assert stored == _preview("p1", NOW + timedelta(hours=1))
    assert stored is not None and stored.expires_at.tzinfo is not None


def test_delete_succeeds_once(factory: sessionmaker[DbSession]) -> None:
    with factory() as db:
        repo = SqlAlchemyPreviewRepository(db)
        repo.add(_preview("p1", NOW + timedelta(hours=1)))
        assert repo.delete("p1") is True
        assert repo.delete("p1") is False
        assert repo.get("p1") is None


def test_purge_and_count_use_the_expiry(factory: sessionmaker[DbSession]) -> None:
    with factory() as db:
        repo = SqlAlchemyPreviewRepository(db)
        repo.add(_preview("vieja", NOW - timedelta(seconds=1)))
        repo.add(_preview("nueva", NOW + timedelta(hours=1)))
        assert repo.count_active(NOW) == 1
        assert repo.purge_expired(NOW) == 1
        db.commit()

    with factory() as db:
        repo = SqlAlchemyPreviewRepository(db)
        assert repo.get("vieja") is None
        assert repo.get("nueva") is not None


def _load_migration() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0016", MIGRATIONS / "0016_previews.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_0016_metadata() -> None:
    module = _load_migration()
    assert module.revision == "0016_previews"
    assert len(module.revision) <= 32
    assert module.down_revision == "0015_effort_accumulated"


def test_migration_0016_upgrade_and_downgrade_on_sqlite() -> None:
    module = _load_migration()
    engine = create_memory_engine()

    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        module.upgrade()

    inspector = inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("previews")}
    assert set(columns) == {
        "id",
        "token_hash",
        "document",
        "image",
        "image_media_type",
        "title",
        "composer",
        "part_instruments",
        "source_filename",
        "created_at",
        "expires_at",
    }
    assert columns["image"]["nullable"] is False
    assert columns["title"]["nullable"] is True
    assert {ix["name"] for ix in inspector.get_indexes("previews")} == {"ix_previews_expires_at"}

    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        module.downgrade()

    assert "previews" not in inspect(engine).get_table_names()


def test_migration_0016_generates_postgresql_sql() -> None:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg2://c:c@localhost:5432/c")
    buffer = io.StringIO()
    config.stdout = buffer
    command.upgrade(config, "0015_effort_accumulated:0016_previews", sql=True)
    sql = buffer.getvalue()
    assert "CREATE TABLE previews" in sql
    assert "image BYTEA NOT NULL" in sql
    assert "document JSONB NOT NULL" in sql
    assert "CREATE INDEX ix_previews_expires_at" in sql

    buffer.truncate(0)
    buffer.seek(0)
    command.downgrade(config, "0016_previews:0015_effort_accumulated", sql=True)
    assert "DROP TABLE previews" in buffer.getvalue()
