"""Pruebas de compatibilidad y verificación con PostgreSQL real (#6, ADR-0004, ADR-0007).

Valida:
1. Compilación de DDL y resolución de JSON a JSONB en dialecto PostgreSQL.
2. Presencia de la restricción UNIQUE(session_id, seq) y ondelete='RESTRICT' en edit_events.
3. Generación limpia de scripts SQL de migración (0001-0009) para dialecto PostgreSQL.
4. Pruebas de integración sobre servidor PostgreSQL en vivo (se omiten con pytest.skip si
   no hay servidor activo en CADENZA_TEST_POSTGRES_URL o localhost:5432).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from cadenza.persistence import create_session_factory
from cadenza.persistence.models import (
    EditEventRecord,
    EffortMetricsRecord,
    FindingRecord,
    Session,
    UserRecord,
)
from sqlalchemy import Table, create_engine, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.schema import CreateTable


def test_models_resolve_to_jsonb_in_postgresql_dialect() -> None:
    """Verifica que en PostgreSQL las columnas JsonDocument se compilen como JSONB (ADR-0004)."""
    pg_dialect = PGDialect_psycopg2()  # type: ignore[no-untyped-call]

    # 1. sessions.document debe compilar como JSONB
    sessions_ddl = str(CreateTable(cast(Table, Session.__table__)).compile(dialect=pg_dialect))
    assert "JSONB" in sessions_ddl

    # 2. edit_events.anchor, before, after deben compilar como JSONB
    edits_ddl = str(CreateTable(cast(Table, EditEventRecord.__table__)).compile(dialect=pg_dialect))
    assert "JSONB" in edits_ddl

    # 3. findings.anchor debe compilar como JSONB
    findings_ddl = str(
        CreateTable(cast(Table, FindingRecord.__table__)).compile(dialect=pg_dialect)
    )
    assert "JSONB" in findings_ddl

    # 4. effort_metrics.interventions debe compilar como JSONB
    effort_ddl = str(
        CreateTable(cast(Table, EffortMetricsRecord.__table__)).compile(dialect=pg_dialect)
    )
    assert "JSONB" in effort_ddl


def test_models_constraints_in_postgresql_dialect() -> None:
    """Verifica la restricción UNIQUE(session_id, seq) y ondelete='RESTRICT' (ADR-0007)."""
    pg_dialect = PGDialect_psycopg2()  # type: ignore[no-untyped-call]
    edits_ddl = str(CreateTable(cast(Table, EditEventRecord.__table__)).compile(dialect=pg_dialect))

    # Restricción de unicidad de secuencia por sesión
    assert "uq_edit_events_session_seq" in edits_ddl or "UNIQUE (session_id, seq)" in edits_ddl
    # Clave foránea con ondelete RESTRICT para inmutabilidad del log
    assert "RESTRICT" in edits_ddl


def test_alembic_migrations_offline_sql_generation_for_postgresql() -> None:
    """Verifica que todas las migraciones (0001..0009) generen SQL válido para PostgreSQL."""
    import io

    alembic_ini_path = Path(__file__).parents[1] / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg2://cadenza:cadenza@localhost:5432/cadenza",
    )

    buf = io.StringIO()
    alembic_cfg.stdout = buf
    command.upgrade(alembic_cfg, "head", sql=True)

    generated_sql = buf.getvalue()
    assert len(generated_sql) > 0
    assert "CREATE TABLE sessions" in generated_sql
    assert "CREATE TABLE edit_events" in generated_sql
    assert "CREATE TABLE findings" in generated_sql
    assert "CREATE TABLE artifacts" in generated_sql
    assert "CREATE TABLE effort_metrics" in generated_sql
    assert "0009_findings_dismissal" in generated_sql


def _get_live_postgres_url() -> str | None:
    """Obtiene la URL de PostgreSQL si está configurada o si el puerto estándar responde."""
    return os.getenv("CADENZA_TEST_POSTGRES_URL") or os.getenv("CADENZA_DATABASE_URL")


@pytest.fixture(scope="module")
def postgres_engine() -> Any:
    """Fixture que conecta a PostgreSQL real o salta las pruebas si no hay servidor."""
    url = _get_live_postgres_url()
    if not url or not url.startswith("postgresql"):
        pytest.skip("Servidor PostgreSQL no configurado (definir CADENZA_TEST_POSTGRES_URL)")

    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except (OperationalError, Exception) as exc:
        pytest.skip(f"No se pudo conectar al servidor PostgreSQL en {url}: {exc}")

    return engine


def test_postgres_live_migrations_and_jsonb_types(postgres_engine: Any) -> None:
    """Ejecuta migraciones sobre PostgreSQL real y valida tipos JSONB e índices."""
    url = _get_live_postgres_url()
    assert url is not None

    alembic_ini_path = Path(__file__).parents[1] / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", url)

    # Aplicar todas las migraciones
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(postgres_engine)
    table_names = inspector.get_table_names()
    assert "sessions" in table_names
    assert "edit_events" in table_names
    assert "findings" in table_names
    assert "users" in table_names
    assert "artifacts" in table_names
    assert "effort_metrics" in table_names

    # Verificar que las columnas JSON son efectivamente JSONB en PostgreSQL
    session_cols = {c["name"]: c for c in inspector.get_columns("sessions")}
    assert isinstance(session_cols["document"]["type"], JSONB)

    finding_cols = {c["name"]: c for c in inspector.get_columns("findings")}
    assert isinstance(finding_cols["anchor"]["type"], JSONB)

    edits_cols = {c["name"]: c for c in inspector.get_columns("edit_events")}
    assert isinstance(edits_cols["anchor"]["type"], JSONB)


def test_postgres_live_unique_constraint_and_restrict_delete(postgres_engine: Any) -> None:
    """Comprueba UNIQUE(session_id, seq) y ondelete='RESTRICT' sobre PostgreSQL real."""
    session_factory = create_session_factory(postgres_engine)

    with session_factory() as db:
        # Fixtures de usuario y sesión
        user = UserRecord(
            id="u-pg-test",
            username="pg_tester",
            password_hash="fakehash",
            role="transcriptor",
        )
        db.merge(user)
        session = Session(
            id="s-pg-test",
            owner_id="u-pg-test",
            document_id="doc-pg",
            omr_engine="fake",
            document={"score": {"parts": []}},
        )
        db.merge(session)
        db.commit()

    now = datetime.now(UTC)
    # 1. Verificar violación de UNIQUE(session_id, seq)
    with session_factory() as db:
        e1 = EditEventRecord(
            id="e-pg-1",
            session_id="s-pg-test",
            seq=1,
            op="SetPitch",
            author="pg_tester",
            anchor={"measure": 1, "voice": 0, "event_index": 0},
            created_at=now,
        )
        db.add(e1)
        db.commit()

        # Intentar insertar misma sesión y mismo seq
        e2 = EditEventRecord(
            id="e-pg-2",
            session_id="s-pg-test",
            seq=1,
            op="SetPitch",
            author="pg_tester",
            anchor={"measure": 1, "voice": 0, "event_index": 0},
            created_at=now,
        )
        db.add(e2)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    # 2. Verificar violación de ondelete='RESTRICT' en sessions
    with session_factory() as db:
        sess_to_delete = db.get(Session, "s-pg-test")
        assert sess_to_delete is not None
        db.delete(sess_to_delete)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
