"""Caso de uso: registro de una cuenta por la propia persona (ADR-0022, #154)."""

from __future__ import annotations

import uuid

from ..exceptions import RegistrationClosed, WeakPassword
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
    max_pending: int | None = None,
) -> User:
    """Crea una cuenta de transcriptor marcada como autorregistrada e **inactiva**.

    No inicia sesión ni transcribe hasta que un investigador la activa (`update_user`), y la marca
    `self_registered` permite excluirla de los datos del estudio. Lanza `DuplicateUsername` si el
    nombre ya existe. Con `max_pending`, se cierra mientras haya ese número de cuentas
    autorregistradas esperando activación (`RegistrationClosed`): una avalancha de registros no
    llena la lista que revisa el investigador.
    """

    if max_pending is not None:
        pending = sum(1 for u in user_repository.list() if u.self_registered and not u.active)
        if pending >= max_pending:
            raise RegistrationClosed(pending)
    if len(password) < 8:
        raise WeakPassword(min_length=8)

    new_user = User(
        id=user_id or str(uuid.uuid4()),
        username=username,
        password_hash=password_hasher.hash(password),
        role=Role.TRANSCRIPTOR,
        active=False,
        self_registered=True,
    )
    return user_repository.add(new_user)
