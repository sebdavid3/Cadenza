"""Puertos y dobles en memoria de seguridad: hashing de contraseñas y tokens (ADR-0012, #44)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ..exceptions import NotAuthenticated
from ..user import Role


class PasswordHasher(ABC):
    """Puerto para el cálculo y verificación de hashes seguros de contraseñas."""

    @abstractmethod
    def hash(self, password: str) -> str:
        """Calcula el hash seguro de una contraseña en texto plano."""

    @abstractmethod
    def verify(self, password: str, password_hash: str) -> bool:
        """Verifica si una contraseña en texto plano coincide con su hash."""


@dataclass(frozen=True)
class TokenPayload:
    """Contenido verificado de un token de acceso."""

    sub: str
    role: Role
    exp: datetime | None = None


class TokenService(ABC):
    """Puerto para la emisión y verificación de tokens de acceso."""

    @abstractmethod
    def create_access_token(
        self,
        user_id: str,
        role: Role,
        expires_in_seconds: int | None = None,
    ) -> str:
        """Emite un token de acceso firmado para el usuario y rol dados."""

    @abstractmethod
    def decode_token(self, token: str) -> TokenPayload:
        """Decodifica y valida un token. Lanza NotAuthenticated si es inválido o caducó."""


class InMemoryPasswordHasher(PasswordHasher):
    """Doble determinista en memoria para pruebas desacopladas de Argon2id."""

    def hash(self, password: str) -> str:
        return f"mock-hash:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == f"mock-hash:{password}"


class InMemoryTokenService(TokenService):
    """Doble determinista en memoria para pruebas de emisión y decodificación de tokens."""

    def __init__(self, default_expire_seconds: int = 1800) -> None:
        self._default_expire_seconds = default_expire_seconds

    def create_access_token(
        self,
        user_id: str,
        role: Role,
        expires_in_seconds: int | None = None,
    ) -> str:
        seconds = (
            expires_in_seconds if expires_in_seconds is not None else self._default_expire_seconds
        )
        exp_timestamp = int((datetime.now(UTC) + timedelta(seconds=seconds)).timestamp())
        return f"mock-token:{user_id}:{role.value}:{exp_timestamp}"

    def decode_token(self, token: str) -> TokenPayload:
        if not token.startswith("mock-token:"):
            raise NotAuthenticated("Token inválido")
        parts = token.split(":")
        if len(parts) != 4:
            raise NotAuthenticated("Token inválido")
        _, user_id, role_str, exp_str = parts
        try:
            role = Role(role_str)
            exp_timestamp = int(exp_str)
        except (ValueError, TypeError) as err:
            raise NotAuthenticated("Token inválido") from err

        exp_time = datetime.fromtimestamp(exp_timestamp, tz=UTC)
        if datetime.now(UTC) > exp_time:
            raise NotAuthenticated("Token caducado")

        return TokenPayload(sub=user_id, role=role, exp=exp_time)
