"""Adaptadores de seguridad para FastAPI: Argon2id y JWT (ADR-0012, #44)."""

from __future__ import annotations

import ipaddress
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


def client_network_key(host: str) -> str:
    """Clave del límite por IP: la dirección IPv4, o la red /64 de una IPv6.

    Un mismo cliente IPv6 suele disponer de todo un /64; contar por dirección dejaría esquivar el
    límite rotando direcciones (ADR-0022).
    """

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


class LoginRateLimiter:
    """Control en memoria de intentos por clave en una ventana de tiempo (#40, ADR-0022).

    El inicio de sesión y el registro anotan cada intento con `hit`, que comprueba y anota bajo el
    mismo cerrojo; el inicio de sesión borra el historial de su clave con `reset` si sale bien, de
    modo que en la práctica solo cuentan los fallos.
    """

    # A partir de este número de claves se purgan las que ya no tienen intentos en la ventana. El
    # umbral siguiente se fija en el doble de las que sobreviven, para que purgar cueste O(1)
    # amortizado aunque alguien cree claves sin parar (revisión de #156).
    _PURGE_THRESHOLD = 10_000

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 300,
        *,
        message: str = "Demasiados intentos fallidos. Reintente en {retry_after} segundos.",
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.message = message
        self._failures: dict[str, list[float]] = {}
        self._next_purge = self._PURGE_THRESHOLD
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        failures = [t for t in self._failures.get(key, []) if now - t < self.window_seconds]
        if failures:
            self._failures[key] = failures
        else:
            self._failures.pop(key, None)
        return failures

    def _purge(self, now: float) -> None:
        if len(self._failures) < self._next_purge:
            return
        for key in list(self._failures):
            self._recent(key, now)
        self._next_purge = max(self._PURGE_THRESHOLD, 2 * len(self._failures))

    def _raise_limited(self, failures: list[float], now: float) -> None:
        retry_after = max(1, int(self.window_seconds - (now - failures[0])))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=self.message.format(retry_after=retry_after),
            headers={"Retry-After": str(retry_after)},
        )

    def hit(self, key: str) -> None:
        """Anota un intento y lanza 429 si ya se había alcanzado el límite, de forma atómica."""
        if self.max_attempts <= 0:
            return
        now = time.time()
        with self._lock:
            self._purge(now)
            failures = self._recent(key, now)
            if len(failures) >= self.max_attempts:
                self._raise_limited(failures, now)
            failures.append(now)
            self._failures[key] = failures

    def check(self, key: str) -> None:
        """Verifica si la clave ha superado el límite de intentos permitidos."""
        if self.max_attempts <= 0:
            return
        now = time.time()
        with self._lock:
            failures = self._recent(key, now)
            if len(failures) >= self.max_attempts:
                self._raise_limited(failures, now)

    def record_failure(self, key: str) -> None:
        """Registra un intento fallido para la clave especificada."""
        if self.max_attempts <= 0:
            return
        now = time.time()
        with self._lock:
            self._purge(now)
            failures = self._recent(key, now)
            failures.append(now)
            self._failures[key] = failures

    def reset(self, key: str) -> None:
        """Limpia el historial de fallos tras un inicio de sesión exitoso."""
        with self._lock:
            self._failures.pop(key, None)
