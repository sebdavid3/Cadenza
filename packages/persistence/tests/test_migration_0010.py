"""Pruebas de la migración Alembic 0010_model_versions (#21)."""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from cadenza.persistence import create_memory_engine
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    func,
    inspect,
    select,
)


def _load_migration_0010() -> types.ModuleType:
    migration_path = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0010_model_versions.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0010", migration_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0010_metadata() -> None:
    mod = _load_migration_0010()
    assert mod.revision == "0010_model_versions"
    assert mod.down_revision == "0009_findings_dismissal"


def test_migration_0010_upgrade_and_downgrade() -> None:
    mod = _load_migration_0010()
    engine = create_memory_engine()

    meta = MetaData()
    artifacts = Table(
        "artifacts",
        meta,
        Column("sha256", String(64), primary_key=True),
        Column("kind", String(32), nullable=False),
        Column("media_type", String(128), nullable=False),
        Column("size_bytes", Integer(), nullable=False),
        Column("path", String(512), nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    meta.create_all(engine)

    # Inserción de fixture de artefacto previo (pesos ONNX)
    with engine.begin() as conn:
        conn.execute(
            artifacts.insert().values(
                sha256="model_onnx_hash_abc",
                kind="model",
                media_type="application/octet-stream",
                size_bytes=1048576,
                path="sha256/mo/de/model_onnx_hash_abc",
            )
        )

    # Ejecutar upgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()

    inspector = inspect(engine)
    assert "model_versions" in inspector.get_table_names()
    columns = {c["name"]: c for c in inspector.get_columns("model_versions")}
    assert "version" in columns
    assert "artifact_hash" in columns
    assert "dataset_hash" in columns
    assert "config_hash" in columns
    assert "ser" in columns
    assert "omr_ned" in columns
    assert "promoted" in columns
    assert "created_at" in columns

    # Inserción y consulta en model_versions
    meta_up = MetaData()
    meta_up.reflect(bind=engine)
    mv_table = meta_up.tables["model_versions"]

    with engine.begin() as conn:
        conn.execute(
            mv_table.insert().values(
                version="v1.0.0",
                artifact_hash="model_onnx_hash_abc",
                dataset_hash="dataset_hash_123",
                config_hash="config_hash_456",
                ser=0.045,
                omr_ned=0.082,
                promoted=True,
            )
        )
        row = conn.execute(select(mv_table).where(mv_table.c.version == "v1.0.0")).mappings().one()
        assert row["version"] == "v1.0.0"
        assert row["artifact_hash"] == "model_onnx_hash_abc"
        assert row["ser"] == 0.045
        assert row["omr_ned"] == 0.082
        assert row["promoted"] in (True, 1)

    # Ejecutar downgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.downgrade()

    inspector_down = inspect(engine)
    assert "model_versions" not in inspector_down.get_table_names()
