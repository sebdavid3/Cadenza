"""Permiso de uso de los datos al registrarse y desde «Tu cuenta» (#378, ADR-0065).

El permiso solo se guarda: cuándo se dio y qué versión del texto se leyó. Usarlo para incluir
datos será otro issue.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

import pytest
from cadenza.application import (
    DATA_CONSENT_VERSION,
    InMemoryPasswordHasher,
    InMemoryUserRepository,
    Role,
    StaleDataConsent,
    User,
    has_current_data_consent,
    register_user,
    set_data_consent,
)

PASSWORD = secrets.token_urlsafe(12)
NOW = datetime(2026, 11, 9, 18, 30, tzinfo=UTC)


def _register(
    repo: InMemoryUserRepository,
    *,
    data_consent_version: str | None = None,
    now: datetime | None = None,
) -> User:
    return register_user(
        "ana",
        PASSWORD,
        user_repository=repo,
        password_hasher=InMemoryPasswordHasher(),
        data_consent_version=data_consent_version,
        now=now,
    )


def test_registering_with_the_current_text_records_when_and_which_version() -> None:
    repo = InMemoryUserRepository()

    user = _register(repo, data_consent_version=DATA_CONSENT_VERSION, now=NOW)

    assert user.data_consent_at == NOW
    assert user.data_consent_version == DATA_CONSENT_VERSION
    assert has_current_data_consent(user)
    assert repo.get_by_username("ana") == user


def test_registering_without_the_permission_creates_the_account_without_it() -> None:
    repo = InMemoryUserRepository()

    user = _register(repo)

    assert user.data_consent_at is None
    assert user.data_consent_version is None
    assert not has_current_data_consent(user)
    # El permiso no cambia que las cuentas del registro queden fuera del estudio.
    assert user.self_registered is True


def test_a_permission_for_another_text_is_refused_and_creates_nothing() -> None:
    repo = InMemoryUserRepository()

    with pytest.raises(StaleDataConsent):
        _register(repo, data_consent_version="2020-01-01", now=NOW)

    assert repo.get_by_username("ana") is None


def test_the_permission_is_given_and_withdrawn_just_as_easily() -> None:
    repo = InMemoryUserRepository()
    user = _register(repo)

    given = set_data_consent(
        user.id, granted=True, version=DATA_CONSENT_VERSION, now=NOW, user_repository=repo
    )
    assert has_current_data_consent(given)
    assert given.data_consent_at == NOW

    withdrawn = set_data_consent(user.id, granted=False, now=NOW, user_repository=repo)
    assert withdrawn.data_consent_at is None
    assert withdrawn.data_consent_version is None
    assert not has_current_data_consent(withdrawn)
    assert repo.get(user.id) == withdrawn
    # Lo demás de la cuenta no cambia.
    assert (withdrawn.username, withdrawn.role, withdrawn.self_registered) == (
        "ana",
        Role.TRANSCRIPTOR,
        True,
    )


def test_giving_it_again_keeps_the_first_date_and_needs_the_current_text() -> None:
    repo = InMemoryUserRepository()
    user = _register(repo, data_consent_version=DATA_CONSENT_VERSION, now=NOW)

    again = set_data_consent(
        user.id,
        granted=True,
        version=DATA_CONSENT_VERSION,
        now=datetime(2026, 11, 10, tzinfo=UTC),
        user_repository=repo,
    )
    assert again.data_consent_at == NOW

    with pytest.raises(StaleDataConsent):
        set_data_consent(user.id, granted=True, version=None, now=NOW, user_repository=repo)
    with pytest.raises(StaleDataConsent):
        set_data_consent(user.id, granted=True, version="otra", now=NOW, user_repository=repo)


def test_a_permission_given_for_an_older_text_is_not_current() -> None:
    old = User(
        id="u-1",
        username="ana",
        password_hash="-",
        role=Role.TRANSCRIPTOR,
        data_consent_at=NOW,
        data_consent_version="2020-01-01",
    )

    assert not has_current_data_consent(old)
