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
from typing import Annotated, Any

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
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session as DbSession

from .schemas import (
    AnchorIndexPayload,
    ChangePasswordRequest,
    DismissFindingRequest,
    EditEventCreate,
    EditEventRead,
    EffortMetricsCreate,
    EffortMetricsRead,
    ErrorDetail,
    FinalizeResponse,
    FindingRead,
    ReopenResponse,
    RevalidateResponse,
    ScoreDocumentPayload,
    ScoreIRPayload,
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
    VersionResponse,
)
from .security import Argon2PasswordHasher, JwtTokenService
from .settings import Settings

API_VERSION = "1.0.0"

AUTH_401: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": ErrorDetail,
        "description": "Credenciales inválidas, token ausente o expirado (ADR-0012)",
    }
}
FORBIDDEN_403: dict[int | str, dict[str, Any]] = {
    status.HTTP_403_FORBIDDEN: {
        "model": ErrorDetail,
        "description": "Permisos insuficientes para realizar la operación solicitada",
    }
}
NOT_FOUND_404: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorDetail,
        "description": "Recurso no encontrado o no accesible para el usuario actual",
    }
}
CONFLICT_409: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {
        "model": ErrorDetail,
        "description": "Conflicto de secuencia, estado inválido o recurso duplicado",
    }
}
UNPROCESSABLE_422: dict[int | str, dict[str, Any]] = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ErrorDetail,
        "description": "Entidad no procesable o violación de validación de negocio",
    }
}
UPLOAD_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_413_CONTENT_TOO_LARGE: {
        "model": ErrorDetail,
        "description": "El archivo excede el tamaño máximo permitido",
    },
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {
        "model": ErrorDetail,
        "description": "Tipo de archivo no soportado (se requiere imagen PNG o JPEG)",
    },
}

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

    app = FastAPI(
        title="Cadenza API",
        version=API_VERSION,
        description=(
            "API REST de digitalización asistida de partituras (Cadenza v1). "
            "Proporciona transcripción con OMR, validación musical automática, "
            "registro append-only de correcciones humanas (HITL) y exportación "
            "MusicXML 4.0 / MIDI 1.0 (ADR-0004, ADR-0010, ADR-0012, ADR-0014)."
        ),
        openapi_tags=[
            {"name": "Auth", "description": "Autenticación JWT e identidad del usuario"},
            {"name": "Users", "description": "Gestión de cuentas (exclusivo para investigadores)"},
            {"name": "Transcription", "description": "Ingesta de imágenes y transcripción OMR"},
            {
                "name": "Sessions",
                "description": "Ciclo de vida, consulta y exportación de sesiones",
            },
            {
                "name": "Edits",
                "description": "Registro append-only de ediciones y compensación undo",
            },
            {
                "name": "Validation",
                "description": "Revalidación musical y gestión de falsos positivos",
            },
            {"name": "Effort", "description": "Registro y telemetría de métricas de esfuerzo"},
            {"name": "System", "description": "Metadatos y versión del servicio"},
        ],
    )

    @app.middleware("http")
    async def add_api_version_header(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        response.headers["X-API-Version"] = API_VERSION
        return response

    @app.get(
        "/version",
        response_model=VersionResponse,
        tags=["System"],
        summary="Versión del servicio y contrato de API",
        description="Devuelve la versión actual del contrato OpenAPI y de la aplicación Cadenza.",
    )
    def get_version_endpoint() -> VersionResponse:
        return VersionResponse(api_version=API_VERSION, app_version=API_VERSION)

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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": exc.message},
        )

    @app.exception_handler(NoEditsToUndo)
    def no_edits_to_undo_handler(request: Request, exc: NoEditsToUndo) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": str(exc)},
        )

    @app.post(
        "/auth/login",
        response_model=TokenResponse,
        tags=["Auth"],
        summary="Inicio de sesión",
        description=(
            "Autentica credenciales mediante formulario OAuth2 "
            "y emite un token de acceso Bearer JWT."
        ),
        responses={**UNPROCESSABLE_422},
    )
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

    @app.get(
        "/auth/me",
        response_model=UserRead,
        tags=["Auth"],
        summary="Perfil del usuario autenticado",
        description=(
            "Devuelve el perfil y rol del usuario correspondiente al token Bearer provisto."
        ),
        responses={**AUTH_401},
    )
    def get_me(current_user: CurrentUserDep) -> UserRead:
        """Devuelve el perfil del usuario autenticado."""
        return UserRead(
            id=current_user.id,
            username=current_user.username,
            role=current_user.role.value,
            active=current_user.active,
            created_at=current_user.created_at,
        )

    @app.post(
        "/auth/password",
        response_model=StatusResponse,
        tags=["Auth"],
        summary="Cambio de contraseña por el propio usuario",
        description=(
            "Permite al usuario autenticado cambiar su contraseña "
            "previa comprobación de la contraseña actual."
        ),
        responses={**AUTH_401, **UNPROCESSABLE_422},
    )
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

    @app.get(
        "/users",
        response_model=list[UserRead],
        tags=["Users"],
        summary="Listar cuentas registradas",
        description=(
            "Lista las cuentas registradas en el sistema. "
            "Operación exclusiva para usuarios con rol investigador (ADR-0012)."
        ),
        responses={**AUTH_401, **FORBIDDEN_403},
    )
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

    @app.post(
        "/users",
        response_model=UserRead,
        status_code=status.HTTP_201_CREATED,
        tags=["Users"],
        summary="Dar de alta una nueva cuenta de usuario",
        description=(
            "Crea una nueva cuenta de usuario con rol tipado. "
            "Exclusivo para investigadores (ADR-0012)."
        ),
        responses={**AUTH_401, **FORBIDDEN_403, **CONFLICT_409, **UNPROCESSABLE_422},
    )
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

    @app.patch(
        "/users/{user_id}",
        response_model=UserRead,
        tags=["Users"],
        summary="Modificar rol, estado o restablecer contraseña",
        description=(
            "Permite a un investigador modificar datos de acceso " "o rol de una cuenta existente."
        ),
        responses={**AUTH_401, **FORBIDDEN_403, **NOT_FOUND_404, **UNPROCESSABLE_422},
    )
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

    @app.post(
        "/transcribe",
        response_model=TranscribeResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["Transcription"],
        summary="Transcribir imagen con OMR y validación inicial",
        description=(
            "Sube una imagen de partitura, ejecuta inferencia OMR asíncrona, "
            "valida reglas y crea la sesión inicial."
        ),
        responses={**AUTH_401, **UPLOAD_ERRORS, **UNPROCESSABLE_422},
    )
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

    @app.get(
        "/sessions",
        response_model=list[SessionSummaryRead],
        tags=["Sessions"],
        summary="Listar sesiones con resúmenes ligeros paginados",
        description=(
            "Lista las sesiones con resúmenes ligeros "
            "sin transferir el ScoreDocument JSONB (ADR-0009, ADR-0012)."
        ),
        responses={**AUTH_401},
    )
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

    @app.get(
        "/sessions/{session_id}/image",
        tags=["Sessions"],
        summary="Descargar imagen de origen de la sesión",
        description=(
            "Recupera la imagen física de origen desde el ArtifactStore "
            "verificando permisos de acceso (ADR-0012)."
        ),
        responses={**AUTH_401, **FORBIDDEN_403, **NOT_FOUND_404},
    )
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
        tags=["Sessions"],
        summary="Exportar sesión a MusicXML o MIDI",
        description=(
            "Exporta el ScoreIR materializado de la sesión a formato "
            "MusicXML 4.0 o MIDI 1.0 (Issue #12, ADR-0010)."
        ),
        responses={**AUTH_401, **FORBIDDEN_403, **NOT_FOUND_404, **UNPROCESSABLE_422},
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

    @app.get(
        "/sessions/{session_id}",
        response_model=SessionDetailRead,
        tags=["Sessions"],
        summary="Detalle completo de sesión con estado materializado",
        description=(
            "Devuelve el ScoreDocument crudo, hallazgos, log de ediciones, "
            "current_score materializado y anchor_index enriquecido (ADR-0011)."
        ),
        responses={**AUTH_401, **FORBIDDEN_403, **NOT_FOUND_404},
    )
    def get_session(session_id: str, db: DbDep, current_user: CurrentUserDep) -> SessionDetailRead:
        session_repo = SqlAlchemySessionRepository(db)
        edit_repo = SqlAlchemyEditEventRepository(db)
        detail = get_session_use_case(
            session_id,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=current_user,
        )

        score_doc = ScoreDocumentPayload.model_validate(detail.document)
        curr_score = (
            ScoreIRPayload.model_validate(detail.current_score)
            if detail.current_score is not None
            else None
        )
        anchor_idx = (
            AnchorIndexPayload.model_validate(detail.anchor_index)
            if detail.anchor_index is not None
            else None
        )

        return SessionDetailRead(
            session_id=detail.session_id,
            document_id=detail.document_id,
            omr_engine=detail.omr_engine,
            document=score_doc,
            findings=[FindingRead.from_persisted(f) for f in detail.findings],
            edits=[EditEventRead.from_edit(e, detail.session_id) for e in detail.edits],
            current_score=curr_score,
            current_seq=detail.current_seq,
            anchor_index=anchor_idx,
            image_artifact=detail.image_artifact,
            model_version=detail.model_version,
            status=detail.status,
        )

    @app.get(
        "/sessions/{session_id}/findings",
        response_model=list[FindingRead],
        tags=["Validation"],
        summary="Listar hallazgos de validación de la sesión",
        description=(
            "Devuelve los hallazgos de la sesión, filtrando por defecto "
            "solo los activos no descartados (ADR-0013, #36)."
        ),
        responses={**AUTH_401, **FORBIDDEN_403, **NOT_FOUND_404},
    )
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
        tags=["Validation"],
        summary="Descartar un hallazgo como falso positivo",
        description=(
            "Marca un hallazgo como falso positivo descartado con motivo opcional "
            "y autoría fijada por el servidor (#36)."
        ),
        responses={**AUTH_401, **FORBIDDEN_403, **NOT_FOUND_404, **CONFLICT_409},
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
        tags=["Validation"],
        summary="Restaurar un hallazgo previamente descartado",
        description=(
            "Restaura un falso positivo previamente descartado "
            "al catálogo de hallazgos activos (#36)."
        ),
        responses={**AUTH_401, **FORBIDDEN_403, **NOT_FOUND_404, **CONFLICT_409},
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
        tags=["Validation"],
        summary="Revalidar partitura sobre su estado materializado actual",
        description=(
            "Aplica las reglas sobre el estado materializado actual de la partitura. "
            "Los hallazgos vigentes pasan a asociarse a current_seq, y los hallazgos "
            "de estados anteriores se conservan para análisis de esfuerzo (ADR-0013, #11)."
        ),
        responses={**AUTH_401, **FORBIDDEN_403, **NOT_FOUND_404},
    )
    def validate_session(
        session_id: str,
        request: Request,
        db: DbDep,
        current_user: CurrentUserDep,
    ) -> RevalidateResponse:
        """Revalida la partitura sobre su estado materializado actual (#11, ADR-0013)."""
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
        tags=["Sessions"],
        summary="Finalizar sesión y cerrar corrección",
        description=(
            "Ejecuta revalidación final y cierra la sesión "
            "contra nuevas ediciones humanas (ADR-0014, #34)."
        ),
        responses={**AUTH_401, **FORBIDDEN_403, **NOT_FOUND_404, **CONFLICT_409},
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
        tags=["Sessions"],
        summary="Reabrir una sesión finalizada",
        description=(
            "Reabre una sesión finalizada permitiendo retomar "
            "la adición de correcciones (ADR-0014, #34)."
        ),
        responses={**AUTH_401, **FORBIDDEN_403, **NOT_FOUND_404},
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
        tags=["Edits"],
        summary="Añadir una edición inmutable al log",
        description=(
            "Añade una corrección humana validada contra el estado actual. "
            "Exige base_seq, verifica before y fija autor por el servidor (ADR-0011, ADR-0012)."
        ),
        responses={
            **AUTH_401,
            **FORBIDDEN_403,
            **NOT_FOUND_404,
            **CONFLICT_409,
            **UNPROCESSABLE_422,
        },
    )
    def append_edit(
        session_id: str,
        payload: EditEventCreate,
        db: DbDep,
        current_user: CurrentUserDep,
    ) -> EditEventRead:
        """Añade una edición inmutable al log de la sesión."""
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
        tags=["Edits"],
        summary="Deshacer la última edición activa en el servidor",
        description=(
            "Registra un evento compensatorio inverso de la última edición activa "
            "en el log append-only sin borrar historia (ADR-0007, #35). "
            "Devuelve el nuevo current_seq, el ID de la edición deshecha, "
            "la partitura materializada actualizada y su índice de anclas."
        ),
        responses={
            **AUTH_401,
            **FORBIDDEN_403,
            **NOT_FOUND_404,
            **CONFLICT_409,
            **UNPROCESSABLE_422,
        },
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
        curr_score = ScoreIRPayload.model_validate(result.current_score)
        anchor_idx = (
            AnchorIndexPayload.model_validate(result.anchor_index)
            if result.anchor_index is not None
            else None
        )
        return UndoResponse(
            session_id=result.session_id,
            current_seq=result.current_seq,
            undone_edit_id=result.undone_edit_id,
            current_score=curr_score,
            anchor_index=anchor_idx,
            compensatory_edit_id=result.compensatory_edit.id,
            compensatory_edit=EditEventRead.from_edit(result.compensatory_edit, session_id),
        )

    @app.post(
        "/sessions/{session_id}/effort",
        response_model=EffortMetricsRead,
        status_code=status.HTTP_201_CREATED,
        tags=["Effort"],
        summary="Persistir métricas de esfuerzo de corrección",
        description=(
            "Persiste la duración, latencia hasta la primera edición e intervenciones por compás. "
            "Solo el dueño de la sesión puede registrar esfuerzo (ADR-0012, #13)."
        ),
        responses={**AUTH_401, **FORBIDDEN_403, **NOT_FOUND_404},
    )
    def record_effort_endpoint(
        session_id: str,
        payload: EffortMetricsCreate,
        db: DbDep,
        current_user: CurrentUserDep,
    ) -> EffortMetricsRead:
        """Persiste las métricas de esfuerzo de corrección de una sesión (#13, D13)."""
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
        tags=["Effort"],
        summary="Consultar métricas de esfuerzo de la sesión",
        description=(
            "Devuelve el historial de registros de métricas de esfuerzo "
            "de la sesión (ADR-0012, #13)."
        ),
        responses={**AUTH_401, **FORBIDDEN_403, **NOT_FOUND_404},
    )
    def get_effort_endpoint(
        session_id: str,
        db: DbDep,
        current_user: CurrentUserDep,
    ) -> list[EffortMetricsRead]:
        """Devuelve las métricas de esfuerzo registradas para una sesión (#13)."""
        session_repo = SqlAlchemySessionRepository(db)
        effort_repo = SqlAlchemyEffortRepository(db)
        metrics = get_effort_use_case(
            session_repo,
            effort_repo,
            session_id=session_id,
            current_user=current_user,
        )
        return [EffortMetricsRead.from_data(m) for m in metrics]

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
            tags=app.openapi_tags,
        )
        components = openapi_schema.setdefault("components", {})
        security_schemes = components.setdefault("securitySchemes", {})
        security_schemes["BearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Token JWT emitido por POST /auth/login. Enviar en la cabecera "
                "'Authorization: Bearer <token>'."
            ),
        }
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]

    return app


def create_default_app(settings: Settings | None = None) -> FastAPI:
    """Factory para uvicorn: carga Settings tipada de entorno y conecta el motor OMR."""

    app_settings = settings or Settings()
    engine = create_engine_for_url(app_settings.database_url)
    # En producción no se crea el esquema al arrancar; se depende de las migraciones (#6).
    if app_settings.auto_create_schema or (
        app_settings.database_url.startswith("sqlite") and ":memory:" in app_settings.database_url
    ):
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
