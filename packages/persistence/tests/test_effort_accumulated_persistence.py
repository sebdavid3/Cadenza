"""El registro de esfuerzo que acumula la web, en la base (#188, ADR-0050, migración 0015).

Uno por sesión (índice único parcial), con sus tramos, sus intervenciones por clase y sus
contadores; los registros sueltos de `POST /effort` (#13) siguen como antes.
"""

from __future__ import annotations

import importlib.util
import io
import types
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cadenza.application import EffortMetricsData, EffortSegment
from cadenza.application.ports.effort_repository import empty_accumulated
from cadenza.persistence import (
    SqlAlchemyEffortRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from cadenza.persistence.models import EffortMetricsRecord, Session, UserRecord
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
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

MIGRATIONS = Path(__file__).parents[1] / "migrations" / "versions"
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def db() -> Iterator[DbSession]:
    engine = create_memory_engine()
    create_schema(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        session.add(UserRecord(id="u1", username="u1", password_hash="h", role="transcriptor"))
        session.add(
            Session(id="s1", owner_id="u1", document_id="d1", omr_engine="fake", document={})
        )
        session.flush()
        yield session


def _metrics(**changes: Any) -> EffortMetricsData:
    return replace(empty_accumulated("s1", NOW), **changes)


def test_save_creates_then_updates_the_single_accumulated_record(db: DbSession) -> None:
    repo = SqlAlchemyEffortRepository(db)
    assert repo.get_accumulated("s1") is None

    first = repo.save_accumulated(
        _metrics(segments=(EffortSegment("tab-a", 1_000),), duration_ms=1_000)
    )
    second = repo.save_accumulated(
        _metrics(
            segments=(EffortSegment("tab-a", 4_000, 2_500), EffortSegment("tab-b", 500)),
            duration_ms=4_500,
            time_to_first_edit_ms=2_500,
            interventions={"1": 2},
            interventions_by_class={"content": {"1": 2}, "mark": {}, "meter": {}},
            suggestions_applied=1,
            suggestions_rejected=2,
            updated_at=NOW,
        )
    )

    assert second.id == first.id
    stored = repo.get_accumulated("s1")
    assert stored is not None
    assert stored.accumulated is True
    assert stored.segments == (EffortSegment("tab-a", 4_000, 2_500), EffortSegment("tab-b", 500))
    assert (stored.duration_ms, stored.time_to_first_edit_ms) == (4_500, 2_500)
    assert stored.interventions == {"1": 2}
    assert stored.interventions_by_class == {"content": {"1": 2}, "mark": {}, "meter": {}}
    assert (stored.suggestions_applied, stored.suggestions_rejected) == (1, 2)
    assert len(repo.list_by_session("s1")) == 1


def test_counters_add_up_in_the_database_and_saving_keeps_them(db: DbSession) -> None:
    repo = SqlAlchemyEffortRepository(db)
    repo.add_finding_action("s1", "dismissed", now=NOW)
    repo.add_finding_action("s1", "dismissed", now=NOW)
    repo.add_finding_action("s1", "restored", now=NOW)

    repo.save_accumulated(_metrics(segments=(EffortSegment("tab-a", 9_000),), duration_ms=9_000))

    stored = repo.get_accumulated("s1")
    assert stored is not None
    assert (stored.findings_dismissed, stored.findings_restored) == (2, 1)
    assert stored.duration_ms == 9_000
    assert len(repo.list_by_session("s1")) == 1


def test_loose_records_are_not_the_accumulated_one(db: DbSession) -> None:
    repo = SqlAlchemyEffortRepository(db)
    loose = repo.add(
        EffortMetricsData(
            id="loose",
            session_id="s1",
            duration_ms=5,
            time_to_first_edit_ms=None,
            interventions={},
            created_at=NOW,
        )
    )

    assert loose.accumulated is False
    assert loose.segments == ()
    assert loose.findings_dismissed == 0
    assert repo.get_accumulated("s1") is None


def test_the_database_refuses_a_second_accumulated_record(db: DbSession) -> None:
    for record_id in ("a", "b"):
        db.add(
            EffortMetricsRecord(
                id=record_id,
                session_id="s1",
                duration_ms=0,
                interventions={},
                accumulated=True,
            )
        )
    with pytest.raises(IntegrityError):
        db.flush()


def test_several_loose_records_are_still_allowed(db: DbSession) -> None:
    for record_id in ("a", "b"):
        db.add(EffortMetricsRecord(id=record_id, session_id="s1", duration_ms=0, interventions={}))
    db.flush()
    assert len(db.scalars(select(EffortMetricsRecord)).all()) == 2


# --- Migración 0015 ------------------------------------------------------------------------


def _load_migration() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "migration_0015", MIGRATIONS / "0015_effort_accumulated.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_0015_metadata() -> None:
    module = _load_migration()
    assert module.revision == "0015_effort_accumulated"
    assert len(module.revision) <= 32
    assert module.down_revision == "0014_session_metadata"


def test_migration_0015_upgrade_and_downgrade_on_sqlite() -> None:
    module = _load_migration()
    engine = create_memory_engine()
    meta = MetaData()
    Table("sessions", meta, Column("id", String(36), primary_key=True))
    effort = Table(
        "effort_metrics",
        meta,
        Column("id", String(36), primary_key=True),
        Column("session_id", String(36), ForeignKey("sessions.id"), nullable=False),
        Column("duration_ms", Integer, nullable=False),
        Column("time_to_first_edit_ms", Integer, nullable=True),
        Column("interventions", JSON, nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(meta.tables["sessions"].insert().values(id="s1"))
        conn.execute(
            effort.insert().values(id="old", session_id="s1", duration_ms=7, interventions={})
        )

    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        module.upgrade()

    reloaded = Table("effort_metrics", MetaData(), autoload_with=engine)
    with engine.connect() as conn:
        row = conn.execute(select(reloaded)).mappings().one()
    # El registro anterior queda suelto, sin tramos y a cero.
    assert row["accumulated"] in (False, 0)
    assert row["segments"] == []
    assert row["interventions_by_class"] == {}
    assert (
        row["findings_dismissed"],
        row["findings_restored"],
        row["suggestions_applied"],
        row["suggestions_rejected"],
    ) == (0, 0, 0, 0)
    assert row["updated_at"] is None
    indexes = {index["name"]: index for index in inspect(engine).get_indexes("effort_metrics")}
    assert indexes["uq_effort_metrics_accumulated_session"]["unique"]

    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        module.downgrade()

    remaining = {c["name"] for c in inspect(engine).get_columns("effort_metrics")}
    assert remaining == {
        "id",
        "session_id",
        "duration_ms",
        "time_to_first_edit_ms",
        "interventions",
        "created_at",
    }


def test_migration_0015_generates_postgresql_sql() -> None:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg2://c:c@localhost:5432/c")
    buffer = io.StringIO()
    config.stdout = buffer
    command.upgrade(config, "0014_session_metadata:0015_effort_accumulated", sql=True)
    sql = buffer.getvalue()
    assert "ALTER TABLE effort_metrics ADD COLUMN accumulated BOOLEAN DEFAULT false NOT NULL" in sql
    assert "ALTER TABLE effort_metrics ADD COLUMN segments JSONB DEFAULT '[]' NOT NULL" in sql
    assert (
        "ALTER TABLE effort_metrics ADD COLUMN interventions_by_class JSONB DEFAULT '{}' NOT NULL"
        in sql
    )
    assert "CREATE UNIQUE INDEX uq_effort_metrics_accumulated_session" in sql
    assert "WHERE accumulated" in sql

    buffer.truncate(0)
    buffer.seek(0)
    command.downgrade(config, "0015_effort_accumulated:0014_session_metadata", sql=True)
    downgrade_sql = buffer.getvalue()
    assert "DROP INDEX uq_effort_metrics_accumulated_session" in downgrade_sql
    assert "ALTER TABLE effort_metrics DROP COLUMN segments" in downgrade_sql
