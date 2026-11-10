"""Caso de uso: registro de una cuenta por la propia persona (ADR-0022, ADR-0025)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ..exceptions import WeakPassword
from ..ports.security import PasswordHasher
from ..ports.user_repository import UserRepository
from ..user import Role, User
from .set_data_consent import check_data_consent_version


def register_user(
    username: str,
    password: str,
    *,
    user_repository: UserRepository,
    password_hasher: PasswordHasher,
    user_id: str | None = None,
    data_consent_version: str | None = None,
    now: datetime | None = None,
) -> User:
    """Crea una cuenta de transcriptor activa y marcada como autorregistrada (ADR-0025).

    Puede entrar en el momento. La marca `self_registered` la excluye de los datos del estudio,
    y un investigador puede desactivarla (`update_user`). Lanza `DuplicateUsername` si el
    nombre ya existe.

    Con `data_consent_version`, la versión del texto del permiso de uso de los datos que la
    persona aceptó, guarda el permiso con la fecha `now` (#378, ADR-0064); si no es la vigente,
    lanza `StaleDataConsent` y no crea la cuenta. Sin ella, la cuenta nace sin permiso.
    """

    if len(password) < 8:
        raise WeakPassword(min_length=8)
    consent_version = (
        None if data_consent_version is None else check_data_consent_version(data_consent_version)
    )

    new_user = User(
        id=user_id or str(uuid.uuid4()),
        username=username,
        password_hash=password_hasher.hash(password),
        role=Role.TRANSCRIPTOR,
        active=True,
        self_registered=True,
        data_consent_at=None if consent_version is None else (now or datetime.now(UTC)),
        data_consent_version=consent_version,
    )
    return user_repository.add(new_user)
