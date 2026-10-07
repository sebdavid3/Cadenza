"""API Gateway de Cadenza (FastAPI).

Raíz de composición hexagonal: construye y conecta los adaptadores (OMREngine,
ValidationEngine, SessionRepository, EditEventRepository) y delega la orquestación
a la capa de aplicación (ADR-0009).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Annotated

from cadenza.application import (
    InvalidEdit,
    SequenceConflict,
    SessionNotFound,
)
from cadenza.application import (
    append_edit as append_edit_use_case,
)
from cadenza.application import (
    get_session as get_session_use_case,
)
from cadenza.application import (
    list_findings as list_findings_use_case,
)
from cadenza.application import (
    transcribe_score as transcribe_score_use_case,
)
from cadenza.omr import FakeOMREngine, OMREngine
from cadenza.persistence import (
    SessionFactory,
    SqlAlchemyEditEventRepository,
    SqlAlchemySessionRepository,
    create_engine_for_url,
    create_schema,
    create_session_factory,
)
from cadenza.validation import MeasureBalanceRule, ValidationEngine, ValidationRule
from fastapi import Depends, FastAPI, File, Request, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session as DbSession

from .schemas import (
    EditEventCreate,
    EditEventRead,
    FindingRead,
    SessionDetailRead,
    TranscribeResponse,
)


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
    """Construye la aplicación con dependencias inyectadas (raíz de composición)."""

    app = FastAPI(title="Cadenza API", version="0.1.0")
    app.state.session_factory = session_factory
    app.state.omr_engine = omr_engine if omr_engine is not None else FakeOMREngine()
    app.state.validator = ValidationEngine(
        list(rules) if rules is not None else [MeasureBalanceRule()]
    )

    @app.exception_handler(SessionNotFound)
    def session_not_found_handler(request: Request, exc: SessionNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "session not found"},
        )

    @app.exception_handler(InvalidEdit)
    def invalid_edit_handler(request: Request, exc: InvalidEdit) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.message},
        )

    @app.exception_handler(SequenceConflict)
    def sequence_conflict_handler(request: Request, exc: SequenceConflict) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exc)},
        )

    @app.post("/transcribe", response_model=TranscribeResponse, status_code=status.HTTP_201_CREATED)
    def transcribe(
        request: Request,
        db: DbDep,
        file: Annotated[UploadFile, File()],
    ) -> TranscribeResponse:
        session_repo = SqlAlchemySessionRepository(db)
        with tempfile.TemporaryDirectory(prefix="cadenza-upload-") as work_dir:
            upload_path = Path(work_dir) / Path(file.filename or "upload.png").name
            with upload_path.open("wb") as handle:
                shutil.copyfileobj(file.file, handle)
            result = transcribe_score_use_case(
                upload_path,
                omr_engine=request.app.state.omr_engine,
                validator=request.app.state.validator,
                session_repository=session_repo,
            )

        return TranscribeResponse(
            session_id=result.session_id,
            document_id=result.document_id,
            omr_engine=result.omr_engine,
            findings_count=result.findings_count,
        )

    @app.get("/sessions/{session_id}", response_model=SessionDetailRead)
    def get_session(session_id: str, db: DbDep) -> SessionDetailRead:
        session_repo = SqlAlchemySessionRepository(db)
        edit_repo = SqlAlchemyEditEventRepository(db)
        detail = get_session_use_case(
            session_id,
            session_repository=session_repo,
            edit_repository=edit_repo,
        )

        return SessionDetailRead(
            session_id=detail.session_id,
            document_id=detail.document_id,
            omr_engine=detail.omr_engine,
            document=detail.document,
            findings=[FindingRead.from_persisted(f) for f in detail.findings],
            edits=[EditEventRead.from_edit(e, detail.session_id) for e in detail.edits],
            current_score=detail.current_score,
        )

    @app.get("/sessions/{session_id}/findings", response_model=list[FindingRead])
    def list_findings(session_id: str, db: DbDep) -> list[FindingRead]:
        session_repo = SqlAlchemySessionRepository(db)
        findings = list_findings_use_case(session_id, session_repository=session_repo)
        return [FindingRead.from_persisted(f) for f in findings]

    @app.post(
        "/sessions/{session_id}/edits",
        response_model=EditEventRead,
        status_code=status.HTTP_201_CREATED,
    )
    def append_edit(session_id: str, payload: EditEventCreate, db: DbDep) -> EditEventRead:
        session_repo = SqlAlchemySessionRepository(db)
        edit_repo = SqlAlchemyEditEventRepository(db)
        edit = append_edit_use_case(
            session_id,
            anchor=payload.anchor.to_anchor(),
            op=payload.op,
            author=payload.author,
            session_repository=session_repo,
            edit_repository=edit_repo,
            before=payload.before,
            after=payload.after,
        )
        return EditEventRead.from_edit(edit, session_id)

    return app


def create_default_app() -> FastAPI:
    """Factory para uvicorn: usa `CADENZA_DATABASE_URL` (SQLite por defecto)."""

    url = os.environ.get("CADENZA_DATABASE_URL", "sqlite+pysqlite:///./cadenza.db")
    engine = create_engine_for_url(url)
    create_schema(engine)
    return create_app(create_session_factory(engine))
