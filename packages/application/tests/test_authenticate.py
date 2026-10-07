"""Pruebas del caso de uso authenticate y puertos de seguridad en memoria (ADR-0012, #44)."""

from __future__ import annotations

import pytest
from cadenza.application import (
    InMemoryPasswordHasher,
    InMemoryTokenService,
    InMemoryUserRepository,
    NotAuthenticated,
    Role,
    User,
    authenticate,
)


@pytest.fixture
def user_repo() -> InMemoryUserRepository:
    repo = InMemoryUserRepository()
    hasher = InMemoryPasswordHasher()
    # Usuario activo
    repo.add(
        User(
            id="usr-1",
            username="alice",
            password_hash=hasher.hash("secret123"),
            role=Role.TRANSCRIPTOR,
            active=True,
        )
    )
    # Usuario inactivo
    repo.add(
        User(
            id="usr-2",
            username="bob",
            password_hash=hasher.hash("secret456"),
            role=Role.INVESTIGADOR,
            active=False,
        )
    )
    return repo


@pytest.fixture
def password_hasher() -> InMemoryPasswordHasher:
    return InMemoryPasswordHasher()


def test_authenticate_success(
    user_repo: InMemoryUserRepository,
    password_hasher: InMemoryPasswordHasher,
) -> None:
    user = authenticate(
        "alice",
        "secret123",
        user_repository=user_repo,
        password_hasher=password_hasher,
    )
    assert user.id == "usr-1"
    assert user.username == "alice"
    assert user.role == Role.TRANSCRIPTOR


def test_authenticate_wrong_password_raises_not_authenticated(
    user_repo: InMemoryUserRepository,
    password_hasher: InMemoryPasswordHasher,
) -> None:
    with pytest.raises(NotAuthenticated) as exc_info:
        authenticate(
            "alice",
            "wrong_password",
            user_repository=user_repo,
            password_hasher=password_hasher,
        )
    assert exc_info.value.message == "Credenciales inválidas"


def test_authenticate_unknown_user_raises_not_authenticated(
    user_repo: InMemoryUserRepository,
    password_hasher: InMemoryPasswordHasher,
) -> None:
    with pytest.raises(NotAuthenticated) as exc_info:
        authenticate(
            "charlie",
            "any_password",
            user_repository=user_repo,
            password_hasher=password_hasher,
        )
    assert exc_info.value.message == "Credenciales inválidas"


def test_authenticate_inactive_user_raises_not_authenticated(
    user_repo: InMemoryUserRepository,
    password_hasher: InMemoryPasswordHasher,
) -> None:
    with pytest.raises(NotAuthenticated) as exc_info:
        authenticate(
            "bob",
            "secret456",
            user_repository=user_repo,
            password_hasher=password_hasher,
        )
    assert exc_info.value.message == "Credenciales inválidas"


def test_in_memory_token_service_roundtrip() -> None:
    token_service = InMemoryTokenService(default_expire_seconds=60)
    token = token_service.create_access_token(user_id="usr-1", role=Role.TRANSCRIPTOR)

    payload = token_service.decode_token(token)
    assert payload.sub == "usr-1"
    assert payload.role == Role.TRANSCRIPTOR


def test_in_memory_token_service_expired_raises_not_authenticated() -> None:
    # Expiración con 0 segundos o negativa
    token_service = InMemoryTokenService(default_expire_seconds=0)
    token = token_service.create_access_token(
        user_id="usr-1",
        role=Role.INVESTIGADOR,
        expires_in_seconds=-1,
    )

    with pytest.raises(NotAuthenticated) as exc_info:
        token_service.decode_token(token)
    assert "caducado" in exc_info.value.message.lower()


def test_in_memory_token_service_invalid_format_raises_not_authenticated() -> None:
    token_service = InMemoryTokenService()

    with pytest.raises(NotAuthenticated) as exc_info:
        token_service.decode_token("invalid-token-string")
    assert "inválido" in exc_info.value.message.lower()
