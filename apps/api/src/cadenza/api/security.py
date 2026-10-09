"""Adaptadores de seguridad para FastAPI: Argon2id y JWT (ADR-0012, #44)."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta

import argon2
import argon2.exceptions
import jwt
from cadenza.application import NotAuthenticated, PasswordHasher, Role, TokenPayload, TokenService
from fastapi import HTTPException, status


class Argon2PasswordHasher(PasswordHasher):
    """Adaptador de hashing seguro de contraseñas usando Argon2id (ADR-0012)."""

    def __init__(self) -> None:
        self._hasher = argon2.PasswordHasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (
            argon2.exceptions.VerifyMismatchError,
            argon2.exceptions.VerificationError,
            argon2.exceptions.InvalidHashError,
        ):
            return False


class JwtTokenService(TokenService):
    """Adaptador de emisión y verificación de tokens de acceso JWT (ADR-0012)."""

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        default_expire_minutes: int = 30,
    ) -> None:
        if not secret_key:
            raise ValueError("secret_key no puede estar vacía")
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._default_expire_minutes = default_expire_minutes

    def create_access_token(
        self,
        user_id: str,
        role: Role,
        expires_in_seconds: int | None = None,
    ) -> str:
        now = datetime.now(UTC)
        if expires_in_seconds is not None:
            exp = now + timedelta(seconds=expires_in_seconds)
        else:
            exp = now + timedelta(minutes=self._default_expire_minutes)

        payload = {
            "sub": user_id,
            "role": role.value,
            "exp": int(exp.timestamp()),
            "iat": int(now.timestamp()),
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def decode_token(self, token: str) -> TokenPayload:
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[self._algorithm])
            user_id = str(payload.get("sub", ""))
            role_str = str(payload.get("role", ""))
            exp_int = payload.get("exp")
            if not user_id or not role_str:
                raise NotAuthenticated("Token inválido")
            exp = datetime.fromtimestamp(exp_int, tz=UTC) if exp_int else None
            return TokenPayload(sub=user_id, role=Role(role_str), exp=exp)
        except jwt.ExpiredSignatureError as err:
            raise NotAuthenticated("Token caducado") from err
        except (jwt.PyJWTError, ValueError) as err:
            raise NotAuthenticated("Token inválido") from err


class LoginRateLimiter:
    """Control en memoria de intentos fallidos de inicio de sesión (#40)."""

    def __init__(self, max_attempts: int = 5, window_seconds: int = 300) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        """Verifica si la clave ha superado el límite de intentos permitidos."""
        if self.max_attempts <= 0:
            return
        now = time.time()
        with self._lock:
            failures = [t for t in self._failures.get(key, []) if now - t < self.window_seconds]
            self._failures[key] = failures
            if len(failures) >= self.max_attempts:
                oldest = failures[0]
                retry_after = max(1, int(self.window_seconds - (now - oldest)))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Demasiados intentos fallidos. Reintente en {retry_after} segundos.",
                    headers={"Retry-After": str(retry_after)},
                )

    def record_failure(self, key: str) -> None:
        """Registra un intento fallido para la clave especificada."""
        if self.max_attempts <= 0:
            return
        now = time.time()
        with self._lock:
            failures = [t for t in self._failures.get(key, []) if now - t < self.window_seconds]
            failures.append(now)
            self._failures[key] = failures

    def reset(self, key: str) -> None:
        """Limpia el historial de fallos tras un inicio de sesión exitoso."""
        with self._lock:
            self._failures.pop(key, None)
