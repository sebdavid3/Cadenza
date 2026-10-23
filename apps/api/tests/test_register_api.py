"""Registro de cuentas por los propios usuarios (ADR-0022, #154)."""

from __future__ import annotations

from cadenza.api import Settings, create_app
from cadenza.application import Role, User
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

SECRET = "test-jwt-signing-key-minimum-32-bytes-long"


def _client(
    *, enabled: bool = True, max_attempts: int = 5, window_seconds: int = 3600
) -> tuple[TestClient, FastAPI]:
    engine = create_memory_engine()
    create_schema(engine)
    settings = Settings(
        auth_secret_key=SECRET,
        registration_enabled=enabled,
        registration_rate_limit_max_attempts=max_attempts,
        registration_rate_limit_window_seconds=window_seconds,
    )
    app = create_app(create_session_factory(engine), settings=settings)
    return TestClient(app), app


def _add_investigator(app: FastAPI) -> str:
    """Investigadora con token, para activar cuentas con PATCH /users/{id}."""
    state = app.state
    with state.session_factory() as db:
        user = SqlAlchemyUserRepository(db).add(
            User(
                id="inv-1",
                username="investigadora",
                password_hash=state.password_hasher.hash("inv_password_123"),
                role=Role.INVESTIGADOR,
            )
        )
        db.commit()
    token: str = state.token_service.create_access_token(user_id=user.id, role=user.role)
    return token


def test_register_creates_an_inactive_self_registered_transcriptor() -> None:
    client, _app = _client()

    response = client.post("/auth/register", json={"username": "ana", "password": "clave_larga_1"})

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "ana"
    assert body["role"] == "transcriptor"
    assert body["active"] is False
    assert body["self_registered"] is True
    assert "password" not in body and "password_hash" not in body


def test_self_registered_account_cannot_log_in_until_activated() -> None:
    client, app = _client()
    created = client.post("/auth/register", json={"username": "ana", "password": "clave_larga_1"})
    form = {"username": "ana", "password": "clave_larga_1"}

    # Igual que unas credenciales incorrectas: no revela si la cuenta existe.
    assert client.post("/auth/login", data=form).status_code == 401

    token = _add_investigator(app)
    activated = client.patch(
        f"/users/{created.json()['id']}",
        json={"active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert activated.status_code == 200
    assert activated.json()["self_registered"] is True
    assert client.post("/auth/login", data=form).status_code == 200


def test_register_rejects_a_taken_username() -> None:
    client, _app = _client()
    client.post("/auth/register", json={"username": "ana", "password": "clave_larga_1"})

    response = client.post("/auth/register", json={"username": "ana", "password": "otra_clave_2"})

    assert response.status_code == 409


def test_register_validates_the_payload_and_forbids_choosing_a_role() -> None:
    client, _app = _client()

    short = client.post("/auth/register", json={"username": "ana", "password": "corta"})
    empty = client.post("/auth/register", json={"username": "", "password": "clave_larga_1"})
    role = client.post(
        "/auth/register",
        json={"username": "ana", "password": "clave_larga_1", "role": "investigador"},
    )

    assert short.status_code == 422
    assert empty.status_code == 422
    assert role.status_code == 422
    assert role.json()["detail"][0]["type"] == "extra_forbidden"


def test_register_limits_attempts_per_ip_including_failed_ones() -> None:
    client, _app = _client(max_attempts=2, window_seconds=600)
    client.post("/auth/register", json={"username": "a1", "password": "clave_larga_1"})
    client.post("/auth/register", json={"username": "a1", "password": "clave_larga_1"})  # 409

    response = client.post("/auth/register", json={"username": "a2", "password": "clave_larga_1"})

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0


def test_register_is_not_found_when_disabled() -> None:
    client, _app = _client(enabled=False)

    response = client.post("/auth/register", json={"username": "ana", "password": "clave_larga_1"})

    assert response.status_code == 404


def test_accounts_created_by_an_investigator_are_not_self_registered() -> None:
    client, app = _client()
    token = _add_investigator(app)

    created = client.post(
        "/users",
        json={"username": "participante_07", "password": "clave_larga_1", "role": "transcriptor"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert created.status_code == 201
    assert created.json()["self_registered"] is False
    assert created.json()["active"] is True
