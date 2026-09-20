"""API Gateway de Cadenza (FastAPI).

Flujo hexagonal: `OMREngine` (fake) → `ValidationEngine` → persistencia. El
`ScoreDocument` es la fuente de verdad; la API solo lo transporta, valida y
guarda. Las correcciones se registran como `EditEvent` inmutables (ADR-0007).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from cadenza.domain import EditEvent
from cadenza.omr import FakeOMREngine, OMREngine
from cadenza.persistence import (
    EditEventRecord,
    FindingRecord,
    SessionFactory,
    create_engine_for_url,
    create_schema,
    create_session_factory,
)
from cadenza.persistence import Session as SessionRecord
from cadenza.validation import MeasureBalanceRule, ValidationEngine, ValidationRule
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from .schemas import EditEventCreate, EditEventRead, FindingRead, TranscribeResponse


def get_db(request: Request) -> Iterator[DbSession]:
    """Dependencia de base de datos: una sesión por request, con commit/rollback."""

    factory: SessionFactory = request.app.state.session_factory
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DbDep = Annotated[DbSession, Depends(get_db)]


def create_app(
    session_factory: SessionFactory,
    *,
    omr_engine: OMREngine | None = None,
    rules: Sequence[ValidationRule] | None = None,
) -> FastAPI:
    """Construye la aplicación con dependencias inyectadas (testeable)."""

    app = FastAPI(title="Cadenza API", version="0.1.0")
    app.state.session_factory = session_factory
    app.state.omr_engine = omr_engine if omr_engine is not None else FakeOMREngine()
    app.state.validator = ValidationEngine(
        list(rules) if rules is not None else [MeasureBalanceRule()]
    )

    @app.post("/transcribe", response_model=TranscribeResponse, status_code=status.HTTP_201_CREATED)
    def transcribe(
        request: Request,
        db: DbDep,
        file: Annotated[UploadFile, File()],
    ) -> TranscribeResponse:
        engine: OMREngine = request.app.state.omr_engine
        validator: ValidationEngine = request.app.state.validator

        document = engine.transcribe(Path(file.filename or "upload.png"))
        findings = validator.validate(document)

        session_id = str(uuid.uuid4())
        record = SessionRecord(
            id=session_id,
            document_id=document.id,
            omr_engine=document.provenance.omr_engine,
            document=document.to_primitive(),
        )
        record.findings = [
            FindingRecord(
                rule_id=finding.rule_id,
                severity=finding.severity.value,
                message=finding.message,
                suggested_fix=finding.suggested_fix,
                anchor=finding.anchor.to_primitive(),
            )
            for finding in findings
        ]
        db.add(record)
        db.flush()
        return TranscribeResponse(
            session_id=session_id,
            document_id=document.id,
            omr_engine=document.provenance.omr_engine,
            findings_count=len(findings),
        )

    @app.get("/sessions/{session_id}/findings", response_model=list[FindingRead])
    def list_findings(session_id: str, db: DbDep) -> list[FindingRead]:
        if db.get(SessionRecord, session_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
        rows = db.scalars(
            select(FindingRecord)
            .where(FindingRecord.session_id == session_id)
            .order_by(FindingRecord.id)
        ).all()
        return [FindingRead.from_record(row) for row in rows]

    @app.post(
        "/sessions/{session_id}/edits",
        response_model=EditEventRead,
        status_code=status.HTTP_201_CREATED,
    )
    def append_edit(session_id: str, payload: EditEventCreate, db: DbDep) -> EditEventRead:
        record = db.get(SessionRecord, session_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

        max_seq = db.scalar(
            select(func.coalesce(func.max(EditEventRecord.seq), 0)).where(
                EditEventRecord.session_id == session_id
            )
        )
        edit = EditEvent(
            id=str(uuid.uuid4()),
            document_id=record.document_id,
            seq=int(max_seq or 0) + 1,
            anchor=payload.anchor.to_anchor(),
            op=payload.op,
            author=payload.author,
            created_at=datetime.now(UTC),
            before=payload.before,
            after=payload.after,
        )
        row = EditEventRecord(
            id=edit.id,
            session_id=session_id,
            seq=edit.seq,
            op=edit.op.value,
            author=edit.author,
            anchor=edit.anchor.to_primitive(),
            before=None if edit.before is None else dict(edit.before),
            after=None if edit.after is None else dict(edit.after),
            created_at=edit.created_at,
        )
        db.add(row)
        db.flush()
        return EditEventRead.from_record(row)

    return app


def create_default_app() -> FastAPI:
    """Factory para uvicorn: usa `CADENZA_DATABASE_URL` (SQLite por defecto)."""

    url = os.environ.get("CADENZA_DATABASE_URL", "sqlite+pysqlite:///./cadenza.db")
    engine = create_engine_for_url(url)
    create_schema(engine)
    return create_app(create_session_factory(engine))
