"""Persistencia de las sugerencias y del registro de la capa (ADR-0036 §4, §8)."""

from __future__ import annotations

import importlib.util
import io
import types
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cadenza.application import (
    NewSuggestion,
    SessionData,
    SuggestionModelVersionData,
    SuggestionNotFound,
)
from cadenza.domain import Anchor, EditOp, Finding, Severity, SuggestedEdit
from cadenza.persistence import (
    ArtifactRecord,
    SqlAlchemySessionRepository,
    SqlAlchemySuggestionModelRegistry,
    UserRecord,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, func, inspect
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

MIGRATIONS = Path(__file__).parents[1] / "migrations" / "versions"


@pytest.fixture
def factory() -> sessionmaker[DbSession]:
    engine = create_memory_engine()
    create_schema(engine)
    return create_session_factory(engine)


def _anchor(index: int = 0) -> Anchor:
    return Anchor(part=0, staff=0, measure=1, voice=0, event_index=index, staff_id="P1-S1")


def _finding(index: int = 0, rule_id: str = "measure.balance") -> Finding:
    return Finding(anchor=_anchor(index), rule_id=rule_id, severity=Severity.ERROR, message="m")


def _suggestion(index: int, duration: str = "2") -> NewSuggestion:
    return NewSuggestion(
        edit=SuggestedEdit(
            op=EditOp.SET_DURATION,
            anchor=_anchor(index),
            after={"duration_beats": duration},
            before={"duration_beats": "1"},
            confidence=0.6,
            confidence_level="medium",
            explanation="Cambiar la negra por blanca.",
            source="learned",
            model_version="sug-1",
        )
    )


def _session(db: DbSession) -> SqlAlchemySessionRepository:
    db.add(UserRecord(id="u1", username="ana", password_hash="h", role="transcriptor"))
    db.flush()
    repo = SqlAlchemySessionRepository(db)
    repo.add(
        SessionData(
            id="s1",
            document_id="d",
            omr_engine="fake",
            document={"id": "d"},
            owner_id="u1",
        ),
        [_finding(0), _finding(1, "learned.accidental")],
        [[_suggestion(0), _suggestion(1)], []],
    )
    return repo


def test_suggestions_are_stored_with_their_findings_in_order(
    factory: sessionmaker[DbSession],
) -> None:
    with factory() as db:
        repo = _session(db)
        balance, learned = repo.list_findings("s1")
        assert learned.suggestions == ()
        first, second = balance.suggestions
        assert (first.rank, second.rank) == (0, 1)
        assert first.finding_id == balance.id and first.at_seq == 0
        assert (first.op, first.after, first.before) == (
            "SetDuration",
            {"duration_beats": "2"},
            {"duration_beats": "1"},
        )
        assert (first.confidence, first.confidence_level, first.source) == (
            0.6,
            "medium",
            "learned",
        )
        assert first.model_version == "sug-1" and first.response is None
        assert repo.get_suggestion("s1", first.id) == first
        assert repo.get_suggestion("other", first.id) is None


def test_replacing_findings_deletes_unanswered_suggestions_and_unlinks_answered_ones(
    factory: sessionmaker[DbSession],
) -> None:
    with factory() as db:
        repo = _session(db)
        balance, _ = repo.list_findings("s1")
        answered, unanswered = balance.suggestions
        rejected = repo.respond_suggestion("s1", answered.id, response="rejected", user="ana")
        assert (rejected.response, rejected.responded_by) == ("rejected", "ana")
        assert rejected.responded_at is not None

        replaced = repo.replace_findings(
            "s1", [_finding(0)], at_seq=0, suggestions=[[_suggestion(0, "3")]]
        )
        assert [s.after for s in replaced[0].suggestions] == [{"duration_beats": "3"}]
        # Los ids no se reutilizan: el de la borrada no apunta a la nueva.
        assert repo.get_suggestion("s1", unanswered.id) is None
        kept = repo.get_suggestion("s1", answered.id)
        assert kept is not None and kept.finding_id is None and kept.response == "rejected"
        # Otro estado: los hallazgos y las sugerencias de seq 0 se conservan.
        repo.replace_findings("s1", [], at_seq=1, suggestions=[])
        assert len(repo.list_suggestions("s1", at_seq=0)) == 2
        assert repo.list_suggestions("s1", at_seq=1) == ()


def test_an_inherited_rejection_is_stored_rejected(factory: sessionmaker[DbSession]) -> None:
    with factory() as db:
        repo = _session(db)
        balance, _ = repo.list_findings("s1")
        old = repo.respond_suggestion(
            "s1", balance.suggestions[0].id, response="rejected", user="ana"
        )
        new = NewSuggestion(edit=_suggestion(0).edit, inherited=old)
        (finding,) = repo.replace_findings("s1", [_finding(0)], at_seq=2, suggestions=[[new]])
        (stored,) = finding.suggestions
        assert (stored.response, stored.responded_by) == ("rejected", "ana")
        assert stored.id != old.id


def test_accepting_records_the_applied_seq_and_unknown_ids_fail(
    factory: sessionmaker[DbSession],
) -> None:
    with factory() as db:
        repo = _session(db)
        balance, _ = repo.list_findings("s1")
        accepted = repo.respond_suggestion(
            "s1", balance.suggestions[0].id, response="accepted", user="ana", applied_seq=1
        )
        assert (accepted.response, accepted.applied_seq) == ("accepted", 1)
        with pytest.raises(SuggestionNotFound):
            repo.respond_suggestion("s1", 999, response="rejected", user="ana")
        dismissed = repo.dismiss_finding("s1", balance.id, user="ana")
        assert len(dismissed.suggestions) == 2


def _registry_version(name: str) -> SuggestionModelVersionData:
    return SuggestionModelVersionData(
        version=name,
        artifact_hash="a" * 64,
        dataset_hash="d" * 64,
        config_hash="c" * 64,
        seed=42,
        model_type="frequency_backoff",
        feature_version=1,
        metrics={"families": {"accidental": {"f1": 0.5}}},
        created_at=datetime(2026, 10, 30, tzinfo=UTC),
    )


def test_suggestion_registry_is_separate_from_the_omr_registry(
    factory: sessionmaker[DbSession],
) -> None:
    with factory() as db:
        db.add(
            ArtifactRecord(
                sha256="a" * 64,
                kind="suggestion_model",
                media_type="application/json",
                size_bytes=10,
                path="x",
            )
        )
        db.flush()
        registry = SqlAlchemySuggestionModelRegistry(db)
        assert registry.active() is None
        registry.register(_registry_version("s1"))
        registry.register(_registry_version("s2"))
        with pytest.raises(ValueError):
            registry.register(_registry_version("s1"))
        registry.promote("s1")
        promoted = registry.promote("s2")
        assert promoted.promoted
        active = registry.active()
        assert active is not None and active.version == "s2"
        assert active.metrics == {"families": {"accidental": {"f1": 0.5}}}
        assert (active.seed, active.feature_version) == (42, 1)
        assert [v.promoted for v in registry.versions()] == [False, True]
        with pytest.raises(KeyError):
            registry.promote("nope")


def _load_migration() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(
        "migration_0013", MIGRATIONS / "0013_suggestions.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_0013_metadata() -> None:
    module = _load_migration()
    assert module.revision == "0013_suggestions"
    assert len(module.revision) <= 32
    assert module.down_revision == "0012_users_self_registered"


def test_migration_0013_upgrade_and_downgrade_on_sqlite() -> None:
    module = _load_migration()
    engine = create_memory_engine()
    meta = MetaData()
    Table("sessions", meta, Column("id", String(36), primary_key=True))
    Table("findings", meta, Column("id", Integer, primary_key=True))
    Table(
        "artifacts",
        meta,
        Column("sha256", String(64), primary_key=True),
        Column("created_at", DateTime(timezone=True), server_default=func.now()),
    )
    meta.create_all(engine)
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        module.upgrade()
    tables = set(inspect(engine).get_table_names())
    assert {"suggestions", "suggestion_model_versions"} <= tables
    columns = {c["name"] for c in inspect(engine).get_columns("suggestions")}
    assert {
        "session_id",
        "finding_id",
        "at_seq",
        "rank",
        "op",
        "anchor",
        "before",
        "after",
        "confidence",
        "confidence_level",
        "explanation",
        "source",
        "model_version",
        "response",
        "responded_by",
        "responded_at",
        "applied_seq",
    } <= columns
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        module.downgrade()
    assert not {"suggestions", "suggestion_model_versions"} & set(inspect(engine).get_table_names())


def test_migration_0013_generates_postgresql_sql() -> None:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg2://c:c@localhost:5432/c")
    buffer = io.StringIO()
    config.stdout = buffer
    command.upgrade(config, "0012_users_self_registered:0013_suggestions", sql=True)
    sql = buffer.getvalue()
    assert "CREATE TABLE suggestions" in sql
    assert "CREATE TABLE suggestion_model_versions" in sql
    assert "JSONB" in sql
    assert "ON DELETE SET NULL" in sql
    buffer = io.StringIO()
    config.stdout = buffer
    command.downgrade(config, "0013_suggestions:0012_users_self_registered", sql=True)
    assert "DROP TABLE suggestions" in buffer.getvalue()
