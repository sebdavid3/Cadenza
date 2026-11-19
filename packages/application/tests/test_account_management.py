"""Pruebas unitarias del cambio de contraseña de la propia cuenta (ADR-0012, #46)."""

from __future__ import annotations

import pytest
from cadenza.application import (
    InMemoryPasswordHasher,
    InMemoryUserRepository,
    NotAuthenticated,
    User,
    WeakPassword,
    change_password,
)


def _make_user(user_id: str = "user-1", username: str = "ana") -> User:
    return User(
        id=user_id,
        username=username,
        password_hash="mock-hash:secret123",
        active=True,
    )


def test_change_password_success() -> None:
    user = _make_user()
    repo = InMemoryUserRepository([user])
    hasher = InMemoryPasswordHasher()

    updated = change_password(
        current_password="secret123",
        new_password="brand_new_password",
        current_user=user,
        user_repository=repo,
        password_hasher=hasher,
    )

    assert updated.password_hash == "mock-hash:brand_new_password"
    saved = repo.get(user.id)
    assert saved is not None
    assert saved.password_hash == "mock-hash:brand_new_password"


def test_change_password_invalid_current_password() -> None:
    user = _make_user()
    repo = InMemoryUserRepository([user])
    hasher = InMemoryPasswordHasher()

    with pytest.raises(NotAuthenticated, match="actual es incorrecta"):
        change_password(
            current_password="wrong_password",
            new_password="brand_new_password",
            current_user=user,
            user_repository=repo,
            password_hasher=hasher,
        )


def test_change_password_short_new_password() -> None:
    user = _make_user()
    repo = InMemoryUserRepository([user])
    hasher = InMemoryPasswordHasher()

    with pytest.raises(WeakPassword):
        change_password(
            current_password="secret123",
            new_password="123",
            current_user=user,
            user_repository=repo,
            password_hasher=hasher,
        )
