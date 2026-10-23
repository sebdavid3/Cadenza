"""Pruebas del caso de uso register_user: registro con activación (ADR-0022, #154)."""

from __future__ import annotations

import pytest
from cadenza.application import (
    DuplicateUsername,
    InMemoryPasswordHasher,
    InMemoryUserRepository,
    NotAuthenticated,
    Role,
    WeakPassword,
    authenticate,
    register_user,
)


def test_register_user_creates_an_inactive_self_registered_transcriptor() -> None:
    repo = InMemoryUserRepository()
    hasher = InMemoryPasswordHasher()

    user = register_user(
        "ana", "clave_larga_1", user_repository=repo, password_hasher=hasher, user_id="u-1"
    )

    assert user.id == "u-1"
    assert user.role is Role.TRANSCRIPTOR
    assert user.active is False
    assert user.self_registered is True
    assert user.password_hash != "clave_larga_1"
    assert repo.get_by_username("ana") == user


def test_registered_user_cannot_authenticate_until_activated() -> None:
    repo = InMemoryUserRepository()
    hasher = InMemoryPasswordHasher()
    register_user("ana", "clave_larga_1", user_repository=repo, password_hasher=hasher)

    with pytest.raises(NotAuthenticated):
        authenticate("ana", "clave_larga_1", user_repository=repo, password_hasher=hasher)


def test_register_user_rejects_short_passwords_and_taken_usernames() -> None:
    repo = InMemoryUserRepository()
    hasher = InMemoryPasswordHasher()
    register_user("ana", "clave_larga_1", user_repository=repo, password_hasher=hasher)

    with pytest.raises(WeakPassword):
        register_user("luis", "corta", user_repository=repo, password_hasher=hasher)
    with pytest.raises(DuplicateUsername):
        register_user("ana", "otra_clave_2", user_repository=repo, password_hasher=hasher)
