"""Pruebas de la migración Alembic 0017_users_data_consent (#378, ADR-0064)."""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from cadenza.persistence import create_memory_engine
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    false,
    func,
    inspect,
    select,
)


def _load_migration_0017() -> types.ModuleType:
    migration_path = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0017_users_data_consent.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0017", migration_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0017_metadata() -> None:
    mod = _load_migration_0017()
    assert mod.revision == "0017_users_data_consent"
    assert len(mod.revision) <= 32  # alembic_version.version_num es VARCHAR(32)
    assert mod.down_revision == "0016_previews"


def test_migration_0017_leaves_existing_accounts_without_permission_and_goes_back() -> None:
    mod = _load_migration_0017()
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
        Column("self_registered", Boolean(), nullable=False, server_default=false()),
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
    assert {"data_consent_at", "data_consent_version"} <= columns
    reloaded = Table("users", MetaData(), autoload_with=engine)
    with engine.connect() as conn:
        row = conn.execute(
            select(reloaded.c.data_consent_at, reloaded.c.data_consent_version)
        ).one()
    assert tuple(row) == (None, None)

    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        mod.downgrade()

    columns = {c["name"] for c in inspect(engine).get_columns("users")}
    assert "data_consent_at" not in columns and "data_consent_version" not in columns
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(users)).scalar_one() == 1
