"""Caso de uso: cambio de contraseña por parte del propio usuario (ADR-0012, #46)."""

from __future__ import annotations

from dataclasses import replace

from ..exceptions import NotAuthenticated, UserNotFound, WeakPassword
from ..ports.security import PasswordHasher
from ..ports.user_repository import UserRepository
from ..user import User


def change_password(
    current_password: str,
    new_password: str,
    *,
    current_user: User,
    user_repository: UserRepository,
    password_hasher: PasswordHasher,
) -> User:
    """Permite al usuario autenticado actualizar su contraseña tras validar la actual."""

    user = user_repository.get(current_user.id)
    if user is None:
        raise UserNotFound(current_user.id)

    if not password_hasher.verify(current_password, user.password_hash):
        raise NotAuthenticated("La contraseña actual es incorrecta")

    if len(new_password) < 8:
        raise WeakPassword(min_length=8)

    new_hash = password_hasher.hash(new_password)
    updated_user = replace(user, password_hash=new_hash)
    return user_repository.update(updated_user)
