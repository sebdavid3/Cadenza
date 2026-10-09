"""Caso de uso: dar de alta una nueva cuenta de usuario (ADR-0012, #46)."""

from __future__ import annotations

import uuid

from ..exceptions import Forbidden, WeakPassword
from ..ports.security import PasswordHasher
from ..ports.user_repository import UserRepository
from ..user import Role, User


def create_user(
    username: str,
    password: str,
    role: Role,
    *,
    current_user: User,
    user_repository: UserRepository,
    password_hasher: PasswordHasher,
    user_id: str | None = None,
) -> User:
    """Crea una cuenta en el sistema. Operación restringida exclusivamente a investigadores."""

    if current_user.role != Role.INVESTIGADOR:
        raise Forbidden("Solo un investigador puede crear usuarios")

    if len(password) < 8:
        raise WeakPassword(min_length=8)

    actual_id = user_id or str(uuid.uuid4())
    password_hash = password_hasher.hash(password)

    new_user = User(
        id=actual_id,
        username=username,
        password_hash=password_hash,
        role=role,
        active=True,
    )

    return user_repository.add(new_user)
