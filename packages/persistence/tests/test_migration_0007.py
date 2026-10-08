"""Pruebas de la migración Alembic 0007_effort_metrics_table (ADR-0004, #13)."""

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
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    func,
    inspect,
    select,
)
from sqlalchemy.types import JSON


def _load_migration_0007() -> types.ModuleType:
    migration_path = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0007_effort_metrics_table.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0007", migration_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0007_metadata() -> None:
    mod = _load_migration_0007()
    assert mod.revision == "0007_effort_metrics_table"
    assert mod.down_revision == "0006_session_validated_at_seq"


def test_migration_0007_upgrade_and_downgrade() -> None:
    mod = _load_migration_0007()
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
    sessions = Table(
        "sessions",
        meta,
        Column("id", String(36), primary_key=True),
        Column("owner_id", String(36), ForeignKey("users.id"), nullable=False),
        Column("document_id", String(255), nullable=False),
        Column("omr_engine", String(64), nullable=False),
        Column("model_version", String(64), nullable=True),
        Column("status", String(32), nullable=False, server_default="transcribed"),
        Column("validated_at_seq", Integer(), nullable=False, server_default="0"),
        Column("image_artifact", String(64), nullable=True),
        Column("document", JSON, nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    meta.create_all(engine)

    # Inserción de fixture previa
    with engine.begin() as conn:
        conn.execute(
            users.insert().values(
                id="u1",
                username="transcriptor1",
                password_hash="hash",
                role="transcriptor",
                active=1,
            )
        )
        conn.execute(
            sessions.insert().values(
                id="s1",
                owner_id="u1",
                document_id="doc-1",
                omr_engine="fake",
                document={"score": {}},
            )
        )

    # Ejecutar upgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()

    inspector = inspect(engine)
    assert "effort_metrics" in inspector.get_table_names()
    columns = {c["name"]: c for c in inspector.get_columns("effort_metrics")}
    assert "id" in columns
    assert "session_id" in columns
    assert "duration_ms" in columns
    assert "time_to_first_edit_ms" in columns
    assert "interventions" in columns
    assert "created_at" in columns

    # Insertar y consultar fila
    meta_up = MetaData()
    meta_up.reflect(bind=engine)
    effort_table = meta_up.tables["effort_metrics"]

    with engine.begin() as conn:
        conn.execute(
            effort_table.insert().values(
                id="eff-1",
                session_id="s1",
                duration_ms=30000,
                time_to_first_edit_ms=5000,
                interventions={"1": 2, "2": 1},
            )
        )
        query = select(effort_table).where(effort_table.c.id == "eff-1")
        row = conn.execute(query).mappings().one()
        assert row["duration_ms"] == 30000
        assert row["session_id"] == "s1"
        assert row["interventions"] == {"1": 2, "2": 1}

    # Ejecutar downgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.downgrade()

    inspector_down = inspect(engine)
    assert "effort_metrics" not in inspector_down.get_table_names()
