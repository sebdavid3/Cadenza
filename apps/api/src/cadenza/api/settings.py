"""Configuración tipada del plano online de Cadenza (ADR-0005, #8, #44)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    omr_engine: Literal["fake", "homr"] = Field(
        default="fake",
        description="Motor OMR seleccionado para inferencia ('fake' o 'homr').",
    )
    omr_use_gpu: bool = Field(
        default=False,
        description="Indica si el motor OMR debe intentar usar GPU (CUDA/ROCm).",
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
