"""Puerto abstracto y doble en memoria del repositorio de usuarios (ADR-0012, #43, #46)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..exceptions import DuplicateUsername, UserNotFound
from ..user import User


class UserRepository(ABC):
    """Puerto de persistencia y consulta de cuentas de usuario."""

    @abstractmethod
    def add(self, user: User) -> User:
        """Persiste un nuevo usuario. Lanza DuplicateUsername si el username ya existe."""

    @abstractmethod
    def get(self, user_id: str) -> User | None:
        """Recupera un usuario por su identificador primario o None si no existe."""

    @abstractmethod
    def get_by_username(self, username: str) -> User | None:
        """Recupera un usuario por su nombre de usuario o None si no existe."""

    @abstractmethod
    def list(self) -> tuple[User, ...]:
        """Devuelve todos los usuarios registrados."""

    @abstractmethod
    def update(self, user: User) -> User:
        """Actualiza un usuario existente. Lanza UserNotFound si no existe."""


class InMemoryUserRepository(UserRepository):
    """Implementación en memoria para pruebas desacopladas de la base de datos."""

    def __init__(self, users: Sequence[User] | None = None) -> None:
        self._users_by_id: dict[str, User] = {}
        self._users_by_username: dict[str, User] = {}
        if users:
            for user in users:
                self.add(user)

    def add(self, user: User) -> User:
        if user.username in self._users_by_username:
            raise DuplicateUsername(user.username)
        self._users_by_id[user.id] = user
        self._users_by_username[user.username] = user
        return user

    def get(self, user_id: str) -> User | None:
        return self._users_by_id.get(user_id)

    def get_by_username(self, username: str) -> User | None:
        return self._users_by_username.get(username)

    def list(self) -> tuple[User, ...]:
        return tuple(self._users_by_id.values())

    def update(self, user: User) -> User:
        if user.id not in self._users_by_id:
            raise UserNotFound(user.id)
        existing = self._users_by_id[user.id]
        if existing.username != user.username and user.username in self._users_by_username:
            raise DuplicateUsername(user.username)
        if existing.username != user.username:
            del self._users_by_username[existing.username]
        self._users_by_id[user.id] = user
        self._users_by_username[user.username] = user
        return user
