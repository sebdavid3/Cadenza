"""Pruebas de la migración Alembic 0018_users_drop_role (#419, ADR-0070)."""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from cadenza.persistence import create_memory_engine
from sqlalchemy import Boolean, Column, MetaData, String, Table, inspect, select


def _load_migration_0018() -> types.ModuleType:
    migration_path = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0018_users_drop_role.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0018", migration_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0018_metadata() -> None:
    mod = _load_migration_0018()
    assert mod.revision == "0018_users_drop_role"
    assert len(mod.revision) <= 32  # alembic_version.version_num es VARCHAR(32)
    assert mod.down_revision == "0017_users_data_consent"


def test_migration_0018_drops_the_role_keeping_accounts_and_goes_back() -> None:
    mod = _load_migration_0018()
    engine = create_memory_engine()
    meta = MetaData()
    users = Table(
        "users",
        meta,
        Column("id", String(36), primary_key=True),
        Column("username", String(64), unique=True, nullable=False),
        Column("password_hash", String(255), nullable=False),
        Column("role", String(32), nullable=False),
        Column("active", Boolean(), nullable=False, server_default="1"),
    )
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            users.insert(),
            [
                {"id": "u1", "username": "ana", "password_hash": "h", "role": "transcriptor"},
                {"id": "u2", "username": "irene", "password_hash": "h", "role": "investigador"},
            ],
        )

    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        mod.upgrade()

    assert "role" not in {c["name"] for c in inspect(engine).get_columns("users")}
    reloaded = Table("users", MetaData(), autoload_with=engine)
    with engine.connect() as conn:
        names = conn.execute(select(reloaded.c.username).order_by(reloaded.c.id)).scalars().all()
    assert names == ["ana", "irene"]

    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        mod.downgrade()

    reloaded = Table("users", MetaData(), autoload_with=engine)
    with engine.connect() as conn:
        roles = conn.execute(select(reloaded.c.role)).scalars().all()
    assert roles == ["transcriptor", "transcriptor"]
