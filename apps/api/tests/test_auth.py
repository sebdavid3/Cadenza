"""Pruebas de autenticación: adaptadores Argon2/JWT y endpoints /auth/* (ADR-0012, #44)."""

from __future__ import annotations

import pytest
from cadenza.api import Argon2PasswordHasher, JwtTokenService, Settings, create_app
from cadenza.application import NotAuthenticated, Role, User
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi.testclient import TestClient


def test_argon2_password_hasher() -> None:
    hasher = Argon2PasswordHasher()
    hashed = hasher.hash("my_secret_password")
    assert hashed != "my_secret_password"
    assert hashed.startswith("$argon2")

    assert hasher.verify("my_secret_password", hashed) is True
    assert hasher.verify("wrong_password", hashed) is False
    assert hasher.verify("my_secret_password", "invalid_hash_string") is False


def test_jwt_token_service() -> None:
    service = JwtTokenService(
        secret_key="my-super-secret-key-32-bytes-long!", default_expire_minutes=30
    )
    token = service.create_access_token(user_id="usr-123", role=Role.TRANSCRIPTOR)

    payload = service.decode_token(token)
    assert payload.sub == "usr-123"
    assert payload.role == Role.TRANSCRIPTOR
    assert payload.exp is not None

    # Token caducado
    expired_token = service.create_access_token(
        user_id="usr-123", role=Role.TRANSCRIPTOR, expires_in_seconds=-10
    )
    with pytest.raises(NotAuthenticated) as exc_info:
        service.decode_token(expired_token)
    assert "caducado" in exc_info.value.message.lower()

    # Token manipulado
    with pytest.raises(NotAuthenticated) as exc_info:
        service.decode_token(token + "manipulated")
    assert "inválido" in exc_info.value.message.lower()

    # Clave secreta vacía
    with pytest.raises(ValueError, match="secret_key no puede estar vacía"):
        JwtTokenService(secret_key="")


@pytest.fixture
def auth_client() -> TestClient:
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)
    hasher = Argon2PasswordHasher()

    with session_factory() as db:
        user_repo = SqlAlchemyUserRepository(db)
        # Usuario activo
        user_repo.add(
            User(
                id="usr-alice",
                username="alice",
                password_hash=hasher.hash("secret_alice"),
                role=Role.TRANSCRIPTOR,
                active=True,
            )
        )
        # Usuario inactivo
        user_repo.add(
            User(
                id="usr-bob",
                username="bob",
                password_hash=hasher.hash("secret_bob"),
                role=Role.INVESTIGADOR,
                active=False,
            )
        )
        db.commit()

    settings = Settings(
        auth_secret_key="integration-test-secret-key-12345678",
        auth_token_expire_minutes=30,
    )
    app = create_app(
        session_factory,
        settings=settings,
        password_hasher=hasher,
    )
    return TestClient(app)


def test_login_success(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/auth/login",
        data={"username": "alice", "password": "secret_alice"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["access_token"]


def test_login_wrong_password_returns_401(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/auth/login",
        data={"username": "alice", "password": "wrong_password"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["detail"] == "Credenciales inválidas"
    assert "wrong_password" not in response.text


def test_login_unknown_user_returns_401(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/auth/login",
        data={"username": "unknown_user", "password": "any_password"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["detail"] == "Credenciales inválidas"
    assert "unknown_user" not in data["detail"]


def test_login_inactive_user_returns_401(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/auth/login",
        data={"username": "bob", "password": "secret_bob"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["detail"] == "Credenciales inválidas"


def test_get_me_success(auth_client: TestClient) -> None:
    # 1. Login para obtener token
    login_res = auth_client.post(
        "/auth/login",
        data={"username": "alice", "password": "secret_alice"},
    )
    token = login_res.json()["access_token"]

    # 2. Consultar perfil con token
    response = auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "usr-alice"
    assert data["username"] == "alice"
    assert data["role"] == "transcriptor"
    assert data["active"] is True
    assert "password" not in data
    assert "password_hash" not in data


def test_get_me_without_token_returns_401(auth_client: TestClient) -> None:
    response = auth_client.get("/auth/me")
    assert response.status_code == 401


def test_get_me_tampered_token_returns_401(auth_client: TestClient) -> None:
    response = auth_client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid_or_manipulated_token"},
    )
    assert response.status_code == 401
    data = response.json()
    assert "Token inválido o expirado" in data["detail"]


def test_get_me_expired_token_returns_401(auth_client: TestClient) -> None:
    service = JwtTokenService(
        secret_key="integration-test-secret-key-12345678",
        default_expire_minutes=30,
    )
    expired_token = service.create_access_token(
        user_id="usr-alice",
        role=Role.TRANSCRIPTOR,
        expires_in_seconds=-60,
    )

    response = auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    data = response.json()
    assert "Token inválido o expirado" in data["detail"]


def test_openapi_documents_oauth2_login(auth_client: TestClient) -> None:
    response = auth_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/auth/login" in schema["paths"]
    assert "/auth/me" in schema["paths"]
    login_op = schema["paths"]["/auth/login"]["post"]
    assert "requestBody" in login_op
