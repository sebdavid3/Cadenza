"""Caso de uso: modificar cuenta, cambiar rol, estado o restablecer contraseña (ADR-0012, #46)."""

from __future__ import annotations

from dataclasses import replace

from ..exceptions import Forbidden, UserNotFound, WeakPassword
from ..ports.security import PasswordHasher
from ..ports.user_repository import UserRepository
from ..user import Role, User


def update_user(
    user_id: str,
    *,
    current_user: User,
    user_repository: UserRepository,
    role: Role | None = None,
    active: bool | None = None,
    new_password: str | None = None,
    password_hasher: PasswordHasher | None = None,
) -> User:
    """Modifica el rol, estado o contraseña de un usuario. Restringido a investigadores."""

    if current_user.role != Role.INVESTIGADOR:
        raise Forbidden("Solo un investigador puede modificar usuarios")

    user = user_repository.get(user_id)
    if user is None:
        raise UserNotFound(user_id)

    updated_fields: dict[str, object] = {}

    if role is not None:
        updated_fields["role"] = role

    if active is not None:
        updated_fields["active"] = active

    if new_password is not None:
        if len(new_password) < 8:
            raise WeakPassword(min_length=8)
        if password_hasher is None:
            raise ValueError("password_hasher es requerido para restablecer contraseña")
        updated_fields["password_hash"] = password_hasher.hash(new_password)

    if not updated_fields:
        return user

    updated_user = replace(user, **updated_fields)  # type: ignore[arg-type]
    return user_repository.update(updated_user)
