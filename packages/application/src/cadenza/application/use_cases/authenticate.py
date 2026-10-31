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
    incorrecta o la cuenta está inactiva: ni por la respuesta ni por el tiempo. En los tres
    casos se verifica la contraseña exactamente una vez, contra el hash de la cuenta o, si no
    existe, contra el hash de relleno del adaptador (#226, ADR-0042).
    """
    user = user_repository.get_by_username(username)
    password_hash = user.password_hash if user is not None else password_hasher.dummy_hash()
    matches = password_hasher.verify(password, password_hash)
    if user is None or not user.active or not matches:
        raise NotAuthenticated("Credenciales inválidas")
    return user
