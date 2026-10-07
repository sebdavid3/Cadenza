"""Configuración tipada del plano online de Cadenza (ADR-0005, #8, #44)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

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
