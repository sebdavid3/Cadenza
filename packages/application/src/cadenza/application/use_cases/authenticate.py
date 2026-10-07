"""Caso de uso de autenticación de usuario (ADR-0012, #44)."""

from __future__ import annotations

from ..exceptions import NotAuthenticated
from ..ports.security import PasswordHasher
from ..ports.user_repository import UserRepository
from ..user import User


def authenticate(
    username: str,
    password: str,
    *,
    user_repository: UserRepository,
    password_hasher: PasswordHasher,
) -> User:
    """Verifica credenciales y devuelve el usuario si está activo.

    Lanza NotAuthenticated sin revelar si el usuario no existe, la contraseña es
    incorrecta o la cuenta está inactiva.
    """
    user = user_repository.get_by_username(username)
    if user is None:
        raise NotAuthenticated("Credenciales inválidas")
    if not user.active:
        raise NotAuthenticated("Credenciales inválidas")
    if not password_hasher.verify(password, user.password_hash):
        raise NotAuthenticated("Credenciales inválidas")
    return user
