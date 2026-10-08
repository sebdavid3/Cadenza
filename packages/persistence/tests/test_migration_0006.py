"""Pruebas de la migración Alembic 0006_session_validated_at_seq (ADR-0013, #11)."""

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


def _load_migration_0006() -> types.ModuleType:
    migration_path = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0006_session_validated_at_seq.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0006", migration_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0006_metadata() -> None:
    mod = _load_migration_0006()
    assert mod.revision == "0006_session_validated_at_seq"
    assert mod.down_revision == "0005_users_and_session_owner"


def test_migration_0006_upgrade_and_downgrade() -> None:
    mod = _load_migration_0006()
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
    )
    meta.create_all(engine)

    # Insertar usuario y sesión previa
    with engine.begin() as conn:
        conn.execute(
            users.insert().values(
                id="u1",
                username="test-user",
                password_hash="hash",
                role="transcriptor",
                active=1,
            )
        )
        conn.execute(
            sessions.insert().values(
                id="s1",
                document_id="doc1",
                omr_engine="fake",
                document={"score": {}},
                owner_id="u1",
            )
        )

    # Aplicar upgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()

    insp = inspect(engine)
    cols = {col["name"]: col for col in insp.get_columns("sessions")}
    assert "validated_at_seq" in cols

    # Verificar que las filas existentes tienen validated_at_seq = 0
    with engine.connect() as conn:
        meta_after = MetaData()
        sessions_after = Table("sessions", meta_after, autoload_with=conn)
        row = (
            conn.execute(select(sessions_after.c.id, sessions_after.c.validated_at_seq))
            .mappings()
            .one()
        )
        assert row["id"] == "s1"
        assert row["validated_at_seq"] == 0

    # Aplicar downgrade
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.downgrade()

    insp2 = inspect(engine)
    cols2 = {col["name"]: col for col in insp2.get_columns("sessions")}
    assert "validated_at_seq" not in cols2
