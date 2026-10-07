"""Pruebas E2E de gestión de cuentas y usuarios en la API (ADR-0012, #46)."""

from __future__ import annotations

from cadenza.api import Settings, create_app
from cadenza.api.cli import create_initial_investigator
from cadenza.application import Role, User
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi.testclient import TestClient


def _setup_app_and_tokens() -> tuple[TestClient, str, str, str, str]:
    """Crea app de prueba con un investigador y un transcriptor precargados."""
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)
    settings = Settings(auth_secret_key="test-jwt-signing-key-minimum-32-bytes-long")
    app = create_app(session_factory, settings=settings)

    hasher = app.state.password_hasher
    token_serv = app.state.token_service

    inv_pass_hash = hasher.hash("inv_password_123")
    trans_pass_hash = hasher.hash("trans_password_123")

    with session_factory() as db:
        user_repo = SqlAlchemyUserRepository(db)
        inv = user_repo.add(
            User(
                id="inv-id-1",
                username="investigator_boss",
                password_hash=inv_pass_hash,
                role=Role.INVESTIGADOR,
                active=True,
            )
        )
        trans = user_repo.add(
            User(
                id="trans-id-1",
                username="transcriptor_pepe",
                password_hash=trans_pass_hash,
                role=Role.TRANSCRIPTOR,
                active=True,
            )
        )
        db.commit()

    inv_token = token_serv.create_access_token(user_id=inv.id, role=inv.role)
    trans_token = token_serv.create_access_token(user_id=trans.id, role=trans.role)
    client = TestClient(app)

    return client, inv_token, trans_token, inv.id, trans.id


def test_create_user_as_investigator_succeeds() -> None:
    client, inv_token, _, _, _ = _setup_app_and_tokens()

    payload = {
        "username": "new_user_1",
        "password": "valid_secret_pass",
        "role": "transcriptor",
    }
    response = client.post(
        "/users",
        json=payload,
        headers={"Authorization": f"Bearer {inv_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "new_user_1"
    assert data["role"] == "transcriptor"
    assert data["active"] is True
    assert "password_hash" not in data


def test_create_user_forbidden_for_transcriptor() -> None:
    client, _, trans_token, _, _ = _setup_app_and_tokens()

    payload = {
        "username": "illegal_user",
        "password": "valid_secret_pass",
        "role": "transcriptor",
    }
    response = client.post(
        "/users",
        json=payload,
        headers={"Authorization": f"Bearer {trans_token}"},
    )
    assert response.status_code == 403


def test_create_user_short_password_rejected() -> None:
    client, inv_token, _, _, _ = _setup_app_and_tokens()

    payload = {
        "username": "shorty",
        "password": "123",
        "role": "transcriptor",
    }
    response = client.post(
        "/users",
        json=payload,
        headers={"Authorization": f"Bearer {inv_token}"},
    )
    assert response.status_code == 422


def test_create_user_duplicate_username_returns_409() -> None:
    client, inv_token, _, _, _ = _setup_app_and_tokens()

    payload = {
        "username": "transcriptor_pepe",
        "password": "valid_secret_pass",
        "role": "transcriptor",
    }
    response = client.post(
        "/users",
        json=payload,
        headers={"Authorization": f"Bearer {inv_token}"},
    )
    assert response.status_code == 409


def test_list_users_as_investigator() -> None:
    client, inv_token, _, inv_id, trans_id = _setup_app_and_tokens()

    response = client.get(
        "/users",
        headers={"Authorization": f"Bearer {inv_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    ids = [u["id"] for u in data]
    assert inv_id in ids and trans_id in ids
    for u in data:
        assert "password_hash" not in u


def test_list_users_forbidden_for_transcriptor() -> None:
    client, _, trans_token, _, _ = _setup_app_and_tokens()

    response = client.get(
        "/users",
        headers={"Authorization": f"Bearer {trans_token}"},
    )
    assert response.status_code == 403


def test_change_password_endpoint_flow() -> None:
    client, _, trans_token, _, _ = _setup_app_and_tokens()

    # Intento con contraseña actual errónea -> 401
    bad_res = client.post(
        "/auth/password",
        json={"current_password": "wrong_password", "new_password": "brand_new_password_8"},
        headers={"Authorization": f"Bearer {trans_token}"},
    )
    assert bad_res.status_code == 401

    # Cambio exitoso
    ok_res = client.post(
        "/auth/password",
        json={"current_password": "trans_password_123", "new_password": "brand_new_password_8"},
        headers={"Authorization": f"Bearer {trans_token}"},
    )
    assert ok_res.status_code == 200
    assert ok_res.json()["status"] == "success"

    # Verificar que puede iniciar sesión con la nueva contraseña
    login_res = client.post(
        "/auth/login",
        data={"username": "transcriptor_pepe", "password": "brand_new_password_8"},
    )
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()


def test_patch_user_reset_password_and_deactivate() -> None:
    client, inv_token, _, _, trans_id = _setup_app_and_tokens()

    patch_res = client.patch(
        f"/users/{trans_id}",
        json={"password": "reset_password_99", "active": False},
        headers={"Authorization": f"Bearer {inv_token}"},
    )
    assert patch_res.status_code == 200
    data = patch_res.json()
    assert data["active"] is False


def test_deactivated_account_with_valid_token_returns_401() -> None:
    client, inv_token, trans_token, _, trans_id = _setup_app_and_tokens()

    # Con token válido accede a /auth/me
    before_res = client.get("/auth/me", headers={"Authorization": f"Bearer {trans_token}"})
    assert before_res.status_code == 200

    # Investigador desactiva la cuenta
    client.patch(
        f"/users/{trans_id}",
        json={"active": False},
        headers={"Authorization": f"Bearer {inv_token}"},
    )

    # Ahora el token existente de transcriptor es rechazado de inmediato
    after_res = client.get("/auth/me", headers={"Authorization": f"Bearer {trans_token}"})
    assert after_res.status_code == 401


def test_patch_user_unknown_id_returns_404() -> None:
    client, inv_token, _, _, _ = _setup_app_and_tokens()

    patch_res = client.patch(
        "/users/non-existent-user-id",
        json={"active": False},
        headers={"Authorization": f"Bearer {inv_token}"},
    )
    assert patch_res.status_code == 404


def test_cli_create_initial_investigator() -> None:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        auth_secret_key="test-jwt-signing-key-minimum-32-bytes-long",
    )
    user = create_initial_investigator("chief_investigator", "super_secret_99", settings)
    assert user.username == "chief_investigator"
    assert user.role == Role.INVESTIGADOR
    assert user.active is True
