"""Pruebas de la migración Alembic 0009_findings_dismissal (#36)."""

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


def _load_migration_0009() -> types.ModuleType:
    migration_path = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0009_findings_dismissal.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0009", migration_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0009_metadata() -> None:
    mod = _load_migration_0009()
    assert mod.revision == "0009_findings_dismissal"
    assert mod.down_revision == "0008_edit_events_reverts_edit_id"


def test_migration_0009_upgrade_and_downgrade() -> None:
    mod = _load_migration_0009()
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
    findings = Table(
        "findings",
        meta,
        Column("id", Integer(), primary_key=True, autoincrement=True),
        Column("session_id", String(36), ForeignKey("sessions.id"), nullable=False),
        Column("at_seq", Integer(), nullable=False, server_default="0"),
        Column("rule_id", String(128), nullable=False),
        Column("severity", String(16), nullable=False),
        Column("message", Text(), nullable=False),
        Column("suggested_fix", Text(), nullable=True),
        Column("anchor", JSON, nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
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
            findings.insert().values(
                id=1,
                session_id="s1",
                at_seq=0,
                rule_id="measure.balance",
                severity="error",
                message="Compás incompleto",
                suggested_fix=None,
                anchor={"measure": 1, "voice": 0, "event_index": 0},
            )
        )

    # Ejecutar upgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()

    inspector = inspect(engine)
    columns = {c["name"]: c for c in inspector.get_columns("findings")}
    assert "status" in columns
    assert "dismissed_at" in columns
    assert "dismissed_by" in columns
    assert "dismissal_reason" in columns
    assert columns["status"]["nullable"] is False
    assert columns["dismissed_at"]["nullable"] is True
    assert columns["dismissed_by"]["nullable"] is True
    assert columns["dismissal_reason"]["nullable"] is True

    # Verificar que el registro preexistente tomó el server_default "active"
    meta_up = MetaData()
    meta_up.reflect(bind=engine)
    findings_up = meta_up.tables["findings"]

    with engine.begin() as conn:
        query = select(findings_up).where(findings_up.c.id == 1)
        row = conn.execute(query).mappings().one()
        assert row["status"] == "active"
        assert row["dismissed_at"] is None
        assert row["dismissed_by"] is None
        assert row["dismissal_reason"] is None

        # Insertar y consultar fila descartada
        conn.execute(
            findings_up.insert().values(
                id=2,
                session_id="s1",
                at_seq=0,
                rule_id="pitch.range",
                severity="warning",
                message="Altura fuera de tesitura",
                suggested_fix=None,
                anchor={"measure": 1, "voice": 0, "event_index": 1},
                status="dismissed",
                dismissed_at=func.now(),
                dismissed_by="transcriptor1",
                dismissal_reason="Válido en contexto litúrgico",
            )
        )
        row2 = conn.execute(select(findings_up).where(findings_up.c.id == 2)).mappings().one()
        assert row2["status"] == "dismissed"
        assert row2["dismissed_by"] == "transcriptor1"
        assert row2["dismissal_reason"] == "Válido en contexto litúrgico"
        assert row2["dismissed_at"] is not None

    # Ejecutar downgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.downgrade()

    inspector_down = inspect(engine)
    columns_down = {c["name"]: c for c in inspector_down.get_columns("findings")}
    assert "status" not in columns_down
    assert "dismissed_at" not in columns_down
    assert "dismissed_by" not in columns_down
    assert "dismissal_reason" not in columns_down
