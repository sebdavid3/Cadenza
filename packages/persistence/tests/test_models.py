"""Pruebas de los modelos de persistencia sobre SQLite en memoria."""

from __future__ import annotations

from datetime import UTC, datetime

from cadenza.persistence import (
    ArtifactRecord,
    EditEventRecord,
    FindingRecord,
    Session,
    SessionFactory,
    SqlAlchemySessionRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from sqlalchemy import select


def _factory() -> SessionFactory:
    engine = create_memory_engine()
    create_schema(engine)
    return create_session_factory(engine)


def test_session_and_findings_roundtrip() -> None:
    factory = _factory()
    with factory() as db:
        artifact = ArtifactRecord(
            sha256="deadbeef1234",
            kind="image",
            media_type="image/png",
            size_bytes=1024,
            path="sha256/de/ad/deadbeef1234",
        )
        db.add(artifact)
        session = Session(
            id="s1",
            document_id="doc-1",
            omr_engine="fake",
            model_version="test-v1",
            status="transcribed",
            image_artifact="deadbeef1234",
            document={"id": "doc-1"},
        )
        session.findings = [
            FindingRecord(
                at_seq=0,
                rule_id="measure.balance",
                severity="error",
                message="msg",
                suggested_fix="fix",
                anchor={"part": 0, "bbox": [1.0, 2.0, 3.0, 4.0]},
            )
        ]
        db.add(session)
        db.commit()

    with factory() as db:
        loaded = db.get(Session, "s1")
        assert loaded is not None
        assert loaded.document == {"id": "doc-1"}
        assert loaded.model_version == "test-v1"
        assert loaded.status == "transcribed"
        assert loaded.image_artifact == "deadbeef1234"
        assert loaded.artifact is not None
        assert loaded.artifact.kind == "image"
        findings = db.scalars(select(FindingRecord)).all()
        assert len(findings) == 1
        assert findings[0].at_seq == 0
        assert findings[0].anchor["bbox"] == [1.0, 2.0, 3.0, 4.0]
        assert findings[0].created_at is not None


def test_edit_events_are_append_only() -> None:
    factory = _factory()
    with factory() as db:
        db.add(Session(id="s2", document_id="doc-2", omr_engine="fake", document={}))
        db.commit()
        db.add(
            EditEventRecord(
                id="e1",
                session_id="s2",
                seq=1,
                op="SetPitch",
                author="tester",
                anchor={"part": 0},
                before={"pitch": "C4"},
                after={"pitch": "D4"},
                created_at=datetime(2026, 9, 20, tzinfo=UTC),
            )
        )
        db.add(
            EditEventRecord(
                id="e2",
                session_id="s2",
                seq=2,
                op="SetPitch",
                author="tester",
                anchor={"part": 0},
                before={"pitch": "D4"},
                after={"pitch": "E4"},
                created_at=datetime(2026, 9, 20, tzinfo=UTC),
            )
        )
        db.commit()

    with factory() as db:
        rows = db.scalars(select(EditEventRecord).order_by(EditEventRecord.seq)).all()
        assert [row.seq for row in rows] == [1, 2]
        assert rows[0].before == {"pitch": "C4"}
        assert rows[1].after == {"pitch": "E4"}


def test_sqlalchemy_session_repository_roundtrip() -> None:
    factory = _factory()
    with factory() as db:
        repo = SqlAlchemySessionRepository(db)
        from cadenza.application import SessionData
        from cadenza.domain import Anchor, Finding, Severity

        session_data = SessionData(
            id="s3",
            document_id="doc-3",
            omr_engine="fake",
            model_version="omr-v2",
            status="reviewed",
            image_artifact="deadbeef5678",
            document={"id": "doc-3"},
            validated_at_seq=2,
        )
        finding = Finding(
            rule_id="r1",
            severity=Severity.WARNING,
            message="warn msg",
            suggested_fix=None,
            anchor=Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="s-0"),
            at_seq=2,
        )
        repo.add(session_data, [finding])
        db.commit()

    with factory() as db:
        repo = SqlAlchemySessionRepository(db)
        loaded = repo.get("s3")
        assert loaded is not None
        assert loaded.id == "s3"
        assert loaded.model_version == "omr-v2"
        assert loaded.status == "reviewed"
        assert loaded.image_artifact == "deadbeef5678"

        findings = repo.list_findings("s3")
        assert len(findings) == 1
        assert findings[0].at_seq == 2
        assert findings[0].rule_id == "r1"
        assert findings[0].severity == "warning"


def test_replace_findings_and_historical_preservation() -> None:
    factory = _factory()
    with factory() as db:
        repo = SqlAlchemySessionRepository(db)
        from cadenza.application import SessionData
        from cadenza.domain import Anchor, Finding, Severity

        session_data = SessionData(
            id="s4",
            document_id="doc-4",
            omr_engine="fake",
            document={"id": "doc-4"},
        )
        finding_initial = Finding(
            rule_id="measure.balance",
            severity=Severity.ERROR,
            message="unbalanced",
            suggested_fix=None,
            anchor=Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="s-0"),
            at_seq=0,
        )
        repo.add(session_data, [finding_initial])
        db.commit()

    with factory() as db:
        repo = SqlAlchemySessionRepository(db)
        loaded = repo.get("s4")
        assert loaded is not None
        assert loaded.validated_at_seq == 0
        assert len(repo.list_findings("s4", latest_only=True)) == 1

        # Reemplazar hallazgos en seq=1 con lista vacía (error corregido)
        repo.replace_findings("s4", [], at_seq=1)
        db.commit()

    with factory() as db:
        repo = SqlAlchemySessionRepository(db)
        loaded_after = repo.get("s4")
        assert loaded_after is not None
        assert loaded_after.validated_at_seq == 1
        assert len(repo.list_findings("s4", at_seq=0)) == 1
        assert len(repo.list_findings("s4", at_seq=1)) == 0

        # Idempotencia: re-evaluar en seq=1 con un nuevo hallazgo dos veces consecutivas
        from cadenza.application import SessionNotFound

        finding_new = Finding(
            rule_id="measure.balance",
            severity=Severity.ERROR,
            message="unbalanced again",
            suggested_fix=None,
            anchor=Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="s-0"),
            at_seq=1,
        )
        repo.replace_findings("s4", [finding_new], at_seq=1)
        db.commit()
        # Segunda llamada con el mismo at_seq=1 no duplica
        repo.replace_findings("s4", [finding_new], at_seq=1)
        db.commit()

        assert len(repo.list_findings("s4", latest_only=True)) == 1
        assert len(repo.list_findings("s4", at_seq=1)) == 1
        assert len(repo.list_findings("s4", latest_only=False)) == 2

        import pytest

        with pytest.raises(SessionNotFound):
            repo.replace_findings("nonexistent", [], at_seq=1)
