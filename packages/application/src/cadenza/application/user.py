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
