"""Pruebas de la migración Alembic 0011_session_condition_and_test_score (#33, D38)."""

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
    Text,
    func,
    inspect,
    select,
)
from sqlalchemy.types import JSON


def _load_migration_0011() -> types.ModuleType:
    migration_path = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "0011_session_condition_and_test_score.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0011", migration_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0011_metadata() -> None:
    mod = _load_migration_0011()
    assert mod.revision == "0011_session_condition_and_test_score"
    assert mod.down_revision == "0010_model_versions"


def test_migration_0011_upgrade_and_downgrade() -> None:
    mod = _load_migration_0011()
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
    Table(
        "artifacts",
        meta,
        Column("sha256", String(64), primary_key=True),
        Column("kind", String(32), nullable=False),
        Column("media_type", String(128), nullable=False),
        Column("size_bytes", Integer(), nullable=False),
        Column("path", Text(), nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    sessions = Table(
        "sessions",
        meta,
        Column("id", String(36), primary_key=True),
        Column("document_id", String(64), nullable=False),
        Column("omr_engine", String(64), nullable=False),
        Column("document", JSON, nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        Column("image_artifact", String(64), ForeignKey("artifacts.sha256"), nullable=True),
        Column("model_version", String(64), nullable=True),
        Column("status", String(32), server_default="transcribed", nullable=False),
        Column(
            "owner_id",
            String(36),
            ForeignKey("users.id"),
            nullable=False,
            server_default="default-user",
        ),
        Column("validated_at_seq", Integer(), server_default="0", nullable=False),
    )
    meta.create_all(engine)

    # Insertar usuario y sesión previa
    with engine.begin() as conn:
        conn.execute(
            users.insert().values(
                id="u1",
                username="participant_01",
                password_hash="hash",
                role="transcriptor",
                active=1,
            )
        )
        conn.execute(
            sessions.insert().values(
                id="s1",
                document_id="doc-1",
                omr_engine="mock",
                document={"score": {}},
                owner_id="u1",
            )
        )

    # Ejecutar upgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()

    inspector = inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("sessions")}
    assert "condition" in columns
    assert "test_score_id" in columns

    # Validar valor por defecto en fila existente
    meta_up = MetaData()
    meta_up.reflect(bind=engine)
    sess_table = meta_up.tables["sessions"]

    with engine.begin() as conn:
        row = conn.execute(select(sess_table).where(sess_table.c.id == "s1")).fetchone()
        assert row is not None
        assert row._mapping["condition"] == "assisted"
        assert row._mapping["test_score_id"] is None

        # Insertar sesión con condición no asistida y test_score_id
        conn.execute(
            sess_table.insert().values(
                id="s2",
                document_id="doc-2",
                omr_engine="mock",
                document={"score": {}},
                owner_id="u1",
                condition="unassisted",
                test_score_id="TS-01",
            )
        )
        row_s2 = conn.execute(select(sess_table).where(sess_table.c.id == "s2")).fetchone()
        assert row_s2 is not None
        assert row_s2._mapping["condition"] == "unassisted"
        assert row_s2._mapping["test_score_id"] == "TS-01"

    # Ejecutar downgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.downgrade()

    inspector_down = inspect(engine)
    columns_down = {c["name"]: c for c in inspector_down.get_columns("sessions")}
    assert "condition" not in columns_down
    assert "test_score_id" not in columns_down
