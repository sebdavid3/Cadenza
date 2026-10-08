"""Pruebas de la migración Alembic 0008_edit_events_reverts_edit_id (#35, ADR-0007)."""

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


def _load_migration_0008() -> types.ModuleType:
    migration_path = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "0008_edit_events_reverts_edit_id.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0008", migration_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0008_metadata() -> None:
    mod = _load_migration_0008()
    assert mod.revision == "0008_edit_events_reverts_edit_id"
    assert mod.down_revision == "0007_effort_metrics_table"


def test_migration_0008_upgrade_and_downgrade() -> None:
    mod = _load_migration_0008()
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
    edit_events = Table(
        "edit_events",
        meta,
        Column("id", String(36), primary_key=True),
        Column("session_id", String(36), ForeignKey("sessions.id"), nullable=False),
        Column("seq", Integer(), nullable=False),
        Column("op", String(32), nullable=False),
        Column("author", String(128), nullable=False),
        Column("anchor", JSON, nullable=False),
        Column("before", JSON, nullable=True),
        Column("after", JSON, nullable=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )
    meta.create_all(engine)

    # Inserción de fixtures iniciales
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
        conn.execute(
            edit_events.insert().values(
                id="e1",
                session_id="s1",
                seq=1,
                op="SetPitch",
                author="transcriptor1",
                anchor={"measure": 1, "voice": 0, "event_index": 0},
                before={"pitch": "C4"},
                after={"pitch": "D4"},
                created_at=func.now(),
            )
        )

    # Ejecutar upgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()

    inspector = inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("edit_events")}
    assert "reverts_edit_id" in columns
    assert columns["reverts_edit_id"]["nullable"] is True

    # Insertar y consultar fila con reverts_edit_id
    meta_up = MetaData()
    meta_up.reflect(bind=engine)
    edit_table = meta_up.tables["edit_events"]

    with engine.begin() as conn:
        conn.execute(
            edit_table.insert().values(
                id="inv-1",
                session_id="s1",
                seq=2,
                op="SetPitch",
                author="transcriptor1",
                anchor={"measure": 1, "voice": 0, "event_index": 0},
                before={"pitch": "D4"},
                after={"pitch": "C4"},
                reverts_edit_id="e1",
                created_at=func.now(),
            )
        )
        query = select(edit_table).where(edit_table.c.id == "inv-1")
        row = conn.execute(query).mappings().one()
        assert row["reverts_edit_id"] == "e1"

    # Ejecutar downgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.downgrade()

    inspector_down = inspect(engine)
    columns_down = {c["name"]: c for c in inspector_down.get_columns("edit_events")}
    assert "reverts_edit_id" not in columns_down
