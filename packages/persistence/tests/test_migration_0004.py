"""Pruebas de la migración Alembic 0004_sessions_findings_schema (ADR-0004, #5)."""

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


def _load_migration_0004() -> types.ModuleType:
    migration_path = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0004_sessions_findings_schema.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0004", migration_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0004_metadata() -> None:
    mod = _load_migration_0004()
    assert mod.revision == "0004_sessions_findings_schema"
    assert mod.down_revision == "0003_artifacts_table"


def test_migration_0004_upgrade_and_downgrade() -> None:
    mod = _load_migration_0004()
    engine = create_memory_engine()

    # 1. Crear el esquema en el estado 0003 (sin los nuevos campos de 0004)
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
        Column("rule_id", String(128), nullable=False),
        Column("severity", String(16), nullable=False),
        Column("message", Text(), nullable=False),
        Column("suggested_fix", Text(), nullable=True),
        Column("anchor", JSON(), nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    meta.create_all(engine)

    # 2. Insertar registros existentes previos a la migración
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
                document={"id": "doc-pre"},
            )
        )
        conn.execute(
            findings.insert().values(
                session_id="sess-pre",
                rule_id="measure.balance",
                severity="error",
                message="unbalanced",
                suggested_fix=None,
                anchor={"measure": 1},
            )
        )

    # 3. Ejecutar UPGRADE de la migración 0004
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()

    # 4. Inspeccionar columnas añadidas
    with engine.connect() as conn:
        inspector = inspect(conn)
        session_cols = {col["name"]: col for col in inspector.get_columns("sessions")}
        finding_cols = {col["name"]: col for col in inspector.get_columns("findings")}

        assert "image_artifact" in session_cols
        assert "model_version" in session_cols
        assert "status" in session_cols
        assert "at_seq" in finding_cols

        # Verificar que las filas existentes se rellenaron con server_default
        meta_after = MetaData()
        sessions_after = Table("sessions", meta_after, autoload_with=conn)
        findings_after = Table("findings", meta_after, autoload_with=conn)

        row_session = conn.execute(
            select(
                sessions_after.c.id,
                sessions_after.c.status,
                sessions_after.c.image_artifact,
                sessions_after.c.model_version,
            )
        ).one()
        assert row_session[0] == "sess-pre"
        assert row_session[1] == "transcribed"  # status rellenado por defecto
        assert row_session[2] is None  # image_artifact nullable
        assert row_session[3] is None  # model_version nullable

        row_finding = conn.execute(
            select(
                findings_after.c.id,
                findings_after.c.at_seq,
            )
        ).one()
        assert row_finding[1] == 0  # at_seq rellenado con 0

    # 5. Ejecutar DOWNGRADE de la migración 0004
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.downgrade()

    # 6. Verificar que las columnas añadidas se eliminaron
    with engine.connect() as conn:
        inspector = inspect(conn)
        session_cols_after = {col["name"] for col in inspector.get_columns("sessions")}
        finding_cols_after = {col["name"] for col in inspector.get_columns("findings")}

        assert "image_artifact" not in session_cols_after
        assert "model_version" not in session_cols_after
        assert "status" not in session_cols_after
        assert "at_seq" not in finding_cols_after
