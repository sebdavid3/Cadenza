"""Pruebas de la migración Alembic 0019_public_stats (#423, ADR-0073)."""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from cadenza.persistence import create_memory_engine
from sqlalchemy import inspect


def _load_migration_0019() -> types.ModuleType:
    migration_path = Path(__file__).parents[1] / "migrations" / "versions" / "0019_public_stats.py"
    spec = importlib.util.spec_from_file_location("migration_0019", migration_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0019_metadata() -> None:
    mod = _load_migration_0019()
    assert mod.revision == "0019_public_stats"
    assert len(mod.revision) <= 32  # alembic_version.version_num es VARCHAR(32)
    assert mod.down_revision == "0018_users_drop_role"


def test_migration_0019_creates_the_table_and_goes_back() -> None:
    mod = _load_migration_0019()
    engine = create_memory_engine()

    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        mod.upgrade()

    columns = {c["name"]: c for c in inspect(engine).get_columns("public_stats")}
    assert set(columns) == {
        "id",
        "source",
        "computed_at",
        "format_version",
        "min_sessions",
        "sessions",
        "source_sha256",
        "stats",
    }
    assert columns["stats"]["nullable"]
    assert columns["source_sha256"]["nullable"]
    assert not columns["computed_at"]["nullable"]
    assert inspect(engine).get_pk_constraint("public_stats")["constrained_columns"] == ["id"]

    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        mod.downgrade()

    assert "public_stats" not in inspect(engine).get_table_names()
