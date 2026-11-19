"""Pruebas de autenticación: adaptadores Argon2/JWT y endpoints /auth/* (ADR-0012, #44)."""

from __future__ import annotations

import secrets
import time
from dataclasses import replace

import jwt
import pytest
from cadenza.api import Argon2PasswordHasher, JwtTokenService, Settings, create_app
from cadenza.application import NotAuthenticated, User
from cadenza.persistence import (
    SessionFactory,
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi.testclient import TestClient

PASS_ALICE = "valid-alice-pass"
PASS_BOB = "valid-bob-pass"
JWT_TEST_KEY = "test-jwt-signing-key-minimum-32-bytes-long"


def _form_credentials(username: str, pwd: str) -> dict[str, str]:
    return {"username": username, "password": pwd}


def test_argon2_password_hasher() -> None:
    hasher = Argon2PasswordHasher()
    hashed = hasher.hash("plain-text-pass")
    assert hashed != "plain-text-pass"
    assert hashed.startswith("$argon2")

    assert hasher.verify("plain-text-pass", hashed) is True
    assert hasher.verify("wrong-pass", hashed) is False
    assert hasher.verify("plain-text-pass", "invalid_hash_string") is False


def test_argon2_dummy_hash_uses_the_real_parameters_and_matches_no_password() -> None:
    """El hash de relleno del login (#226, ADR-0042) cuesta lo mismo que uno real."""
    hasher = Argon2PasswordHasher()
    real = hasher.hash(secrets.token_urlsafe(16))
    dummy = hasher.dummy_hash()

    # Mismo algoritmo, versión y parámetros (m, t, p): verificarlo cuesta lo mismo.
    assert dummy.rsplit("$", 2)[0] == real.rsplit("$", 2)[0]
    assert dummy.startswith("$argon2id$")
    # Se calcula una vez por adaptador.
    assert hasher.dummy_hash() is dummy
    assert hasher.verify(secrets.token_urlsafe(16), dummy) is False
    assert hasher.verify("", dummy) is False


def test_jwt_token_service() -> None:
    service = JwtTokenService(secret_key=JWT_TEST_KEY, default_expire_minutes=30)
    token = service.create_access_token(user_id="usr-123")

    payload = service.decode_token(token)
    assert payload.sub == "usr-123"
    assert payload.exp is not None

    # Token caducado
    expired_token = service.create_access_token(user_id="usr-123", expires_in_seconds=-10)
    with pytest.raises(NotAuthenticated) as exc_info:
        service.decode_token(expired_token)
    assert "caducado" in exc_info.value.message.lower()

    # Token manipulado
    with pytest.raises(NotAuthenticated) as exc_info:
        service.decode_token(token + "manipulated")
    assert "inválido" in exc_info.value.message.lower()

    # Clave de firma vacía
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
                password_hash=hasher.hash(PASS_ALICE),
                active=True,
            )
        )
        # Usuario inactivo
        user_repo.add(
            User(
                id="usr-bob",
                username="bob",
                password_hash=hasher.hash(PASS_BOB),
                active=False,
            )
        )
        db.commit()

    settings = Settings(
        auth_secret_key=JWT_TEST_KEY,
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
        data=_form_credentials("alice", PASS_ALICE),
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["access_token"]


def test_login_wrong_password_returns_401(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/auth/login",
        data=_form_credentials("alice", "wrong-password-entry"),
    )
    assert response.status_code == 401
    data = response.json()
    assert data["detail"] == "Credenciales inválidas"
    assert "wrong-password-entry" not in response.text


def test_login_unknown_user_returns_401(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/auth/login",
        data=_form_credentials("unknown_user", "any-password-entry"),
    )
    assert response.status_code == 401
    data = response.json()
    assert data["detail"] == "Credenciales inválidas"
    assert "unknown_user" not in data["detail"]


def test_login_inactive_user_returns_401(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/auth/login",
        data=_form_credentials("bob", PASS_BOB),
    )
    assert response.status_code == 401
    data = response.json()
    assert data["detail"] == "Credenciales inválidas"


def test_login_401_cases_are_indistinguishable(auth_client: TestClient) -> None:
    """Mismo código, cuerpo y cabeceras de autenticación en los tres casos (#143, #226)."""
    wrong = secrets.token_urlsafe(16)
    responses = [
        auth_client.post("/auth/login", data=_form_credentials(user, pwd))
        for user, pwd in (("nadie", wrong), ("alice", wrong), ("bob", PASS_BOB))
    ]

    assert {r.status_code for r in responses} == {401}
    assert len({r.content for r in responses}) == 1
    assert responses[0].json() == {"detail": "Credenciales inválidas"}
    assert {r.headers.get("www-authenticate") for r in responses} == {"Bearer"}


def test_get_me_success(auth_client: TestClient) -> None:
    # 1. Login para obtener token
    login_res = auth_client.post(
        "/auth/login",
        data=_form_credentials("alice", PASS_ALICE),
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
    assert "role" not in data
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
        secret_key=JWT_TEST_KEY,
        default_expire_minutes=30,
    )
    expired_token = service.create_access_token(
        user_id="usr-alice",
        expires_in_seconds=-60,
    )

    response = auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    data = response.json()
    assert "Token inválido o expirado" in data["detail"]


def test_get_me_accepts_a_token_issued_with_a_role(auth_client: TestClient) -> None:
    """Un token emitido antes de ADR-0070, con `role`, vale hasta que caduque."""
    now = int(time.time())
    old_token = jwt.encode(
        {"sub": "usr-alice", "role": "investigador", "exp": now + 600, "iat": now},
        JWT_TEST_KEY,
        algorithm="HS256",
    )

    response = auth_client.get("/auth/me", headers={"Authorization": f"Bearer {old_token}"})

    assert response.status_code == 200
    assert response.json()["id"] == "usr-alice"


def test_get_me_token_without_subject_returns_401(auth_client: TestClient) -> None:
    now = int(time.time())
    for claims in ({"exp": now + 600}, {"sub": "", "exp": now + 600}):
        token = jwt.encode(claims, JWT_TEST_KEY, algorithm="HS256")
        response = auth_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


def _client_and_factory() -> tuple[TestClient, SessionFactory, str]:
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)
    hasher = Argon2PasswordHasher()
    password = secrets.token_urlsafe(16)
    with session_factory() as db:
        SqlAlchemyUserRepository(db).add(
            User(id="usr-carol", username="carol", password_hash=hasher.hash(password))
        )
        db.commit()
    app = create_app(
        session_factory,
        settings=Settings(auth_secret_key=JWT_TEST_KEY),
        password_hasher=hasher,
    )
    return TestClient(app), session_factory, password


def test_deactivated_account_with_valid_token_returns_401() -> None:
    """Desactivar una cuenta en la base (ADR-0070) deja sin efecto su token al momento."""
    client, session_factory, password = _client_and_factory()
    token = client.post("/auth/login", data=_form_credentials("carol", password)).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/auth/me", headers=headers).status_code == 200

    with session_factory() as db:
        repo = SqlAlchemyUserRepository(db)
        account = repo.get("usr-carol")
        assert account is not None
        repo.update(replace(account, active=False))
        db.commit()

    assert client.get("/auth/me", headers=headers).status_code == 401


def test_change_password_endpoint_flow() -> None:
    client, _, password = _client_and_factory()
    token = client.post("/auth/login", data=_form_credentials("carol", password)).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {token}"}
    new_password = secrets.token_urlsafe(16)

    wrong = client.post(
        "/auth/password",
        json={"current_password": secrets.token_urlsafe(16), "new_password": new_password},
        headers=headers,
    )
    assert wrong.status_code == 401

    changed = client.post(
        "/auth/password",
        json={"current_password": password, "new_password": new_password},
        headers=headers,
    )
    assert changed.status_code == 200
    assert changed.json()["status"] == "success"

    login = client.post("/auth/login", data=_form_credentials("carol", new_password))
    assert login.status_code == 200
    assert client.post("/auth/login", data=_form_credentials("carol", password)).status_code == 401


def test_openapi_documents_oauth2_login(auth_client: TestClient) -> None:
    response = auth_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/auth/login" in schema["paths"]
    assert "/auth/me" in schema["paths"]
    login_op = schema["paths"]["/auth/login"]["post"]
    assert "requestBody" in login_op
