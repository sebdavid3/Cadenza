"""Pruebas de la migración Alembic 0012_users_self_registered (ADR-0022, #154)."""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from cadenza.persistence import create_memory_engine
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, func, inspect, select


def _load_migration_0012() -> types.ModuleType:
    migration_path = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0012_users_self_registered.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0012", migration_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0012_metadata() -> None:
    mod = _load_migration_0012()
    assert mod.revision == "0012_users_self_registered"
    assert len(mod.revision) <= 32  # alembic_version.version_num es VARCHAR(32)
    assert mod.down_revision == "0011_condition_and_test_score"


def test_migration_0012_upgrade_marks_existing_users_as_not_self_registered() -> None:
    mod = _load_migration_0012()
    engine = create_memory_engine()
    meta = MetaData()
    users = Table(
        "users",
        meta,
        Column("id", String(36), primary_key=True),
        Column("username", String(64), unique=True, nullable=False),
        Column("password_hash", String(255), nullable=False),
        Column("role", String(32), nullable=False),
        Column("active", Integer(), nullable=False, server_default="1"),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            users.insert().values(
                id="u1", username="participante_01", password_hash="hash", role="transcriptor"
            )
        )

    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        mod.upgrade()

    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    assert "self_registered" in columns
    reloaded = Table("users", MetaData(), autoload_with=engine)
    with engine.connect() as conn:
        assert conn.execute(select(reloaded.c.self_registered)).scalar_one() in (False, 0)

    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        mod.downgrade()

    assert "self_registered" not in {c["name"] for c in inspect(engine).get_columns("users")}
