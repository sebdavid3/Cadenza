"""Título, compositor, instrumentos y nombre del archivo de una sesión en la base (#235).

ADR-0041 §1: columnas de `sessions`, todas opcionales; una sesión anterior (NULL) se lee sin
metadatos. Migración 0014 con `upgrade()` y `downgrade()`.
"""

from __future__ import annotations

import importlib.util
import io
import types
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cadenza.application import SessionData, SessionNotFound
from cadenza.domain import Instrument, PartMetadata, ScoreMetadata
from cadenza.persistence import (
    SqlAlchemySessionRepository,
    UserRecord,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from sqlalchemy import Column, MetaData, String, Table, inspect, select, text
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

MIGRATIONS = Path(__file__).parents[1] / "migrations" / "versions"
METADATA = ScoreMetadata(
    title="Mondnacht",
    composer="Robert Schumann",
    parts=(
        PartMetadata(Instrument.VOICE, name="Soprano"),
        PartMetadata(),
        PartMetadata(Instrument.OTHER, name="Theremin"),
    ),
)


@pytest.fixture
def factory() -> sessionmaker[DbSession]:
    engine = create_memory_engine()
    create_schema(engine)
    return create_session_factory(engine)


def _repo(
    db: DbSession,
    metadata: ScoreMetadata | None = None,
    source_filename: str | None = None,
) -> SqlAlchemySessionRepository:
    db.add(UserRecord(id="u1", username="ana", password_hash="h", role="transcriptor"))
    db.flush()
    repo = SqlAlchemySessionRepository(db)
    repo.add(
        SessionData(
            id="s1",
            document_id="d",
            omr_engine="fake",
            document={"id": "d"},
            owner_id="u1",
            metadata=metadata or ScoreMetadata(),
            source_filename=source_filename,
        ),
        [],
    )
    return repo


def test_metadata_and_source_filename_round_trip(factory: sessionmaker[DbSession]) -> None:
    with factory() as db:
        repo = _repo(db, metadata=METADATA, source_filename="mondnacht.png")
        db.commit()
    with factory() as db:
        repo = SqlAlchemySessionRepository(db)
        stored = repo.get("s1")
        assert stored is not None
        assert stored.metadata == METADATA
        assert stored.source_filename == "mondnacht.png"
        (summary,) = repo.list_summaries()
        assert summary.metadata == METADATA
        assert summary.source_filename == "mondnacht.png"
        (listed,) = repo.list()
        assert listed.metadata == METADATA


def test_session_without_metadata_reads_as_empty(factory: sessionmaker[DbSession]) -> None:
    with factory() as db:
        repo = _repo(db)
        stored = repo.get("s1")
        assert stored is not None
        assert stored.metadata == ScoreMetadata()
        assert stored.source_filename is None
        row = db.execute(
            text("SELECT title, composer, part_instruments, source_filename FROM sessions")
        ).one()
        # Una sesión sin datos nuevos guarda NULL, como las anteriores a la migración.
        assert tuple(row) == (None, None, None, None)


def test_update_metadata_replaces_only_the_metadata(factory: sessionmaker[DbSession]) -> None:
    with factory() as db:
        repo = _repo(db, source_filename="mondnacht.png")
        repo.update_status("s1", "finalized")

        updated = repo.update_metadata("s1", METADATA)

        assert updated.metadata == METADATA
        assert updated.status == "finalized"
        assert updated.source_filename == "mondnacht.png"
        stored = repo.get("s1")
        assert stored is not None and stored.metadata == METADATA

        cleared = repo.update_metadata("s1", ScoreMetadata())
        assert cleared.metadata == ScoreMetadata()
        row = db.execute(text("SELECT title, composer, part_instruments FROM sessions")).one()
        assert tuple(row) == (None, None, None)


def test_unknown_instrument_is_read_as_other(factory: sessionmaker[DbSession]) -> None:
    # Una versión posterior pudo guardar un instrumento que esta no conoce: el listado sigue.
    with factory() as db:
        _repo(db, metadata=METADATA)
        db.execute(
            text("UPDATE sessions SET part_instruments = :value"),
            {"value": '[{"instrument": "kazoo", "name": null}, {"instrument": "piano"}]'},
        )
        db.expire_all()
        repo = SqlAlchemySessionRepository(db)
        stored = repo.get("s1")
        assert stored is not None
        assert stored.metadata.parts == (
            PartMetadata(Instrument.OTHER, name="kazoo"),
            PartMetadata(Instrument.PIANO),
        )
        (summary,) = repo.list_summaries()
        assert summary.metadata.parts == stored.metadata.parts


def test_update_metadata_of_missing_session(factory: sessionmaker[DbSession]) -> None:
    with factory() as db, pytest.raises(SessionNotFound):
        SqlAlchemySessionRepository(db).update_metadata("nope", METADATA)


def _load_migration() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "migration_0014", MIGRATIONS / "0014_session_metadata.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_0014_metadata() -> None:
    module = _load_migration()
    assert module.revision == "0014_session_metadata"
    assert len(module.revision) <= 32
    assert module.down_revision == "0013_suggestions"


def test_migration_0014_upgrade_and_downgrade_on_sqlite() -> None:
    module = _load_migration()
    engine = create_memory_engine()
    meta = MetaData()
    sessions = Table("sessions", meta, Column("id", String(36), primary_key=True))
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(sessions.insert().values(id="antigua"))

    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        module.upgrade()

    columns = {c["name"]: c for c in inspect(engine).get_columns("sessions")}
    for name in ("title", "composer", "part_instruments", "source_filename"):
        assert columns[name]["nullable"] is True
    reloaded = Table("sessions", MetaData(), autoload_with=engine)
    with engine.connect() as conn:
        row = conn.execute(
            select(
                reloaded.c.title,
                reloaded.c.composer,
                reloaded.c.part_instruments,
                reloaded.c.source_filename,
            )
        ).one()
    # La sesión anterior se lee igual: sin metadatos.
    assert tuple(row) == (None, None, None, None)

    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        module.downgrade()

    remaining = {c["name"] for c in inspect(engine).get_columns("sessions")}
    assert remaining == {"id"}


def test_migration_0014_generates_postgresql_sql() -> None:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg2://c:c@localhost:5432/c")
    buffer = io.StringIO()
    config.stdout = buffer
    command.upgrade(config, "0013_suggestions:0014_session_metadata", sql=True)
    sql = buffer.getvalue()
    assert "ALTER TABLE sessions ADD COLUMN title VARCHAR(200)" in sql
    assert "ALTER TABLE sessions ADD COLUMN composer VARCHAR(200)" in sql
    assert "ALTER TABLE sessions ADD COLUMN part_instruments JSONB" in sql
    assert "ALTER TABLE sessions ADD COLUMN source_filename VARCHAR(255)" in sql

    buffer.truncate(0)
    buffer.seek(0)
    command.downgrade(config, "0014_session_metadata:0013_suggestions", sql=True)
    downgrade_sql = buffer.getvalue()
    for name in ("title", "composer", "part_instruments", "source_filename"):
        assert f"ALTER TABLE sessions DROP COLUMN {name}" in downgrade_sql
