"""Pruebas de la migración Alembic 0005_users_and_session_owner (ADR-0012, #43)."""

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


def _load_migration_0005() -> types.ModuleType:
    migration_path = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0005_users_and_session_owner.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0005", migration_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0005_metadata() -> None:
    mod = _load_migration_0005()
    assert mod.revision == "0005_users_and_session_owner"
    assert mod.down_revision == "0004_sessions_findings_schema"


def test_migration_0005_upgrade_and_downgrade() -> None:
    mod = _load_migration_0005()
    engine = create_memory_engine()

    # 1. Crear el esquema en el estado 0004 (sessions sin owner_id)
    meta = MetaData()
    artifacts = Table(
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
        Column("document_id", String(255), nullable=False),
        Column("omr_engine", String(64), nullable=False),
        Column("model_version", String(64), nullable=True),
        Column("status", String(32), server_default="transcribed", nullable=False),
        Column(
            "image_artifact",
            String(64),
            ForeignKey("artifacts.sha256", ondelete="SET NULL"),
            nullable=True,
        ),
        Column("document", JSON(), nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    findings = Table(
        "findings",
        meta,
        Column("id", Integer(), primary_key=True, autoincrement=True),
        Column(
            "session_id",
            String(36),
            ForeignKey("sessions.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        ),
        Column("at_seq", Integer(), server_default="0", nullable=False),
        Column("rule_id", String(128), nullable=False),
        Column("severity", String(16), nullable=False),
        Column("message", Text(), nullable=False),
        Column("suggested_fix", Text(), nullable=True),
        Column("anchor", JSON(), nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    meta.create_all(engine)

    # 2. Insertar registros previos a la migración
    with engine.begin() as conn:
        conn.execute(
            artifacts.insert().values(
                sha256="abc123sha",
                kind="image",
                media_type="image/png",
                size_bytes=100,
                path="sha256/ab/c1/abc123sha",
            )
        )
        conn.execute(
            sessions.insert().values(
                id="sess-pre",
                document_id="doc-pre",
                omr_engine="fake",
                model_version="1.0",
                status="transcribed",
                image_artifact="abc123sha",
                document={"id": "doc-pre"},
            )
        )
        conn.execute(
            findings.insert().values(
                session_id="sess-pre",
                at_seq=0,
                rule_id="measure.balance",
                severity="error",
                message="unbalanced",
                suggested_fix=None,
                anchor={"measure": 1},
            )
        )

    # 3. Ejecutar UPGRADE de la migración 0005
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()

    # 4. Inspeccionar tabla users y columna owner_id añadida a sessions
    with engine.connect() as conn:
        inspector = inspect(conn)
        tables = inspector.get_table_names()
        assert "users" in tables

        user_cols = {col["name"]: col for col in inspector.get_columns("users")}
        assert "id" in user_cols
        assert "username" in user_cols
        assert "password_hash" in user_cols
        assert "role" in user_cols
        assert "active" in user_cols
        assert "created_at" in user_cols

        session_cols = {col["name"]: col for col in inspector.get_columns("sessions")}
        assert "owner_id" in session_cols

        # Verificar usuario semilla insertado
        meta_after = MetaData()
        users_after = Table("users", meta_after, autoload_with=conn)
        sessions_after = Table("sessions", meta_after, autoload_with=conn)

        seed_user = conn.execute(
            select(
                users_after.c.id,
                users_after.c.username,
                users_after.c.role,
                users_after.c.active,
            ).where(users_after.c.id == "default-user")
        ).one()
        assert seed_user[0] == "default-user"
        assert seed_user[1] == "admin"
        assert seed_user[2] == "investigador"
        assert seed_user[3] is True

        # Verificar que la sesión preexistente fue asociada a default-user
        session_row = conn.execute(
            select(
                sessions_after.c.id,
                sessions_after.c.owner_id,
            ).where(sessions_after.c.id == "sess-pre")
        ).one()
        assert session_row[0] == "sess-pre"
        assert session_row[1] == "default-user"

    # 5. Ejecutar DOWNGRADE de la migración 0005
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.downgrade()

    # 6. Verificar que owner_id fue removido y la tabla users eliminada
    with engine.connect() as conn:
        inspector = inspect(conn)
        tables_after = inspector.get_table_names()
        assert "users" not in tables_after

        session_cols_after = {col["name"] for col in inspector.get_columns("sessions")}
        assert "owner_id" not in session_cols_after
