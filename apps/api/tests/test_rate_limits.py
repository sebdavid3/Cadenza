"""Límite de intentos del inicio de sesión ante un despliegue público (revisión de #156)."""

from __future__ import annotations

import secrets
import threading

import pytest
from cadenza.api import Argon2PasswordHasher, Settings, create_app
from cadenza.api.security import LoginRateLimiter
from cadenza.application import Role, User
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

SECRET = secrets.token_hex(32)


def _app(max_attempts: int = 2, *, password: str | None = None) -> FastAPI:
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)
    if password is not None:
        with session_factory() as db:
            SqlAlchemyUserRepository(db).add(
                User(
                    id="usr-alice",
                    username="alice",
                    password_hash=Argon2PasswordHasher().hash(password),
                    role=Role.TRANSCRIPTOR,
                    active=True,
                )
            )
            db.commit()
    settings = Settings(auth_secret_key=SECRET, login_rate_limit_max_attempts=max_attempts)
    return create_app(session_factory, settings=settings)


def _login(client: TestClient, username: str = "nadie", password: str | None = None) -> int:
    form = {"username": username, "password": password or secrets.token_urlsafe(12)}
    code: int = client.post("/auth/login", data=form).status_code
    return code


def test_login_limit_groups_ipv6_addresses_of_the_same_64() -> None:
    app = _app(max_attempts=2)
    first = TestClient(app, client=("2001:db8:1:2::1", 50000))
    same_64 = TestClient(app, client=("2001:db8:1:2::abcd", 50000))
    other_64 = TestClient(app, client=("2001:db8:1:3::1", 50000))

    assert _login(first) == 401
    assert _login(same_64) == 401
    assert _login(first) == 429
    assert _login(same_64) == 429
    assert _login(other_64) == 401


def test_successful_login_clears_the_failures_of_its_key() -> None:
    password = secrets.token_urlsafe(12)
    client = TestClient(_app(max_attempts=3, password=password))

    assert _login(client, "alice") == 401
    assert _login(client, "alice") == 401
    assert _login(client, "alice", password) == 200
    # Sin el borrado, el siguiente fallo sería el tercero y el cuarto intento daría 429.
    assert _login(client, "alice") == 401
    assert _login(client, "alice") == 401
    assert _login(client, "alice", password) == 200


def test_login_rate_key_does_not_grow_with_the_username() -> None:
    app = _app(max_attempts=5)
    client = TestClient(app)

    for n in range(3):
        assert _login(client, f"{n}" + "x" * 100_000) == 401

    limiter: LoginRateLimiter = app.state.login_rate_limiter
    # La IP del cliente de prueba, «:» y como mucho los 64 caracteres de un nombre válido.
    assert max(len(key) for key in limiter._failures) <= len("testclient:") + 64


def test_rate_limiter_hit_is_atomic_under_concurrency() -> None:
    limiter = LoginRateLimiter(max_attempts=3, window_seconds=300)
    barrier = threading.Barrier(20)
    allowed: list[bool] = []
    lock = threading.Lock()

    def attempt() -> None:
        barrier.wait()
        try:
            limiter.hit("misma-clave")
            ok = True
        except HTTPException as exc:
            assert exc.status_code == 429
            ok = False
        with lock:
            allowed.append(ok)

    threads = [threading.Thread(target=attempt) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert allowed.count(True) == 3
    assert allowed.count(False) == 17


def test_rate_limiter_purges_with_amortized_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    class SmallLimiter(LoginRateLimiter):
        _PURGE_THRESHOLD = 4

    now = [1000.0]
    monkeypatch.setattr("cadenza.api.security.time.time", lambda: now[0])
    limiter = SmallLimiter(max_attempts=5, window_seconds=60)

    for n in range(4):
        limiter.record_failure(f"k{n}")
    # Cuatro claves vigentes: la purga no quita ninguna y el umbral pasa al doble.
    limiter.record_failure("k4")
    assert len(limiter._failures) == 5
    assert limiter._next_purge == 8

    # Hasta llegar a 8 claves no se vuelve a recorrer el diccionario.
    limiter.record_failure("k5")
    limiter.record_failure("k6")
    assert limiter._next_purge == 8

    # Vencida la ventana, la purga quita las antiguas y el umbral vuelve al mínimo.
    now[0] += 120
    limiter.record_failure("k7")
    limiter.record_failure("k8")
    assert set(limiter._failures) == {"k7", "k8"}
    assert limiter._next_purge == 4
