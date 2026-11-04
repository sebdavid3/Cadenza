"""Registro de cuentas por los propios usuarios (ADR-0022, #154)."""

from __future__ import annotations

import secrets

import pytest
from cadenza.api import Settings, create_app
from cadenza.api.security import LoginRateLimiter, client_network_key
from cadenza.application import Role, User
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

SECRET = "test-jwt-signing-key-minimum-32-bytes-long"
ORIGIN = "https://cadenza.test"
# Contraseñas generadas en cada ejecución: ninguna prueba depende de su valor.
PASSWORD = secrets.token_urlsafe(12)
OTHER_PASSWORD = secrets.token_urlsafe(12)
SHORT_PASSWORD = PASSWORD[:5]
INV_PASSWORD = secrets.token_urlsafe(12)


def _app(
    *,
    enabled: bool = True,
    max_attempts: int = 5,
    window_seconds: int = 3600,
) -> FastAPI:
    engine = create_memory_engine()
    create_schema(engine)
    settings = Settings(
        auth_secret_key=SECRET,
        cors_origins=[ORIGIN],
        registration_enabled=enabled,
        registration_rate_limit_max_attempts=max_attempts,
        registration_rate_limit_window_seconds=window_seconds,
    )
    return create_app(create_session_factory(engine), settings=settings)


def _client(
    *,
    enabled: bool = True,
    max_attempts: int = 5,
    window_seconds: int = 3600,
) -> tuple[TestClient, FastAPI]:
    app = _app(enabled=enabled, max_attempts=max_attempts, window_seconds=window_seconds)
    return TestClient(app), app


def _add_investigator(app: FastAPI) -> str:
    """Investigadora con token, para activar cuentas con PATCH /users/{id}."""
    state = app.state
    with state.session_factory() as db:
        user = SqlAlchemyUserRepository(db).add(
            User(
                id="inv-1",
                username="investigadora",
                password_hash=state.password_hasher.hash(INV_PASSWORD),
                role=Role.INVESTIGADOR,
            )
        )
        db.commit()
    token: str = state.token_service.create_access_token(user_id=user.id, role=user.role)
    return token


def _register(client: TestClient, username: str, password: str = PASSWORD) -> int:
    response = client.post("/auth/register", json={"username": username, "password": password})
    code: int = response.status_code
    return code


def test_register_creates_an_active_self_registered_transcriptor() -> None:
    client, _app = _client()

    response = client.post("/auth/register", json={"username": "ana", "password": PASSWORD})

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "ana"
    assert body["role"] == "transcriptor"
    assert body["active"] is True
    assert body["self_registered"] is True
    assert "password" not in body and "password_hash" not in body


def test_self_registered_account_logs_in_right_away_until_deactivated() -> None:
    client, app = _client()
    created = client.post("/auth/register", json={"username": "ana", "password": PASSWORD})
    form = {"username": "ana", "password": PASSWORD}

    assert client.post("/auth/login", data=form).status_code == 200

    # Un investigador puede desactivarla (moderación): entonces no entra, como con unas
    # credenciales incorrectas.
    token = _add_investigator(app)
    deactivated = client.patch(
        f"/users/{created.json()['id']}",
        json={"active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["self_registered"] is True
    assert client.post("/auth/login", data=form).status_code == 401


def test_register_rejects_a_taken_username() -> None:
    client, _app = _client()
    _register(client, "ana")

    assert _register(client, "ana", OTHER_PASSWORD) == 409


@pytest.mark.parametrize(
    "username",
    ["ab", " ", "Ana", "ana ", "a\nb", "\u200badmin", "investigadora\u00a0", "a\u00f1o", "_ana"],
)
def test_register_only_accepts_unambiguous_usernames(username: str) -> None:
    client, _app = _client()

    assert _register(client, username) == 422


def test_register_validates_the_payload_and_forbids_choosing_a_role() -> None:
    client, _app = _client()

    short = client.post("/auth/register", json={"username": "ana", "password": SHORT_PASSWORD})
    role = client.post(
        "/auth/register",
        json={"username": "ana", "password": PASSWORD, "role": "investigador"},
    )

    assert short.status_code == 422
    assert role.status_code == 422
    assert role.json()["detail"][0]["type"] == "extra_forbidden"


def test_register_limits_attempts_per_ip_including_taken_names() -> None:
    client, _app = _client(max_attempts=2, window_seconds=600)
    _register(client, "aaa1")
    _register(client, "aaa1")  # 409: también cuenta

    response = client.post("/auth/register", json={"username": "aaa2", "password": PASSWORD})

    assert response.status_code == 429
    assert 0 < int(response.headers["Retry-After"]) <= 600
    assert "registros" in response.json()["detail"]


def test_register_limit_is_per_ip() -> None:
    app = _app(max_attempts=1)
    first = TestClient(app, client=("203.0.113.1", 50000))
    second = TestClient(app, client=("203.0.113.2", 50000))

    assert _register(first, "aaa1") == 201
    assert _register(first, "aaa2") == 429
    assert _register(second, "aaa3") == 201


@pytest.mark.parametrize(
    "body",
    [
        {"username": "ana", "password": PASSWORD},
        {"username": "ana", "password": SHORT_PASSWORD},
        {"username": "ana", "password": PASSWORD, "role": "investigador"},
    ],
)
def test_register_is_not_found_when_disabled_whatever_the_body(body: dict[str, str]) -> None:
    client, _app = _client(enabled=False)

    assert client.post("/auth/register", json=body).status_code == 404


def test_registration_requires_a_closed_cors_policy() -> None:
    with pytest.raises(ValidationError, match="CADENZA_CORS_ORIGINS"):
        Settings(auth_secret_key=SECRET, registration_enabled=True, cors_origins=["*"])

    assert Settings(auth_secret_key=SECRET, registration_enabled=True, cors_origins=[ORIGIN])


def test_accounts_created_by_an_investigator_are_not_self_registered() -> None:
    client, app = _client()
    token = _add_investigator(app)

    created = client.post(
        "/users",
        json={"username": "participante_07", "password": PASSWORD, "role": "transcriptor"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert created.status_code == 201
    assert created.json()["self_registered"] is False
    assert created.json()["active"] is True


def test_rate_limiter_hit_checks_and_records_atomically() -> None:
    limiter = LoginRateLimiter(max_attempts=2, window_seconds=60, message="espera {retry_after}")
    limiter.hit("k")
    limiter.hit("k")

    with pytest.raises(HTTPException) as excinfo:
        limiter.hit("k")

    assert excinfo.value.status_code == 429
    assert str(excinfo.value.detail).startswith("espera ")
    limiter.hit("otra")  # otra clave no se ve afectada


def test_client_network_key_groups_ipv6_by_64() -> None:
    assert client_network_key("2001:db8:1:2:aaaa::1") == client_network_key("2001:db8:1:2:bbbb::9")
    assert client_network_key("2001:db8:1:2::1") != client_network_key("2001:db8:1:3::1")
    assert client_network_key("203.0.113.7") == "203.0.113.7"
    assert client_network_key("::ffff:203.0.113.7") == "203.0.113.7"
    assert client_network_key("testclient") == "testclient"
