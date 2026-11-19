"""Pruebas de la migración Alembic 0020_public_stats_scores (#424, ADR-0073)."""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from cadenza.persistence import create_memory_engine
from sqlalchemy import inspect


def _load_migration_0020() -> types.ModuleType:
    migration_path = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0020_public_stats_scores.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0020", migration_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0020_metadata() -> None:
    mod = _load_migration_0020()
    assert mod.revision == "0020_public_stats_scores"
    assert len(mod.revision) <= 32  # alembic_version.version_num es VARCHAR(32)
    assert mod.down_revision == "0019_public_stats"


def test_migration_0020_creates_the_table_and_goes_back() -> None:
    mod = _load_migration_0020()
    engine = create_memory_engine()

    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        mod.upgrade()

    columns = {c["name"]: c for c in inspect(engine).get_columns("public_stats_scores")}
    assert set(columns) == {
        "group_id",
        "score_id",
        "computed_at",
        "format_version",
        "detail",
        "image_type",
        "image",
    }
    nullable = {name for name, column in columns.items() if column["nullable"]}
    assert nullable == {"image_type", "image"}
    pk = inspect(engine).get_pk_constraint("public_stats_scores")["constrained_columns"]
    assert pk == ["group_id", "score_id"]
    assert inspect(engine).get_foreign_keys("public_stats_scores") == []

    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        mod.downgrade()

    assert "public_stats_scores" not in inspect(engine).get_table_names()
