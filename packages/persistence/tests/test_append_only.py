"""El log de ediciones debe ser inmutable (append-only) a nivel de ORM (ADR-0007)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from cadenza.persistence import (
    EditEventRecord,
    ImmutableEditEventError,
    Session,
    SessionFactory,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from sqlalchemy.exc import IntegrityError


def _factory() -> SessionFactory:
    engine = create_memory_engine()
    create_schema(engine)
    return create_session_factory(engine)


def _event(event_id: str, seq: int, session_id: str = "s1") -> EditEventRecord:
    return EditEventRecord(
        id=event_id,
        session_id=session_id,
        seq=seq,
        op="SetPitch",
        author="tester",
        anchor={"part": 0, "staff": 0, "measure": 1, "voice": 0, "event_index": 0, "staff_id": "s"},
        before={"pitch": "C4"},
        after={"pitch": "D4"},
        created_at=datetime(2026, 9, 20, tzinfo=UTC),
    )


def _seed(factory: SessionFactory) -> None:
    with factory() as db:
        db.add(Session(id="s1", document_id="doc-1", omr_engine="fake", document={}))
        db.add(_event("e1", 1))
        db.commit()


def test_update_of_persisted_event_is_forbidden() -> None:
    factory = _factory()
    _seed(factory)
    with factory() as db:
        row = db.get(EditEventRecord, "e1")
        assert row is not None
        row.after = {"pitch": "E4"}
        with pytest.raises(ImmutableEditEventError):
            db.commit()
        db.rollback()


def test_delete_of_persisted_event_is_forbidden() -> None:
    factory = _factory()
    _seed(factory)
    with factory() as db:
        row = db.get(EditEventRecord, "e1")
        assert row is not None
        db.delete(row)
        with pytest.raises(ImmutableEditEventError):
            db.commit()
        db.rollback()


def test_deleting_session_does_not_destroy_log() -> None:
    factory = _factory()
    _seed(factory)
    with factory() as db:
        session = db.get(Session, "s1")
        assert session is not None
        db.delete(session)
        with pytest.raises((ImmutableEditEventError, IntegrityError)):
            db.commit()
        db.rollback()


def test_duplicate_sequence_is_rejected() -> None:
    factory = _factory()
    _seed(factory)
    with factory() as db:
        db.add(_event("e2", 1))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
