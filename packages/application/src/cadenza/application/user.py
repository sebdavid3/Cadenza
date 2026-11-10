"""Modelos de usuario y roles en la capa de aplicación (ADR-0012, #43)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Role(StrEnum):
    """Rol de usuario en el sistema según ADR-0012."""

    TRANSCRIPTOR = "transcriptor"
    INVESTIGADOR = "investigador"


@dataclass(frozen=True)
class User:
    """Entidad de usuario en la capa de aplicación."""

    id: str
    username: str
    password_hash: str
    role: Role
    active: bool = True
    created_at: datetime | None = None
    # Cuenta creada desde el registro público (ADR-0022): queda fuera del estudio.
    self_registered: bool = False
    # Permiso de uso de los datos (#378, ADR-0064): cuándo se dio y qué versión del texto se
    # leyó; los dos None, sin permiso. Solo se guarda: usarlo será otro issue.
    data_consent_at: datetime | None = None
    data_consent_version: str | None = None
