"""API Gateway de Cadenza (FastAPI).

Raíz de composición hexagonal: construye y conecta los adaptadores (OMREngine,
ValidationEngine, SessionRepository, EditEventRepository, UserRepository,
PasswordHasher, TokenService) y delega la orquestación a la capa de aplicación
(ADR-0009, ADR-0012).
"""

from __future__ import annotations

import logging
import os
import re
import sys
import tempfile
import time
import uuid
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Annotated, Any, Literal

from cadenza.application import (
    ArtifactStore,
    DuplicateUsername,
    FindingNotFound,
    Forbidden,
    InMemoryScoreStateCache,
    InvalidEdit,
    NoEditsToUndo,
    NotAuthenticated,
    PasswordHasher,
    Role,
    ScoreExporter,
    ScoreStateCache,
    SequenceConflict,
    SessionClosed,
    SessionNotFound,
    StaleSuggestion,
    SuggestionConflict,
    SuggestionModel,
    SuggestionNotFound,
    TokenService,
    TranscribeResult,
    UnsupportedExportFormat,
    User,
    UserNotFound,
    WeakPassword,
    collect_stage_timings,
    is_image_content,
    normalize_condition,
    timed_stage,
)
from cadenza.application import (
    append_edit_with_state as append_edit_use_case,
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
    get_timing as get_timing_use_case,
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
    register_user as register_user_use_case,
)
from cadenza.application import (
    reject_suggestion as reject_suggestion_use_case,
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
from cadenza.domain import TimingMap
from cadenza.interchange import Music21ScoreExporter
from cadenza.omr import (
    HOMREngine,
    OMREngine,
    OMRTranscriptionError,
    get_effective_device,
)
from cadenza.omr.power import disable_power_throttling
from cadenza.persistence import (
    FilesystemArtifactStore,
    SessionFactory,
    SqlAlchemyEditEventRepository,
    SqlAlchemyEffortRepository,
    SqlAlchemyModelRegistry,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
    create_engine_for_url,
    create_schema,
    create_session_factory,
)
from cadenza.validation import ValidationEngine, ValidationRule, get_default_rules
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from .schemas import (
    AnchorIndexPayload,
    AnchorPayload,
    ChangePasswordRequest,
    DismissFindingRequest,
    EditAppliedRead,
    EditEventCreate,
    EditEventRead,
    EffortMetricsCreate,
    EffortMetricsRead,
    ErrorDetail,
    EventTimingRead,
    FinalizeResponse,
    FindingRead,
    HealthStatusResponse,
    RegisterRequest,
    ReopenResponse,
    RevalidateResponse,
    ScoreDocumentPayload,
    ScoreIRPayload,
    SessionDetailRead,
    SessionSummaryRead,
    SessionViewRead,
    StatusResponse,
    SuggestionRead,
    TimingMapRead,
    TokenResponse,
    TranscribeResponse,
    UndoRequest,
    UndoResponse,
    UserCreate,
    UserRead,
    UserUpdate,
    VersionResponse,
)
from .security import (
    Argon2PasswordHasher,
    JwtTokenService,
    LoginRateLimiter,
    client_network_key,
)
from .settings import Settings
from .suggestions import load_suggestion_model
from .transcription_slots import TranscriptionSlots, run_in_transcription_slot

logger = logging.getLogger("cadenza.api")
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
RATE_LIMITED_429: dict[int | str, dict[str, Any]] = {
    status.HTTP_429_TOO_MANY_REQUESTS: {
        "model": ErrorDetail,
        "description": "Demasiados intentos desde la misma IP; ver la cabecera Retry-After",
    }
}
TRANSCRIBE_BUSY_503: dict[int | str, dict[str, Any]] = {
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorDetail,
        "description": (
            "Demasiadas transcripciones en curso: reintentar tras la cabecera Retry-After "
            "(ADR-0024)"
        ),
        "headers": {
            "Retry-After": {
                "description": "Segundos que conviene esperar antes de reintentar",
                "schema": {"type": "integer"},
            }
        },
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

# Un X-Request-ID del cliente se acepta si tiene esta forma; si no, se genera otro: va al
# registro tal cual (#275).
_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}")
# Orden de las etapas en `Server-Timing` (ADR-0037); las demás, detrás.
_STAGE_ORDER = ("db", "materialize", "export", "timing", "serialize")


def _server_timing(stages: dict[str, float], total_ms: float) -> str:
    """`db;dur=1.20, materialize;dur=0.40, …, total;dur=3.10` (milisegundos)."""
    names = [n for n in _STAGE_ORDER if n in stages] + sorted(
        n for n in stages if n not in _STAGE_ORDER
    )
    items = [f"{name};dur={stages[name]:.2f}" for name in names]
    items.append(f"total;dur={total_ms:.2f}")
    return ", ".join(items)


def _json_response(model: BaseModel, status_code: int = status.HTTP_200_OK) -> Response:
    """Serializa el modelo una sola vez, medido como etapa `serialize` (#275).

    FastAPI validaría y serializaría de nuevo lo que ya es un modelo del contrato; con una
    partitura entera, eso es la mayor parte de la serialización.
    """
    with timed_stage("serialize"):
        body = model.model_dump_json()
    return Response(content=body, status_code=status_code, media_type="application/json")


def _timing_read(session_id: str, timing_map: TimingMap) -> TimingMapRead:
    return TimingMapRead(
        session_id=session_id,
        total_beats=str(timing_map.total_beats),
        measure_offsets={str(k): str(v) for k, v in timing_map.measure_offsets.items()},
        events=[
            EventTimingRead(
                anchor=AnchorPayload.model_validate(ev.anchor.to_primitive()),
                kind=ev.kind.value,
                measure_number=ev.measure_number,
                voice=ev.voice,
                offset_beats=str(ev.offset_beats),
                duration_beats=str(ev.duration_beats),
                measure_offset_beats=str(ev.measure_offset_beats),
            )
            for ev in timing_map.events
        ],
    )


def get_db(request: Request) -> Iterator[DbSession]:
    """Dependencia de base de datos: una sesión por request, con commit/rollback."""

    factory: SessionFactory = request.app.state.session_factory
    session = factory()
    try:
        yield session
        with timed_stage("db"):
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# scope="function": la transacción se confirma (o se deshace) al terminar la ruta y antes de
# enviar la respuesta. Con el ámbito por defecto de FastAPI («request»), el commit corría después
# de enviarla: el cliente recibía un 2xx aunque el commit fallase, y una petición inmediata podía
# no ver lo que acababa de crear (#166).
DbDep = Annotated[DbSession, Depends(get_db, scope="function")]


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
    with timed_stage("db"):
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


def configure_logging() -> None:
    """Configura el manejador para los registradores 'cadenza.*' si no existe ninguno.

    Garantiza que bajo el arranque documentado (uvicorn cadenza.api.main:create_default_app
    --factory) los registros de cadenza.* sean visibles en la salida de error estándar (stderr)
    con formato unificado, sin líneas duplicadas y sin alterar la configuración de quienes ya
    traigan la suya.
    """
    cadenza_logger = logging.getLogger("cadenza")
    if not cadenza_logger.hasHandlers():
        handler = logging.StreamHandler(sys.stderr)
        formatter: logging.Formatter
        try:
            from uvicorn.logging import DefaultFormatter

            formatter = DefaultFormatter("%(levelprefix)s %(message)s")
        except ImportError:
            formatter = logging.Formatter("%(levelname)s:     %(message)s")
        handler.setFormatter(formatter)
        cadenza_logger.addHandler(handler)
        if cadenza_logger.level == logging.NOTSET:
            cadenza_logger.setLevel(logging.INFO)


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
    model_registry: Any | None = None,
    score_cache: ScoreStateCache | None = None,
    suggestion_model: SuggestionModel | None = None,
) -> FastAPI:
    """Construye la aplicación con dependencias inyectadas (raíz de composición).

    La capa de sugerencias (ADR-0036) solo corre con `Settings.suggestions_enabled`: la
    versión promovida del registro se carga aquí, al arrancar, envuelta en la política de qué
    se muestra (ADR-0036, enmienda 19), salvo que se inyecte otra: la inyectada se usa tal
    cual, sin política.
    """

    configure_logging()
    app_settings = settings or Settings()
    if not app_settings.auth_secret_key and token_service is None:
        raise RuntimeError(
            "CADENZA_AUTH_SECRET_KEY no configurada: "
            "la aplicación no puede iniciar sin clave de firma."
        )

    if app_settings.disable_power_throttling:
        throttling_applied = disable_power_throttling()
        logger.info(
            "power_throttling_disabled requested=True applied=%s platform=%s",
            throttling_applied,
            sys.platform,
        )
    else:
        logger.info(
            "power_throttling_disabled requested=False applied=False platform=%s",
            sys.platform,
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
            {"name": "System", "description": "Metadatos, salud y versión del servicio"},
        ],
    )

    if app_settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=app_settings.cors_origins,
            # Con `*` no se envían credenciales: Starlette devolvería como permitido cualquier
            # origen junto con `Allow-Credentials` (#123). La API usa tokens Bearer, no cookies.
            allow_credentials="*" not in app_settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID", "X-API-Version", "Server-Timing"],
        )

    @app.middleware("http")
    async def request_id_and_access_log_middleware(request: Request, call_next: Any) -> Response:
        # El que envía la web (#275) relaciona su medida de una orden con este registro.
        incoming = request.headers.get("X-Request-ID") or ""
        req_id = (
            incoming if _REQUEST_ID_PATTERN.fullmatch(incoming) is not None else uuid.uuid4().hex
        )
        request.state.request_id = req_id
        start_time = time.perf_counter()

        # Las etapas que marcan la ruta y los casos de uso, para `Server-Timing` (ADR-0037).
        with collect_stage_timings() as stages:
            response: Response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        duration_ms = round(elapsed_ms, 2)
        response.headers["X-Request-ID"] = req_id
        response.headers["Server-Timing"] = _server_timing(stages, elapsed_ms)

        session_id = request.headers.get("X-Session-ID")
        if not session_id and "/sessions/" in request.url.path:
            parts = request.url.path.split("/")
            try:
                idx = parts.index("sessions")
                if idx + 1 < len(parts) and parts[idx + 1]:
                    session_id = parts[idx + 1]
            except ValueError:
                pass

        logger.info(
            "request_completed method=%s path=%s status=%d duration_ms=%.2f "
            "request_id=%s session_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            req_id,
            session_id or "-",
        )
        return response

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

    @app.get(
        "/health",
        response_model=HealthStatusResponse,
        tags=["System"],
        summary="Estado de salud y operatividad del servicio",
        description=(
            "Verifica la conectividad con la base de datos, el acceso al ArtifactStore, "
            "el motor OMR activo y el dispositivo de cómputo efectivo (#40, D44)."
        ),
        responses={
            status.HTTP_200_OK: {"description": "Servicio saludable"},
            status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Servicio no operativo"},
        },
    )
    def get_health_endpoint(request: Request, db: DbDep) -> JSONResponse:
        db_status = "connected"
        try:
            db.execute(text("SELECT 1"))
        except Exception as err:
            logger.error("Health check db error: %s", err)
            db_status = "error"

        store_status = "accessible"
        store = request.app.state.artifact_store
        # Sin almacén inyectado, como en producción, cada petición crea uno sobre
        # `artifacts_dir` (get_artifact_store): esa es la carpeta que se comprueba.
        root = app_settings.artifacts_dir if store is None else getattr(store, "_root_dir", None)
        try:
            if root is not None:
                root_dir = Path(root)
                root_dir.mkdir(parents=True, exist_ok=True)
                # La API corre sin root (D57): la carpeta puede existir y no admitir escritura,
                # como un volumen de root sin migrar. Se mira también `sha256`, la primera
                # carpeta del almacén; las de prefijo, debajo, no se recorren en cada sondeo.
                for folder in (root_dir, root_dir / "sha256"):
                    if folder.exists() and not os.access(folder, os.W_OK | os.X_OK):
                        raise PermissionError(f"la API no puede escribir en {folder}")
        except Exception as err:
            logger.error("Health check artifact store error: %s", err)
            store_status = "error"

        engine = request.app.state.omr_engine
        engine_name = engine.engine_id
        try:
            device = getattr(engine, "device", None) or get_effective_device()
        except Exception:
            device = "cpu"

        is_healthy = db_status == "connected" and store_status == "accessible"
        status_str = "healthy" if is_healthy else "unhealthy"
        http_code = status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

        payload = {
            "status": status_str,
            "version": API_VERSION,
            "database": db_status,
            "artifact_store": store_status,
            "omr_engine": engine_name,
            "device": str(device),
        }
        return JSONResponse(status_code=http_code, content=payload)

    app.state.session_factory = session_factory
    app.state.settings = app_settings
    app.state.login_rate_limiter = LoginRateLimiter(
        max_attempts=app_settings.login_rate_limit_max_attempts,
        window_seconds=app_settings.login_rate_limit_window_seconds,
    )
    # El registro cuenta todos los intentos por IP, también los que acaban en 409 (ADR-0022).
    app.state.registration_rate_limiter = LoginRateLimiter(
        max_attempts=app_settings.registration_rate_limit_max_attempts,
        window_seconds=app_settings.registration_rate_limit_window_seconds,
        message="Demasiados registros desde esta conexión. Reintente en {retry_after} segundos.",
    )
    # Huecos de transcripción: los libera el cálculo al terminar, no la petición (ADR-0024).
    app.state.transcription_slots = TranscriptionSlots(app_settings.transcribe_max_concurrency)

    # HOMR es el único motor de producción (ADR-0018); las pruebas inyectan su doble.
    resolved_engine = (
        omr_engine
        if omr_engine is not None
        else HOMREngine(
            use_gpu=app_settings.omr_use_gpu,
            preprocessing=app_settings.build_preprocessing_config(),
        )
    )
    app.state.omr_engine = resolved_engine
    app.state.validator = ValidationEngine(
        list(rules) if rules is not None else get_default_rules()
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
    app.state.model_registry = model_registry
    # Capa de sugerencias: global, apagada por defecto y cargada al arrancar (ADR-0036 §8, §12).
    app.state.suggestion_model = (
        (
            suggestion_model
            if suggestion_model is not None
            else load_suggestion_model(session_factory, app_settings, artifact_store)
        )
        if app_settings.suggestions_enabled
        else None
    )
    # Estados materializados por (sesión, seq): el log no cambia (ADR-0007, ADR-0037).
    app.state.score_cache = (
        score_cache
        if score_cache is not None
        else InMemoryScoreStateCache(app_settings.score_cache_max_entries)
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

    @app.exception_handler(SuggestionNotFound)
    def suggestion_not_found_handler(request: Request, exc: SuggestionNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "suggestion not found"},
        )

    @app.exception_handler(StaleSuggestion)
    def stale_suggestion_handler(request: Request, exc: StaleSuggestion) -> JSONResponse:
        # La web la marca como antigua y ofrece revalidar (ADR-0036 §5).
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": StaleSuggestion.detail},
        )

    @app.exception_handler(SuggestionConflict)
    def suggestion_conflict_handler(request: Request, exc: SuggestionConflict) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": exc.message},
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

    def require_registration_enabled(request: Request) -> None:
        """Con el registro apagado, la ruta responde 404 antes de leer el cuerpo (ADR-0022)."""
        app_settings: Settings = request.app.state.settings
        if not app_settings.registration_enabled:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

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
            "y emite un token de acceso Bearer JWT (#40)."
        ),
        responses={
            # No es AUTH_401: aquí el 401 no es un token caducado, y el cliente no debe tratarlo
            # como el fin de una sesión (#143).
            status.HTTP_401_UNAUTHORIZED: {
                "model": ErrorDetail,
                "description": (
                    "Credenciales inválidas o cuenta desactivada: un usuario inexistente, una "
                    "contraseña incorrecta y una cuenta desactivada dan el mismo código y cuerpo"
                ),
            },
            status.HTTP_429_TOO_MANY_REQUESTS: {
                "model": ErrorDetail,
                "description": "Límite de intentos de autenticación superado",
            },
            **UNPROCESSABLE_422,
        },
    )
    def login(
        form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
        request: Request,
        db: DbDep,
    ) -> TokenResponse:
        """Autentica credenciales y emite un token JWT con rate limiting (#40)."""
        client_host = request.client.host if request.client else "unknown"
        # Ningún nombre válido pasa de 64 caracteres (users.username): con más, la clave del límite
        # crecería con lo que mande el cliente y se guardaría toda la ventana (revisión de #156).
        rate_key = f"{client_network_key(client_host)}:{form_data.username[:64]}"
        rate_limiter: LoginRateLimiter = request.app.state.login_rate_limiter
        # El intento se anota antes de comprobar las credenciales, de forma atómica: peticiones
        # simultáneas no pasan todas el límite. Si sale bien, se borra el historial.
        rate_limiter.hit(rate_key)

        user_repo = SqlAlchemyUserRepository(db)
        hasher: PasswordHasher = request.app.state.password_hasher
        token_serv: TokenService = request.app.state.token_service

        user = authenticate_use_case(
            form_data.username,
            form_data.password,
            user_repository=user_repo,
            password_hasher=hasher,
        )
        rate_limiter.reset(rate_key)
        token = token_serv.create_access_token(user_id=user.id, role=user.role)
        return TokenResponse(access_token=token, token_type="bearer")

    @app.post(
        "/auth/register",
        response_model=UserRead,
        status_code=status.HTTP_201_CREATED,
        tags=["Auth"],
        summary="Registro de una cuenta por la propia persona",
        description=(
            "Crea una cuenta de transcriptor activa y marcada como autorregistrada: puede "
            "iniciar sesión en el momento, y un investigador puede desactivarla con "
            "PATCH /users/{id} (ADR-0022, ADR-0025). Solo usuario y contraseña. Limitado por IP "
            "(red /64 en IPv6); si el registro está desactivado en la configuración, responde 404."
        ),
        responses={
            **NOT_FOUND_404,
            **CONFLICT_409,
            **RATE_LIMITED_429,
            **UNPROCESSABLE_422,
        },
        dependencies=[Depends(require_registration_enabled)],
    )
    def register(payload: RegisterRequest, request: Request, db: DbDep) -> UserRead:
        """Registra una cuenta activa de transcriptor (ADR-0022, ADR-0025)."""
        client_host = request.client.host if request.client else "unknown"
        rate_limiter: LoginRateLimiter = request.app.state.registration_rate_limiter
        # Todo intento que llega aquí cuenta, también el que acaba en 409: así no se pueden
        # sondear nombres ocupados sin límite. Comprobar y anotar es una sola operación.
        rate_limiter.hit(client_network_key(client_host))

        user = register_user_use_case(
            payload.username,
            payload.password,
            user_repository=SqlAlchemyUserRepository(db),
            password_hasher=request.app.state.password_hasher,
        )
        return UserRead.from_user(user)

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
        return UserRead.from_user(current_user)

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
        return [UserRead.from_user(u) for u in users]

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
        return UserRead.from_user(new_user)

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
        return UserRead.from_user(updated)

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
        responses={**AUTH_401, **UPLOAD_ERRORS, **UNPROCESSABLE_422, **TRANSCRIBE_BUSY_503},
    )
    async def transcribe(
        request: Request,
        db: DbDep,
        current_user: CurrentUserDep,
        file: Annotated[UploadFile, File()],
        condition: Annotated[
            str | None,
            Query(description="Condición experimental: 'assisted' o 'unassisted'"),
        ] = None,
        test_score_id: Annotated[
            str | None,
            Query(description="Identificador de la partitura de prueba"),
        ] = None,
        condition_form: Annotated[
            str | None,
            Form(alias="condition"),
        ] = None,
        test_score_id_form: Annotated[
            str | None,
            Form(alias="test_score_id"),
        ] = None,
    ) -> TranscribeResponse:
        app_settings: Settings = request.app.state.settings

        raw_condition = condition_form or condition or "assisted"
        effective_score_id = test_score_id_form or test_score_id
        try:
            effective_condition = normalize_condition(raw_condition)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

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

        artifact_store = get_artifact_store(request, db)

        # Resolver versión activa del modelo OMR si existe en el registry (#21)
        model_registry = getattr(
            request.app.state, "model_registry", None
        ) or SqlAlchemyModelRegistry(db)
        active_version = model_registry.active()
        effective_engine = request.app.state.omr_engine
        if active_version is not None and hasattr(type(effective_engine), "from_active_model"):
            preproc_config = getattr(effective_engine, "_preprocessing", None)
            effective_engine = type(effective_engine).from_active_model(
                model_registry,
                artifact_store,
                use_gpu=app_settings.omr_use_gpu,
                preprocessing=preproc_config,
            )

        upload_name = Path(file.filename or "upload.png").name
        factory: SessionFactory = request.app.state.session_factory

        # La transcripción usa su propia sesión de base de datos y su propio directorio temporal, y
        # confirma antes de devolver: si la petición se cancela (el cliente se va) mientras HOMR
        # calcula, el trabajo termina y se guarda igualmente, sin tocar una sesión ya cerrada
        # (ADR-0024). Con un 2xx, la sesión ya está confirmada (#166).
        def transcribe_and_commit() -> TranscribeResult:
            with (
                factory() as work_db,
                tempfile.TemporaryDirectory(prefix="cadenza-upload-") as work_dir,
            ):
                upload_path = Path(work_dir) / upload_name
                upload_path.write_bytes(content)
                outcome = transcribe_score_use_case(
                    upload_path,
                    omr_engine=effective_engine,
                    validator=request.app.state.validator,
                    session_repository=SqlAlchemySessionRepository(work_db),
                    current_user=current_user,
                    artifact_store=get_artifact_store(request, work_db),
                    condition=effective_condition,
                    test_score_id=effective_score_id,
                    suggestion_model=request.app.state.suggestion_model,
                )
                work_db.commit()
                return outcome

        # La sesión de la petición solo ha leído: se cierra su transacción para no retener una
        # conexión del pool, «idle in transaction» en PostgreSQL, mientras HOMR calcula.
        db.rollback()
        result = await run_in_transcription_slot(
            request.app.state.transcription_slots, transcribe_and_commit
        )

        return TranscribeResponse(
            session_id=result.session_id,
            document_id=result.document_id,
            omr_engine=result.omr_engine,
            findings_count=result.findings_count,
            condition=result.condition,
            test_score_id=result.test_score_id,
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
        condition: str | None = Query(
            default=None,
            description="Filtrar por condición experimental ('assisted' o 'unassisted')",
        ),
        test_score_id: str | None = Query(
            default=None, description="Filtrar por partitura de prueba"
        ),
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
            condition=condition,
            test_score_id=test_score_id,
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
                condition=s.condition,
                test_score_id=s.test_score_id,
                owner_id=s.owner_id,
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
            score_cache=request.app.state.score_cache,
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
        # El contrato por defecto no cambia; `fields=view` responde SessionViewRead, que se
        # declara en los componentes (custom_openapi) y en la descripción del parámetro.
        response_model=SessionDetailRead,
        tags=["Sessions"],
        summary="Detalle completo de sesión con estado materializado",
        description=(
            "Devuelve el ScoreDocument crudo, hallazgos, log de ediciones, "
            "current_score materializado y anchor_index enriquecido (ADR-0011). "
            "Con fields=view devuelve SessionViewRead: lo mismo sin document ni anchor_index, "
            "que no se calcula (#275, ADR-0037)."
        ),
        responses={**AUTH_401, **FORBIDDEN_403, **NOT_FOUND_404},
    )
    def get_session(
        session_id: str,
        request: Request,
        db: DbDep,
        current_user: CurrentUserDep,
        fields: Annotated[
            Literal["view"] | None,
            Query(
                description=(
                    "'view': solo lo que necesita la vista (SessionViewRead), sin document ni "
                    "anchor_index. Sin él, el detalle completo (SessionDetailRead)."
                )
            ),
        ] = None,
    ) -> Response:
        session_repo = SqlAlchemySessionRepository(db)
        edit_repo = SqlAlchemyEditEventRepository(db)
        view = fields == "view"
        detail = get_session_use_case(
            session_id,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=current_user,
            include_anchor_index=not view,
            score_cache=request.app.state.score_cache,
        )

        with timed_stage("serialize"):
            curr_score = (
                ScoreIRPayload.model_validate(detail.current_score)
                if detail.current_score is not None
                else None
            )
            common: dict[str, Any] = {
                "session_id": detail.session_id,
                "document_id": detail.document_id,
                "omr_engine": detail.omr_engine,
                "findings": [FindingRead.from_persisted(f) for f in detail.findings],
                "edits": [EditEventRead.from_edit(e, detail.session_id) for e in detail.edits],
                "current_score": curr_score,
                "current_seq": detail.current_seq,
                "image_artifact": detail.image_artifact,
                "model_version": detail.model_version,
                "status": detail.status,
                "condition": detail.condition,
                "test_score_id": detail.test_score_id,
                "owner_id": detail.owner_id,
            }
            body: BaseModel
            if view:
                body = SessionViewRead(**common)
            else:
                body = SessionDetailRead(
                    **common,
                    document=ScoreDocumentPayload.model_validate(detail.document),
                    anchor_index=(
                        AnchorIndexPayload.model_validate(detail.anchor_index)
                        if detail.anchor_index is not None
                        else None
                    ),
                )
        return _json_response(body)

    @app.get(
        "/sessions/{session_id}/timing",
        response_model=TimingMapRead,
        tags=["Sessions"],
        summary="Obtener mapa tiempo-ancla para reproducción sincronizada",
        description=(
            "Calcula y devuelve el mapa determinista de tiempos de inicio y duración "
            "en pulsos para cada evento musical de la sesión (#42, D12)."
        ),
        responses={**AUTH_401, **FORBIDDEN_403, **NOT_FOUND_404},
    )
    def get_session_timing(
        session_id: str,
        request: Request,
        db: DbDep,
        current_user: CurrentUserDep,
    ) -> Response:
        session_repo = SqlAlchemySessionRepository(db)
        edit_repo = SqlAlchemyEditEventRepository(db)
        timing_map = get_timing_use_case(
            session_id,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=current_user,
            score_cache=request.app.state.score_cache,
        )
        with timed_stage("serialize"):
            body = _timing_read(session_id, timing_map)
        return _json_response(body)

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
        "/sessions/{session_id}/suggestions/{suggestion_id}/reject",
        response_model=SuggestionRead,
        tags=["Validation"],
        summary="Rechazar una sugerencia de la capa",
        description=(
            "Guarda que la persona rechaza la sugerencia, con su autoría fijada por el "
            "servidor. 409 en una sesión finalizada o si ya se aplicó; rechazar una ya "
            "rechazada o de una validación anterior responde 200. No descarta el hallazgo "
            "(ADR-0036 §5)."
        ),
        responses={**AUTH_401, **FORBIDDEN_403, **NOT_FOUND_404, **CONFLICT_409},
    )
    def reject_suggestion_endpoint(
        session_id: str,
        suggestion_id: int,
        db: DbDep,
        current_user: CurrentUserDep,
    ) -> SuggestionRead:
        """Rechaza una sugerencia (ADR-0036 §5)."""
        rejected = reject_suggestion_use_case(
            session_id,
            suggestion_id,
            session_repository=SqlAlchemySessionRepository(db),
            current_user=current_user,
        )
        return SuggestionRead.from_persisted(rejected)

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
            suggestion_model=request.app.state.suggestion_model,
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
            "contra nuevas ediciones humanas (ADR-0014, #34). Valida como POST /validate: "
            "conserva los descartes de la validación vigente si su evento no cambió y "
            "devuelve solo los hallazgos activos; en una sesión no asistida no ejecuta las "
            "reglas y guarda los hallazgos vacíos. 409 si la sesión ya está finalizada "
            "(#187, ADR-0043)."
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
            suggestion_model=request.app.state.suggestion_model,
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
        response_model=EditAppliedRead,
        status_code=status.HTTP_201_CREATED,
        tags=["Edits"],
        summary="Añadir una edición inmutable al log",
        description=(
            "Añade una corrección humana validada contra el estado actual. "
            "Exige base_seq, verifica before y fija autor por el servidor (ADR-0011, ADR-0012). "
            "El 201 devuelve la edición y el estado que crea: current_seq, current_score, su "
            "MusicXML y su mapa de tiempos si cambia (#275, ADR-0037). Con suggestion_id "
            "aplica una sugerencia y la marca como aceptada; los errores van en este orden: "
            "409 de base_seq, 409 'stale_suggestion' y 422 si la edición no es la propuesta "
            "(ADR-0036 §5)."
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
        request: Request,
        db: DbDep,
        current_user: CurrentUserDep,
    ) -> Response:
        """Añade una edición inmutable al log de la sesión y devuelve el estado que crea."""
        session_repo = SqlAlchemySessionRepository(db)
        edit_repo = SqlAlchemyEditEventRepository(db)
        applied = append_edit_use_case(
            session_id,
            base_seq=payload.base_seq,
            anchor=payload.anchor.to_anchor(),
            op=payload.op,
            session_repository=session_repo,
            edit_repository=edit_repo,
            exporter=request.app.state.score_exporter,
            current_user=current_user,
            before=payload.before,
            after=payload.after,
            score_cache=request.app.state.score_cache,
            suggestion_id=payload.suggestion_id,
        )
        with timed_stage("serialize"):
            edit = EditEventRead.from_edit(applied.edit, session_id)
            body = EditAppliedRead(
                **edit.model_dump(),
                current_seq=applied.current_seq,
                current_score=ScoreIRPayload.model_validate(applied.current_score.to_primitive()),
                status=applied.status,
                musicxml=applied.musicxml,
                timing=(
                    _timing_read(session_id, applied.timing) if applied.timing is not None else None
                ),
            )
        return _json_response(body, status.HTTP_201_CREATED)

    @app.post(
        "/sessions/{session_id}/undo",
        response_model=UndoResponse,
        tags=["Edits"],
        summary="Deshacer la última edición activa en el servidor",
        description=(
            "Registra un evento compensatorio inverso de la última edición activa "
            "en el log append-only sin borrar historia (ADR-0007, #35). "
            "Devuelve el nuevo current_seq, el ID de la edición deshecha, "
            "la partitura materializada actualizada y su índice de anclas, y además su "
            "MusicXML y su mapa de tiempos si cambia (#275, ADR-0037)."
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
        request: Request,
        db: DbDep,
        current_user: CurrentUserDep,
        payload: UndoRequest | None = None,
    ) -> Response:
        session_repo = SqlAlchemySessionRepository(db)
        edit_repo = SqlAlchemyEditEventRepository(db)
        base_seq = payload.base_seq if payload is not None else None
        result = undo_edit_use_case(
            session_id,
            base_seq=base_seq,
            session_repository=session_repo,
            edit_repository=edit_repo,
            current_user=current_user,
            score_cache=request.app.state.score_cache,
            exporter=request.app.state.score_exporter,
        )
        with timed_stage("serialize"):
            curr_score = ScoreIRPayload.model_validate(result.current_score)
            anchor_idx = (
                AnchorIndexPayload.model_validate(result.anchor_index)
                if result.anchor_index is not None
                else None
            )
            body = UndoResponse(
                session_id=result.session_id,
                current_seq=result.current_seq,
                undone_edit_id=result.undone_edit_id,
                current_score=curr_score,
                anchor_index=anchor_idx,
                compensatory_edit_id=result.compensatory_edit.id,
                compensatory_edit=EditEventRead.from_edit(result.compensatory_edit, session_id),
                status=result.status,
                musicxml=result.musicxml,
                timing=(
                    _timing_read(session_id, result.timing) if result.timing is not None else None
                ),
            )
        return _json_response(body)

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
        # `GET /sessions/{id}?fields=view` (#275, ADR-0037): su esquema, para los clientes.
        schemas = components.setdefault("schemas", {})
        if "SessionViewRead" not in schemas:
            view_schema = SessionViewRead.model_json_schema(
                ref_template="#/components/schemas/{model}"
            )
            # Sus modelos anidados son los del detalle, ya en los componentes.
            for name, definition in view_schema.pop("$defs", {}).items():
                schemas.setdefault(name, definition)
            schemas["SessionViewRead"] = view_schema
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


def create_default_app(
    settings: Settings | None = None,
    *,
    model_registry: Any | None = None,
) -> FastAPI:
    """Factory para uvicorn: carga Settings tipada de entorno y conecta HOMR (ADR-0018)."""

    app_settings = settings or Settings()
    engine = create_engine_for_url(app_settings.database_url)
    # En producción no se crea el esquema al arrancar; se depende de las migraciones (#6).
    if app_settings.auto_create_schema or (
        app_settings.database_url.startswith("sqlite") and ":memory:" in app_settings.database_url
    ):
        create_schema(engine)

    return create_app(
        create_session_factory(engine),
        settings=app_settings,
        model_registry=model_registry,
    )
