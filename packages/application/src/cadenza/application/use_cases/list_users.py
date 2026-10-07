"""Caso de uso: listar usuarios del sistema (ADR-0012, #46)."""

from __future__ import annotations

from ..exceptions import Forbidden
from ..ports.user_repository import UserRepository
from ..user import Role, User


def list_users(
    *,
    current_user: User,
    user_repository: UserRepository,
) -> tuple[User, ...]:
    """Devuelve todas las cuentas registradas. Operación exclusiva de investigadores."""

    if current_user.role != Role.INVESTIGADOR:
        raise Forbidden("Solo un investigador puede listar usuarios")

    return user_repository.list()
