"""Caso de uso: registro de una cuenta por la propia persona (ADR-0022, ADR-0025)."""

from __future__ import annotations

import uuid

from ..exceptions import WeakPassword
from ..ports.security import PasswordHasher
from ..ports.user_repository import UserRepository
from ..user import Role, User


def register_user(
    username: str,
    password: str,
    *,
    user_repository: UserRepository,
    password_hasher: PasswordHasher,
    user_id: str | None = None,
) -> User:
    """Crea una cuenta de transcriptor activa y marcada como autorregistrada (ADR-0025).

    Puede entrar en el momento. La marca `self_registered` la excluye de los datos del estudio,
    y un investigador puede desactivarla (`update_user`). Lanza `DuplicateUsername` si el
    nombre ya existe.
    """

    if len(password) < 8:
        raise WeakPassword(min_length=8)

    new_user = User(
        id=user_id or str(uuid.uuid4()),
        username=username,
        password_hash=password_hasher.hash(password),
        role=Role.TRANSCRIPTOR,
        active=True,
        self_registered=True,
    )
    return user_repository.add(new_user)
