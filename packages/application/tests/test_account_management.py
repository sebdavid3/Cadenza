"""Pruebas unitarias para los casos de uso de gestión de cuentas (ADR-0012, #46)."""

from __future__ import annotations

import pytest
from cadenza.application import (
    DuplicateUsername,
    Forbidden,
    InMemoryPasswordHasher,
    InMemoryUserRepository,
    NotAuthenticated,
    Role,
    User,
    UserNotFound,
    WeakPassword,
    change_password,
    create_user,
    list_users,
    update_user,
)


def _make_investigator(user_id: str = "inv-1", username: str = "investigator") -> User:
    return User(
        id=user_id,
        username=username,
        password_hash="mock-hash:secret123",
        role=Role.INVESTIGADOR,
        active=True,
    )


def _make_transcriptor(user_id: str = "trans-1", username: str = "transcriptor") -> User:
    return User(
        id=user_id,
        username=username,
        password_hash="mock-hash:secret123",
        role=Role.TRANSCRIPTOR,
        active=True,
    )


def test_create_user_success_as_investigator() -> None:
    repo = InMemoryUserRepository()
    hasher = InMemoryPasswordHasher()
    investigator = _make_investigator()

    created = create_user(
        username="newbie",
        password="valid_password_123",
        role=Role.TRANSCRIPTOR,
        current_user=investigator,
        user_repository=repo,
        password_hasher=hasher,
    )

    assert created.username == "newbie"
    assert created.role == Role.TRANSCRIPTOR
    assert created.active is True
    assert created.password_hash == "mock-hash:valid_password_123"

    saved = repo.get(created.id)
    assert saved is not None
    assert saved.username == "newbie"


def test_create_user_forbidden_for_non_investigator() -> None:
    repo = InMemoryUserRepository()
    hasher = InMemoryPasswordHasher()
    transcriptor = _make_transcriptor()

    with pytest.raises(Forbidden, match="investigador"):
        create_user(
            username="newbie",
            password="valid_password_123",
            role=Role.TRANSCRIPTOR,
            current_user=transcriptor,
            user_repository=repo,
            password_hasher=hasher,
        )


def test_create_user_rejects_short_password() -> None:
    repo = InMemoryUserRepository()
    hasher = InMemoryPasswordHasher()
    investigator = _make_investigator()

    with pytest.raises(WeakPassword):
        create_user(
            username="newbie",
            password="short",
            role=Role.TRANSCRIPTOR,
            current_user=investigator,
            user_repository=repo,
            password_hasher=hasher,
        )


def test_create_user_rejects_duplicate_username() -> None:
    investigator = _make_investigator()
    repo = InMemoryUserRepository([investigator])
    hasher = InMemoryPasswordHasher()

    with pytest.raises(DuplicateUsername):
        create_user(
            username=investigator.username,
            password="valid_password_123",
            role=Role.TRANSCRIPTOR,
            current_user=investigator,
            user_repository=repo,
            password_hasher=hasher,
        )


def test_update_user_reset_password_and_deactivate() -> None:
    investigator = _make_investigator()
    transcriptor = _make_transcriptor()
    repo = InMemoryUserRepository([investigator, transcriptor])
    hasher = InMemoryPasswordHasher()

    updated = update_user(
        transcriptor.id,
        current_user=investigator,
        active=False,
        new_password="new_strong_password",
        user_repository=repo,
        password_hasher=hasher,
    )

    assert updated.active is False
    assert updated.password_hash == "mock-hash:new_strong_password"

    saved = repo.get(transcriptor.id)
    assert saved is not None
    assert saved.active is False
    assert saved.password_hash == "mock-hash:new_strong_password"


def test_update_user_forbidden_for_transcriptor() -> None:
    investigator = _make_investigator()
    transcriptor = _make_transcriptor()
    repo = InMemoryUserRepository([investigator, transcriptor])
    hasher = InMemoryPasswordHasher()

    with pytest.raises(Forbidden):
        update_user(
            investigator.id,
            current_user=transcriptor,
            active=False,
            user_repository=repo,
            password_hasher=hasher,
        )


def test_update_user_unknown_user_raises_not_found() -> None:
    investigator = _make_investigator()
    repo = InMemoryUserRepository([investigator])
    hasher = InMemoryPasswordHasher()

    with pytest.raises(UserNotFound):
        update_user(
            "unknown-id",
            current_user=investigator,
            active=False,
            user_repository=repo,
            password_hasher=hasher,
        )


def test_change_password_success() -> None:
    transcriptor = _make_transcriptor()
    repo = InMemoryUserRepository([transcriptor])
    hasher = InMemoryPasswordHasher()

    updated = change_password(
        current_password="secret123",
        new_password="brand_new_password",
        current_user=transcriptor,
        user_repository=repo,
        password_hasher=hasher,
    )

    assert updated.password_hash == "mock-hash:brand_new_password"
    saved = repo.get(transcriptor.id)
    assert saved is not None
    assert saved.password_hash == "mock-hash:brand_new_password"


def test_change_password_invalid_current_password() -> None:
    transcriptor = _make_transcriptor()
    repo = InMemoryUserRepository([transcriptor])
    hasher = InMemoryPasswordHasher()

    with pytest.raises(NotAuthenticated, match="actual es incorrecta"):
        change_password(
            current_password="wrong_password",
            new_password="brand_new_password",
            current_user=transcriptor,
            user_repository=repo,
            password_hasher=hasher,
        )


def test_change_password_short_new_password() -> None:
    transcriptor = _make_transcriptor()
    repo = InMemoryUserRepository([transcriptor])
    hasher = InMemoryPasswordHasher()

    with pytest.raises(WeakPassword):
        change_password(
            current_password="secret123",
            new_password="123",
            current_user=transcriptor,
            user_repository=repo,
            password_hasher=hasher,
        )


def test_list_users_success_as_investigator() -> None:
    investigator = _make_investigator()
    transcriptor = _make_transcriptor()
    repo = InMemoryUserRepository([investigator, transcriptor])

    users = list_users(current_user=investigator, user_repository=repo)
    assert len(users) == 2
    assert {u.id for u in users} == {investigator.id, transcriptor.id}


def test_list_users_forbidden_for_transcriptor() -> None:
    investigator = _make_investigator()
    transcriptor = _make_transcriptor()
    repo = InMemoryUserRepository([investigator, transcriptor])

    with pytest.raises(Forbidden):
        list_users(current_user=transcriptor, user_repository=repo)
