"""Configuración tipada del plano online de Cadenza (ADR-0005, ADR-0018, #8, #44)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Origen web tal como lo envía el navegador: esquema://host[:puerto], sin ruta.
_ORIGIN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^/\s?#]+")


class Settings(BaseSettings):
    """Configuración de la API gobernada por variables de entorno CADENZA_*."""

    model_config = SettingsConfigDict(
        env_prefix="CADENZA_",
        case_sensitive=False,
    )

    database_url: str = Field(
        default="sqlite+pysqlite:///./cadenza.db",
        description="URL de conexión SQLAlchemy para la base de datos.",
    )
    omr_use_gpu: bool = Field(
        default=False,
        description="Indica si HOMR debe intentar usar GPU (CUDA/ROCm).",
    )
    artifacts_dir: Path = Field(
        default=Path("./data/artifacts"),
        description="Directorio raíz para el almacenamiento de artefactos (ArtifactStore).",
    )
    auth_secret_key: str = Field(
        default="",
        description="Clave secreta obligatoria para la firma de tokens JWT (ADR-0012).",
    )
    auth_token_expire_minutes: int = Field(
        default=30,
        description="Tiempo de validez de los tokens de acceso en minutos (ADR-0012).",
    )
    max_upload_size_bytes: int = Field(
        default=20 * 1024 * 1024,
        description=(
            "Tamaño máximo permitido para la subida de imágenes en bytes " "(20 MB por defecto)."
        ),
    )
    auto_create_schema: bool = Field(
        default=False,
        description=(
            "Si es True, crea el esquema DDL al arrancar (solo para desarrollo/tests). "
            "En producción permanece en False, dependiendo de migraciones Alembic (#6)."
        ),
    )
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["*"],
        description=(
            "Orígenes permitidos para peticiones CORS (CADENZA_CORS_ORIGINS): `*` o "
            "`esquema://host[:puerto]`, uno o varios separados por comas o en una lista JSON. "
            "Una lista vacía desactiva CORS."
        ),
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: Any) -> Any:
        """Admite en la variable de entorno texto separado por comas además de JSON (#123)."""

        if not isinstance(value, str):
            return value
        text = value.strip()
        if text.startswith("["):
            return json.loads(text)
        return [origin.strip() for origin in text.split(",") if origin.strip()]

    @field_validator("cors_origins")
    @classmethod
    def _check_cors_origins(cls, origins: list[str]) -> list[str]:
        """Rechaza al arrancar los orígenes que el navegador nunca enviaría (#123).

        Un origen es `esquema://host[:puerto]`, sin ruta ni barra final; `*` va solo, porque
        junto a otros orígenes CORS los ignoraría y permitiría cualquiera.
        """

        if "*" in origins and len(origins) > 1:
            raise ValueError("'*' no se combina con otros orígenes en CADENZA_CORS_ORIGINS")
        for origin in origins:
            if origin != "*" and not _ORIGIN_RE.fullmatch(origin):
                raise ValueError(
                    f"origen CORS no válido: {origin!r} (forma esperada: "
                    "esquema://host[:puerto], sin ruta ni barra final)"
                )
        return origins

    @model_validator(mode="after")
    def _registration_needs_closed_cors(self) -> Settings:
        """Con el registro abierto, CORS no puede ser `*` (ADR-0022).

        Si lo fuera, cualquier web podría registrar cuentas desde el navegador de sus visitantes,
        repartiendo el límite por IP entre todas sus direcciones.
        """

        if self.registration_enabled and "*" in self.cors_origins:
            raise ValueError(
                "CADENZA_REGISTRATION_ENABLED exige CADENZA_CORS_ORIGINS con el origen público "
                "de la interfaz, no '*'"
            )
        return self

    login_rate_limit_max_attempts: int = Field(
        default=5,
        description="Máximo de intentos fallidos antes de bloquear temporalmente el login (#40).",
    )
    login_rate_limit_window_seconds: int = Field(
        default=300,
        description="Ventana de tiempo en segundos para el límite de intentos de login (#40).",
    )
    registration_enabled: bool = Field(
        default=False,
        description=(
            "Abre POST /auth/register (ADR-0022). Apagado, la ruta responde 404 "
            "como si no existiera."
        ),
    )
    registration_rate_limit_max_attempts: int = Field(
        default=5,
        ge=1,
        description=(
            "Intentos de registro por IP (o red /64 en IPv6) en la ventana, también los que acaban "
            "en 409 (ADR-0022)."
        ),
    )
    registration_rate_limit_window_seconds: int = Field(
        default=3600,
        ge=1,
        description="Ventana en segundos del límite de intentos de registro por IP (ADR-0022).",
    )
    registration_max_pending: int = Field(
        default=50,
        ge=1,
        description=(
            "Cuentas autorregistradas pendientes de activación a partir de las cuales el registro "
            "responde 503 hasta que un investigador revise las que hay (ADR-0022)."
        ),
    )
    omr_preprocess_enabled: bool = Field(
        default=False,
        description="Indica si se activa el pipeline de preprocesado de imagen antes de OMR.",
    )
    omr_preprocess_deskew: bool = Field(
        default=False,
        description="Activa el enderezado automático (deskew) de pentagramas.",
    )
    omr_preprocess_binarize: bool = Field(
        default=False,
        description="Activa la binarización (umbralización Otsu o adaptativa).",
    )
    omr_preprocess_rescale: bool = Field(
        default=False,
        description="Activa el control de resolución / escalado de imagen.",
    )
    omr_preprocess_target_dpi: int = Field(
        default=300,
        description=(
            "DPI objetivo para el control de resolución cuando "
            "omr_preprocess_rescale está activo."
        ),
    )
    disable_power_throttling: bool = Field(
        default=True,
        description=(
            "Si es True, solicita desactivar la limitación de energía (EcoQoS/Power Throttling) "
            "del proceso en Windows al arrancar (#106)."
        ),
    )

    def build_preprocessing_config(self) -> Any | None:
        """Construye un PreprocessingConfig si el preprocesado está habilitado."""
        if not self.omr_preprocess_enabled:
            return None
        from cadenza.omr import PreprocessingConfig

        return PreprocessingConfig(
            enabled=True,
            deskew=self.omr_preprocess_deskew,
            binarize=self.omr_preprocess_binarize,
            rescale=self.omr_preprocess_rescale,
            target_dpi=self.omr_preprocess_target_dpi,
        )
