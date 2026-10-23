"""Pruebas del caso de uso register_user: registro abierto (ADR-0022, ADR-0025, #169)."""

from __future__ import annotations

import secrets

import pytest
from cadenza.application import (
    DuplicateUsername,
    InMemoryPasswordHasher,
    InMemoryUserRepository,
    Role,
    WeakPassword,
    authenticate,
    register_user,
)

# Contraseñas generadas en cada ejecución: ninguna prueba depende de su valor.
PASSWORD = secrets.token_urlsafe(12)
OTHER_PASSWORD = secrets.token_urlsafe(12)


def test_register_user_creates_an_active_self_registered_transcriptor() -> None:
    repo = InMemoryUserRepository()
    hasher = InMemoryPasswordHasher()

    user = register_user(
        "ana", PASSWORD, user_repository=repo, password_hasher=hasher, user_id="u-1"
    )

    assert user.id == "u-1"
    assert user.role is Role.TRANSCRIPTOR
    assert user.active is True
    assert user.self_registered is True
    assert user.password_hash != PASSWORD
    assert repo.get_by_username("ana") == user


def test_registered_user_can_authenticate_right_away() -> None:
    repo = InMemoryUserRepository()
    hasher = InMemoryPasswordHasher()
    created = register_user("ana", PASSWORD, user_repository=repo, password_hasher=hasher)

    assert authenticate("ana", PASSWORD, user_repository=repo, password_hasher=hasher) == created


def test_register_user_rejects_short_passwords_and_taken_usernames() -> None:
    repo = InMemoryUserRepository()
    hasher = InMemoryPasswordHasher()
    register_user("ana", PASSWORD, user_repository=repo, password_hasher=hasher)

    with pytest.raises(WeakPassword):
        register_user("luis", PASSWORD[:5], user_repository=repo, password_hasher=hasher)
    with pytest.raises(DuplicateUsername):
        register_user("ana", OTHER_PASSWORD, user_repository=repo, password_hasher=hasher)
