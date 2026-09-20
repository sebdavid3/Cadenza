"""Pruebas de los modelos de persistencia sobre SQLite en memoria."""

from __future__ import annotations

from datetime import UTC, datetime

from cadenza.persistence import (
    EditEventRecord,
    FindingRecord,
    Session,
    SessionFactory,
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
        session = Session(id="s1", document_id="doc-1", omr_engine="fake", document={"id": "doc-1"})
        session.findings = [
            FindingRecord(
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
        findings = db.scalars(select(FindingRecord)).all()
        assert len(findings) == 1
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
