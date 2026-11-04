"""`authenticate` hace el mismo trabajo de hash en los tres casos del 401 (#226, ADR-0042).

El tiempo de respuesta no debe distinguir una cuenta activa de un usuario inexistente o
desactivado. En vez de medir tiempos, que en la CI sería frágil, se cuenta cuántas veces se
verifica una contraseña: exactamente una en todos los casos.
"""

from __future__ import annotations

import secrets

import pytest
from cadenza.application import (
    InMemoryPasswordHasher,
    InMemoryUserRepository,
    NotAuthenticated,
    PasswordHasher,
    Role,
    User,
    authenticate,
)


class CountingPasswordHasher(PasswordHasher):
    """Doble que cuenta las verificaciones y recuerda contra qué hash se hicieron."""

    def __init__(self) -> None:
        self._inner = InMemoryPasswordHasher()
        self.verified_hashes: list[str] = []
        self.dummy_calls = 0

    def hash(self, password: str) -> str:
        return self._inner.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        self.verified_hashes.append(password_hash)
        return self._inner.verify(password, password_hash)

    def dummy_hash(self) -> str:
        self.dummy_calls += 1
        return self._inner.dummy_hash()


ACTIVE_PASSWORD = secrets.token_urlsafe(16)
INACTIVE_PASSWORD = secrets.token_urlsafe(16)
WRONG_PASSWORD = secrets.token_urlsafe(16)


@pytest.fixture
def hasher() -> CountingPasswordHasher:
    return CountingPasswordHasher()


@pytest.fixture
def repo(hasher: CountingPasswordHasher) -> InMemoryUserRepository:
    repo = InMemoryUserRepository()
    repo.add(
        User(
            id="usr-activa",
            username="activa",
            password_hash=hasher.hash(ACTIVE_PASSWORD),
            role=Role.TRANSCRIPTOR,
            active=True,
        )
    )
    repo.add(
        User(
            id="usr-desactivada",
            username="desactivada",
            password_hash=hasher.hash(INACTIVE_PASSWORD),
            role=Role.TRANSCRIPTOR,
            active=False,
        )
    )
    return repo


@pytest.mark.parametrize(
    ("username", "password"),
    [
        pytest.param("nadie", ACTIVE_PASSWORD, id="usuario-inexistente"),
        pytest.param("desactivada", INACTIVE_PASSWORD, id="cuenta-desactivada"),
        pytest.param("desactivada", WRONG_PASSWORD, id="cuenta-desactivada-y-contrasena-mal"),
        pytest.param("activa", WRONG_PASSWORD, id="contrasena-incorrecta"),
    ],
)
def test_the_three_401_cases_verify_exactly_once(
    repo: InMemoryUserRepository,
    hasher: CountingPasswordHasher,
    username: str,
    password: str,
) -> None:
    with pytest.raises(NotAuthenticated) as exc_info:
        authenticate(username, password, user_repository=repo, password_hasher=hasher)

    assert exc_info.value.message == "Credenciales inválidas"
    assert len(hasher.verified_hashes) == 1


def test_success_verifies_once_against_the_real_hash(
    repo: InMemoryUserRepository, hasher: CountingPasswordHasher
) -> None:
    user = authenticate("activa", ACTIVE_PASSWORD, user_repository=repo, password_hasher=hasher)

    assert user.id == "usr-activa"
    assert hasher.verified_hashes == [hasher.hash(ACTIVE_PASSWORD)]
    assert hasher.dummy_calls == 0


def test_unknown_user_verifies_against_the_dummy_hash(
    repo: InMemoryUserRepository, hasher: CountingPasswordHasher
) -> None:
    with pytest.raises(NotAuthenticated):
        authenticate("nadie", ACTIVE_PASSWORD, user_repository=repo, password_hasher=hasher)

    assert hasher.dummy_calls == 1
    assert hasher.verified_hashes == [hasher.dummy_hash()]


def test_inactive_account_verifies_its_own_hash_and_still_fails(
    repo: InMemoryUserRepository, hasher: CountingPasswordHasher
) -> None:
    # Con la contraseña correcta de una cuenta desactivada, el 401 no cambia.
    with pytest.raises(NotAuthenticated):
        authenticate("desactivada", INACTIVE_PASSWORD, user_repository=repo, password_hasher=hasher)

    assert hasher.verified_hashes == [hasher.hash(INACTIVE_PASSWORD)]
    assert hasher.dummy_calls == 0


def test_in_memory_dummy_hash_is_stable_and_matches_no_password() -> None:
    hasher = InMemoryPasswordHasher()

    assert hasher.dummy_hash() == hasher.dummy_hash()
    assert hasher.verify(secrets.token_urlsafe(16), hasher.dummy_hash()) is False
    assert hasher.verify("", hasher.dummy_hash()) is False
