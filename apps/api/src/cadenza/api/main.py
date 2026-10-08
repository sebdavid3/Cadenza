"""API Gateway de Cadenza (FastAPI).

Raíz de composición hexagonal: construye y conecta los adaptadores (OMREngine,
ValidationEngine, SessionRepository, EditEventRepository, UserRepository,
PasswordHasher, TokenService) y delega la orquestación a la capa de aplicación
(ADR-0009, ADR-0012).
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Annotated

from cadenza.application import (
    ArtifactStore,
    DuplicateUsername,
    FindingNotFound,
    Forbidden,
    InvalidEdit,
    NoEditsToUndo,
    NotAuthenticated,
    PasswordHasher,
    Role,
    ScoreExporter,
    SequenceConflict,
    SessionClosed,
    SessionNotFound,
    TokenService,
    UnsupportedExportFormat,
    User,
    UserNotFound,
    WeakPassword,
    is_image_content,
)
from cadenza.application import (
    append_edit as append_edit_use_case,
)
from cadenza.application import (
    authenticate as authenticate_use_case,
)
from cadenza.application import (
    change_password as change_password_use_case,
)
from cadenza.application import (
    create_user as create_user_use_case,
)
from cadenza.application import (
    dismiss_finding as dismiss_finding_use_case,
)
from cadenza.application import (
    export_score as export_score_use_case,
)
from cadenza.application import (
    finalize_session as finalize_session_use_case,
)
from cadenza.application import (
    get_effort as get_effort_use_case,
)
from cadenza.application import (
    get_session as get_session_use_case,
)
from cadenza.application import (
    get_session_image as get_session_image_use_case,
)
from cadenza.application import (
    list_findings as list_findings_use_case,
)
from cadenza.application import (
    list_sessions as list_sessions_use_case,
)
from cadenza.application import (
    list_users as list_users_use_case,
)
from cadenza.application import (
    record_effort as record_effort_use_case,
)
from cadenza.application import (
    reopen_session as reopen_session_use_case,
)
from cadenza.application import (
    restore_finding as restore_finding_use_case,
)
from cadenza.application import (
    revalidate as revalidate_use_case,
)
from cadenza.application import (
    transcribe_score as transcribe_score_use_case,
)
from cadenza.application import (
    undo_edit as undo_edit_use_case,
)
from cadenza.application import (
    update_user as update_user_use_case,
)
from cadenza.interchange import Music21ScoreExporter
from cadenza.omr import FakeOMREngine, HOMREngine, OMREngine, OMRTranscriptionError
from cadenza.persistence import (
    FilesystemArtifactStore,
    SessionFactory,
    SqlAlchemyEditEventRepository,
    SqlAlchemyEffortRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
    create_engine_for_url,
    create_schema,
    create_session_factory,
)
from cadenza.validation import MeasureBalanceRule, ValidationEngine, ValidationRule
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session as DbSession

from .schemas import (
    ChangePasswordRequest,
    DismissFindingRequest,
    EditEventCreate,
    EditEventRead,
    EffortMetricsCreate,
    EffortMetricsRead,
    FinalizeResponse,
    FindingRead,
    ReopenResponse,
    RevalidateResponse,
    SessionDetailRead,
    SessionSummaryRead,
    StatusResponse,
    TokenResponse,
    TranscribeResponse,
    UndoRequest,
    UndoResponse,
    UserCreate,
    UserRead,
    UserUpdate,
)
from .security import Argon2PasswordHasher, JwtTokenService
from .settings import Settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


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


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    request: Request,
    db: DbDep,
) -> User:
    """Resuelve el usuario autenticado a partir del token de acceso Bearer."""

    token_service: TokenService = request.app.state.token_service
    try:
        payload = token_service.decode_token(token)
    except NotAuthenticated as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        ) from err

    user_repo = SqlAlchemyUserRepository(db)
    user = user_repo.get(payload.sub)
    if user is None or not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado o inactivo",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def get_artifact_store(request: Request, db: DbSession) -> ArtifactStore:
    """Obtiene el ArtifactStore configurado o instancia FilesystemArtifactStore."""
    store: ArtifactStore | None = getattr(request.app.state, "artifact_store", None)

    if store is not None:
        return store
    settings: Settings = request.app.state.settings
    return FilesystemArtifactStore(settings.artifacts_dir, session=db)


def create_app(
    session_factory: SessionFactory,
    *,
    omr_engine: OMREngine | None = None,
    rules: Sequence[ValidationRule] | None = None,
    settings: Settings | None = None,
    password_hasher: PasswordHasher | None = None,
    token_service: TokenService | None = None,
    artifact_store: ArtifactStore | None = None,
    score_exporter: ScoreExporter | None = None,
) -> FastAPI:
    """Construye la aplicación con dependencias inyectadas (raíz de composición)."""

    app_settings = settings or Settings()
    if not app_settings.auth_secret_key and token_service is None:
        raise RuntimeError(
            "CADENZA_AUTH_SECRET_KEY no configurada: "
            "la aplicación no puede iniciar sin clave de firma."
        )

    app = FastAPI(title="Cadenza API", version="0.1.0")
    app.state.session_factory = session_factory
    app.state.settings = app_settings
    app.state.omr_engine = omr_engine if omr_engine is not None else FakeOMREngine()
    app.state.validator = ValidationEngine(
        list(rules) if rules is not None else [MeasureBalanceRule()]
    )
    app.state.password_hasher = (
        password_hasher if password_hasher is not None else Argon2PasswordHasher()
    )
    app.state.token_service = (
        token_service
        if token_service is not None
        else JwtTokenService(
            secret_key=app_settings.auth_secret_key,
            default_expire_minutes=app_settings.auth_token_expire_minutes,
        )
    )
    app.state.artifact_store = artifact_store
    app.state.score_exporter = (
        score_exporter if score_exporter is not None else Music21ScoreExporter()
    )

    @app.exception_handler(UnsupportedExportFormat)
    def unsupported_export_format_handler(
        request: Request, exc: UnsupportedExportFormat
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.message, "format": exc.format},
        )

    @app.exception_handler(SessionNotFound)
    def session_not_found_handler(request: Request, exc: SessionNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "session not found"},
        )

    @app.exception_handler(FindingNotFound)
    def finding_not_found_handler(request: Request, exc: FindingNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "finding not found"},
        )

    @app.exception_handler(InvalidEdit)
    def invalid_edit_handler(request: Request, exc: InvalidEdit) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.message},
        )

    @app.exception_handler(NoEditsToUndo)
    def no_edits_to_undo_handler(request: Request, exc: NoEditsToUndo) -> JSONResponse:
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

    @app.exception_handler(SessionClosed)
    def session_closed_handler(request: Request, exc: SessionClosed) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.message},
        )

    @app.exception_handler(OMRTranscriptionError)
    def omr_transcription_error_handler(
        request: Request, exc: OMRTranscriptionError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": f"Error de transcripción OMR: {exc}"},
        )

    @app.exception_handler(NotAuthenticated)
    def not_authenticated_handler(request: Request, exc: NotAuthenticated) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": exc.message},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(Forbidden)
    def forbidden_handler(request: Request, exc: Forbidden) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": exc.message},
        )

    @app.exception_handler(DuplicateUsername)
    def duplicate_username_handler(request: Request, exc: DuplicateUsername) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exc)},
        )

    @app.exception_handler(UserNotFound)
    def user_not_found_handler(request: Request, exc: UserNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )

    @app.exception_handler(WeakPassword)
    def weak_password_handler(request: Request, exc: WeakPassword) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": str(exc)},
        )

    @app.post("/auth/login", response_model=TokenResponse)
    def login(
        form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
        request: Request,
        db: DbDep,
    ) -> TokenResponse:
        """Autentica las credenciales del usuario y emite un token de acceso JWT."""
        user_repo = SqlAlchemyUserRepository(db)
        hasher: PasswordHasher = request.app.state.password_hasher
        token_serv: TokenService = request.app.state.token_service

        user = authenticate_use_case(
            form_data.username,
            form_data.password,
            user_repository=user_repo,
            password_hasher=hasher,
        )
        token = token_serv.create_access_token(user_id=user.id, role=user.role)
        return TokenResponse(access_token=token, token_type="bearer")

    @app.get("/auth/me", response_model=UserRead)
    def get_me(current_user: CurrentUserDep) -> UserRead:
        """Devuelve el perfil del usuario autenticado."""
        return UserRead(
            id=current_user.id,
            username=current_user.username,
            role=current_user.role.value,
            active=current_user.active,
            created_at=current_user.created_at,
        )

    @app.post("/auth/password", response_model=StatusResponse)
    def change_password_endpoint(
        payload: ChangePasswordRequest,
        request: Request,
        db: DbDep,
        current_user: CurrentUserDep,
    ) -> StatusResponse:
        """Permite al usuario autenticado cambiar su propia contraseña."""
        user_repo = SqlAlchemyUserRepository(db)
        hasher: PasswordHasher = request.app.state.password_hasher
        change_password_use_case(
            payload.current_password,
            payload.new_password,
            current_user=current_user,
            user_repository=user_repo,
            password_hasher=hasher,
        )
        return StatusResponse(status="success", message="Contraseña actualizada")

    @app.get("/users", response_model=list[UserRead])
    def list_users_endpoint(
        db: DbDep,
        current_user: CurrentUserDep,
    ) -> list[UserRead]:
        """Lista las cuentas registradas en el sistema. Exclusivo para investigadores."""
        user_repo = SqlAlchemyUserRepository(db)
        users = list_users_use_case(
            current_user=current_user,
            user_repository=user_repo,
        )
        return [
            UserRead(
                id=u.id,
                username=u.username,
                role=u.role.value,
                active=u.active,
                created_at=u.created_at,
            )
            for u in users
        ]

    @app.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
    def create_user_endpoint(
        payload: UserCreate,
        request: Request,
        db: DbDep,
        current_user: CurrentUserDep,
    ) -> UserRead:
        """Crea una nueva cuenta de usuario. Exclusivo para investigadores."""
        user_repo = SqlAlchemyUserRepository(db)
        hasher: PasswordHasher = request.app.state.password_hasher
        new_user = create_user_use_case(
            payload.username,
            payload.password,
            Role(payload.role),
            current_user=current_user,
            user_repository=user_repo,
            password_hasher=hasher,
        )
        return UserRead(
            id=new_user.id,
            username=new_user.username,
            role=new_user.role.value,
            active=new_user.active,
            created_at=new_user.created_at,
        )

    @app.patch("/users/{user_id}", response_model=UserRead)
    def update_user_endpoint(
        user_id: str,
        payload: UserUpdate,
        request: Request,
        db: DbDep,
        current_user: CurrentUserDep,
    ) -> UserRead:
        """Modifica el rol, estado o restablece contraseña de una cuenta."""
        user_repo = SqlAlchemyUserRepository(db)
        hasher: PasswordHasher = request.app.state.password_hasher
        role = Role(payload.role) if payload.role is not None else None
        updated = update_user_use_case(
            user_id,
            current_user=current_user,
            user_repository=user_repo,
            role=role,
            active=payload.active,
            new_password=payload.password,
            password_hasher=hasher,
        )
        return UserRead(
            id=updated.id,
            username=updated.username,
            role=updated.role.value,
            active=updated.active,
            created_at=updated.created_at,
        )

    @app.post("/transcribe", response_model=TranscribeResponse, status_code=status.HTTP_201_CREATED)
    async def transcribe(
        request: Request,
        db: DbDep,
        current_user: CurrentUserDep,
        file: Annotated[UploadFile, File()],
    ) -> TranscribeResponse:
        app_settings: Settings = request.app.state.settings

        # 1. Validar Content-Type declarado
        declared_type = (file.content_type or "").lower()
        if declared_type == "application/pdf" or (
            declared_type
            and not (
                declared_type.startswith("image/") or declared_type == "application/octet-stream"
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Tipo de archivo no soportado. Se requiere una imagen.",
            )

        # 2. Leer contenido y validar tamaño máximo
        content = await file.read()
        if len(content) > app_settings.max_upload_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    f"El archivo excede el tamaño máximo permitido "
                    f"({app_settings.max_upload_size_bytes} bytes)."
                ),
            )

        # 3. Validar tipo real por magic bytes
        if not is_image_content(content):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Tipo de archivo no soportado. Se requiere una imagen válida (PNG, JPEG).",
            )

        session_repo = SqlAlchemySessionRepository(db)
        artifact_store = get_artifact_store(request, db)

        with tempfile.TemporaryDirectory(prefix="cadenza-upload-") as work_dir:
            upload_path = Path(work_dir) / Path(file.filename or "upload.png").name
            upload_path.write_bytes(content)
            result = await asyncio.to_thread(
                transcribe_score_use_case,
                upload_path,
                omr_engine=request.app.state.omr_engine,
                validator=request.app.state.validator,
                session_repository=session_repo,
                current_user=current_user,
                artifact_store=artifact_store,
            )

        return TranscribeResponse(
            session_id=result.session_id,
            document_id=result.document_id,
            omr_engine=result.omr_engine,
            findings_count=result.findings_count,
        )

    @app.get("/sessions", response_model=list[SessionSummaryRead])
    def list_sessions_endpoint(
        db: DbDep,
        current_user: CurrentUserDep,
        status: str | None = None,
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> list[SessionSummaryRead]:
        """Lista las sesiones con resúmenes ligeros paginados (#27, ADR-0009, ADR-0012).

        Un transcriptor solo ve sus sesiones; un investigador las ve todas.
        La consulta no carga la columna JSONB document.
        """
        session_repo = SqlAlchemySessionRepository(db)
        summaries = list_sessions_use_case(
            session_repository=session_repo,
            current_user=current_user,
            status=status,
            limit=limit,
            offset=offset,
        )
        return [
            SessionSummaryRead(
                session_id=s.session_id,
                document_id=s.document_id,
                omr_engine=s.omr_engine,
                model_version=s.model_version,
                status=s.status,
                created_at=s.created_at,
                findings_count=s.findings_count,
                edits_count=s.edits_count,
            )
            for s in summaries
        ]

    @app.get("/sessions/{session_id}/image")
    def get_session_image_endpoint(
        session_id: str,
        request: Request,
        db: DbDep,
        current_user: CurrentUserDep,
    ) -> Response:
        """Devuelve la imagen de origen asociada a la sesión."""
        session_repo = SqlAlchemySessionRepository(db)
        artifact_store = get_artifact_store(request, db)
        image_data = get_session_image_use_case(
            session_id,
            session_repository=session_repo,
            artifact_store=artifact_store,
            current_user=current_user,
        )
        return Response(content=image_data.content, media_type=image_data.media_type)

    @app.get(
        "/sessions/{session_id}/export",
        summary="Exportar sesión a MusicXML o MIDI",
        description=(
            "Exporta el ScoreIR materializado de la sesión a formato "
            "MusicXML 4.0 o MIDI 1.0 (Issue #12, ADR-0010)."
        ),
    )
    def export_session_endpoint(
        session_id: str,
        request: Request,
        db: DbDep,
        current_user: CurrentUserDep,
        format: str = Query(..., description="Formato de exportación: 'musicxml' o 'midi'"),
    ) -> Response:
        session_repo = SqlAlchemySessionRepository(db)
        edit_repo = SqlAlchemyEditEventRepository(db)
        exporter: ScoreExporter = (
            getattr(request.app.state, "score_exporter", None) or Music21ScoreExporter()
        )
        exported = export_score_use_case(
            session_repo,
            edit_repo,
            exporter,
            session_id=session_id,
            format=format,
            current_user=current_user,
        )
        content_bytes = (
            exported.content.encode("utf-8")
            if isinstance(exported.content, str)
            else exported.content
        )
        return Response(
            content=content_bytes,
            media_type=exported.media_type,
            headers={"Content-Disposition": f'attachment; filename="{exported.filename}"'},
        )

    @app.get("/sessions/{session_id}", response_model=SessionDetailRead)
    def get_session(session_id: str, db: DbDep, current_user: CurrentUserDep) -> SessionDetailRead:
        session_repo = SqlAlchemySessionRepository(db)
        edit_repo = SqlAlchemyEditEventRepository(db)
        detail = get_session_use_case(
            session_id,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=current_user,
        )

        return SessionDetailRead(
            session_id=detail.session_id,
            document_id=detail.document_id,
            omr_engine=detail.omr_engine,
            document=detail.document,
            findings=[FindingRead.from_persisted(f) for f in detail.findings],
            edits=[EditEventRead.from_edit(e, detail.session_id) for e in detail.edits],
            current_score=detail.current_score,
            current_seq=detail.current_seq,
            anchor_index=detail.anchor_index,
            image_artifact=detail.image_artifact,
            model_version=detail.model_version,
            status=detail.status,
        )

    @app.get("/sessions/{session_id}/findings", response_model=list[FindingRead])
    def list_findings(
        session_id: str,
        db: DbDep,
        current_user: CurrentUserDep,
        at_seq: int | None = None,
        latest_only: bool = True,
        include_dismissed: bool = False,
    ) -> list[FindingRead]:
        session_repo = SqlAlchemySessionRepository(db)
        findings = list_findings_use_case(
            session_id,
            session_repository=session_repo,
            current_user=current_user,
            at_seq=at_seq,
            latest_only=latest_only,
            include_dismissed=include_dismissed,
        )
        return [FindingRead.from_persisted(f) for f in findings]

    @app.post(
        "/sessions/{session_id}/findings/{finding_id}/dismiss",
        response_model=FindingRead,
    )
    def dismiss_finding_endpoint(
        session_id: str,
        finding_id: int,
        db: DbDep,
        current_user: CurrentUserDep,
        payload: DismissFindingRequest | None = None,
    ) -> FindingRead:
        """Descarta un hallazgo como falso positivo (#36)."""
        session_repo = SqlAlchemySessionRepository(db)
        reason = payload.reason if payload is not None else None
        dismissed = dismiss_finding_use_case(
            session_id,
            finding_id,
            session_repository=session_repo,
            current_user=current_user,
            reason=reason,
        )
        return FindingRead.from_persisted(dismissed)

    @app.post(
        "/sessions/{session_id}/findings/{finding_id}/restore",
        response_model=FindingRead,
    )
    def restore_finding_endpoint(
        session_id: str,
        finding_id: int,
        db: DbDep,
        current_user: CurrentUserDep,
    ) -> FindingRead:
        """Restaura un hallazgo previamente descartado a estado activo (#36)."""
        session_repo = SqlAlchemySessionRepository(db)
        restored = restore_finding_use_case(
            session_id,
            finding_id,
            session_repository=session_repo,
            current_user=current_user,
        )
        return FindingRead.from_persisted(restored)

    @app.post(
        "/sessions/{session_id}/validate",
        response_model=RevalidateResponse,
    )
    def validate_session(
        session_id: str,
        request: Request,
        db: DbDep,
        current_user: CurrentUserDep,
    ) -> RevalidateResponse:
        """Revalida la partitura sobre su estado materializado actual (#11, ADR-0013).

        Aplica las reglas sobre el estado materializado actual de la partitura.
        Los hallazgos vigentes pasan a asociarse a `current_seq`, y los hallazgos
        de estados anteriores se conservan en la base de datos para análisis de esfuerzo.
        """
        session_repo = SqlAlchemySessionRepository(db)
        edit_repo = SqlAlchemyEditEventRepository(db)
        result = revalidate_use_case(
            session_id,
            validator=request.app.state.validator,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=current_user,
        )
        return RevalidateResponse(
            session_id=result.session_id,
            current_seq=result.current_seq,
            findings=[FindingRead.from_persisted(f) for f in result.findings],
        )

    @app.post(
        "/sessions/{session_id}/finalize",
        response_model=FinalizeResponse,
    )
    def finalize_session_endpoint(
        session_id: str,
        request: Request,
        db: DbDep,
        current_user: CurrentUserDep,
    ) -> FinalizeResponse:
        """Finaliza una sesión de transcripción revalidándola y cerrándola.

        ADR-0014, #34.
        """
        session_repo = SqlAlchemySessionRepository(db)
        edit_repo = SqlAlchemyEditEventRepository(db)
        result = finalize_session_use_case(
            session_id,
            validator=request.app.state.validator,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=current_user,
        )
        return FinalizeResponse(
            session_id=result.session_id,
            status=result.status,
            final_seq=result.final_seq,
            findings=[FindingRead.from_persisted(f) for f in result.findings],
        )

    @app.post(
        "/sessions/{session_id}/reopen",
        response_model=ReopenResponse,
    )
    def reopen_session_endpoint(
        session_id: str,
        db: DbDep,
        current_user: CurrentUserDep,
    ) -> ReopenResponse:
        """Reabre una sesión finalizada permitiendo nuevas ediciones (#34, ADR-0014)."""
        session_repo = SqlAlchemySessionRepository(db)
        edit_repo = SqlAlchemyEditEventRepository(db)
        result = reopen_session_use_case(
            session_id,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=current_user,
        )
        return ReopenResponse(
            session_id=result.session_id,
            status=result.status,
            current_seq=result.current_seq,
        )

    @app.post(
        "/sessions/{session_id}/edits",
        response_model=EditEventRead,
        status_code=status.HTTP_201_CREATED,
    )
    def append_edit(
        session_id: str,
        payload: EditEventCreate,
        db: DbDep,
        current_user: CurrentUserDep,
    ) -> EditEventRead:
        """Añade una edición inmutable al log de la sesión.

        El autor lo fija el servidor a partir del usuario autenticado (ADR-0012).
        Exige `base_seq`, que identifica el estado sobre el cual se construyó la
        edición; si no coincide con el estado actual, responde 409 (ADR-0011).
        El ancla del payload se interpreta de forma posicional respecto a ese
        estado base (`base_seq`, ADR-0011).
        """
        session_repo = SqlAlchemySessionRepository(db)
        edit_repo = SqlAlchemyEditEventRepository(db)
        edit = append_edit_use_case(
            session_id,
            base_seq=payload.base_seq,
            anchor=payload.anchor.to_anchor(),
            op=payload.op,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=current_user,
            before=payload.before,
            after=payload.after,
        )
        return EditEventRead.from_edit(edit, session_id)

    @app.post(
        "/sessions/{session_id}/undo",
        response_model=UndoResponse,
        summary="Deshacer la última edición activa en el servidor",
        description=(
            "Registra un evento compensatorio inverso de la última edición activa "
            "en el log append-only sin borrar historia (ADR-0007, #35). "
            "Devuelve el nuevo current_seq, el ID de la edición deshecha, "
            "la partitura materializada actualizada y su índice de anclas."
        ),
    )
    def undo_session_edit(
        session_id: str,
        db: DbDep,
        current_user: CurrentUserDep,
        payload: UndoRequest | None = None,
    ) -> UndoResponse:
        session_repo = SqlAlchemySessionRepository(db)
        edit_repo = SqlAlchemyEditEventRepository(db)
        base_seq = payload.base_seq if payload is not None else None
        result = undo_edit_use_case(
            session_id,
            base_seq=base_seq,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=current_user,
        )
        return UndoResponse(
            session_id=result.session_id,
            current_seq=result.current_seq,
            undone_edit_id=result.undone_edit_id,
            current_score=result.current_score,
            anchor_index=result.anchor_index,
            compensatory_edit_id=result.compensatory_edit.id,
            compensatory_edit=EditEventRead.from_edit(result.compensatory_edit, session_id),
        )

    @app.post(
        "/sessions/{session_id}/effort",
        response_model=EffortMetricsRead,
        status_code=status.HTTP_201_CREATED,
    )
    def record_effort_endpoint(
        session_id: str,
        payload: EffortMetricsCreate,
        db: DbDep,
        current_user: CurrentUserDep,
    ) -> EffortMetricsRead:
        """Persiste las métricas de esfuerzo de corrección de una sesión (#13, D13).

        - Requiere autenticación.
        - Control de acceso ADR-0012:
          * Transcriptor ajeno responde 404 (SessionNotFound).
          * Investigador ajeno responde 403 (Forbidden): solo el dueño registra esfuerzo.
        """
        session_repo = SqlAlchemySessionRepository(db)
        effort_repo = SqlAlchemyEffortRepository(db)
        data = record_effort_use_case(
            session_repo,
            effort_repo,
            session_id=session_id,
            duration_ms=payload.duration_ms,
            time_to_first_edit_ms=payload.time_to_first_edit_ms,
            interventions=payload.interventions,
            current_user=current_user,
        )
        return EffortMetricsRead.from_data(data)

    @app.get(
        "/sessions/{session_id}/effort",
        response_model=list[EffortMetricsRead],
    )
    def get_effort_endpoint(
        session_id: str,
        db: DbDep,
        current_user: CurrentUserDep,
    ) -> list[EffortMetricsRead]:
        """Devuelve las métricas de esfuerzo registradas para una sesión (#13).

        - Requiere autenticación.
        - Control de acceso ADR-0012:
          * Transcriptor ajeno responde 404 (SessionNotFound).
        """
        session_repo = SqlAlchemySessionRepository(db)
        effort_repo = SqlAlchemyEffortRepository(db)
        metrics = get_effort_use_case(
            session_repo,
            effort_repo,
            session_id=session_id,
            current_user=current_user,
        )
        return [EffortMetricsRead.from_data(m) for m in metrics]

    return app


def create_default_app(settings: Settings | None = None) -> FastAPI:
    """Factory para uvicorn: carga Settings tipada de entorno y conecta el motor OMR."""

    app_settings = settings or Settings()
    engine = create_engine_for_url(app_settings.database_url)
    create_schema(engine)

    omr_engine: OMREngine
    if app_settings.omr_engine == "homr":
        omr_engine = HOMREngine(use_gpu=app_settings.omr_use_gpu)
    else:
        omr_engine = FakeOMREngine()

    return create_app(
        create_session_factory(engine),
        omr_engine=omr_engine,
        settings=app_settings,
    )
