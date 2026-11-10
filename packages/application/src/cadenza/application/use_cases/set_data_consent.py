"""Caso de uso: dar o retirar el permiso de uso de los datos (#378, ADR-0065)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from ..data_consent import DATA_CONSENT_VERSION
from ..exceptions import StaleDataConsent, UserNotFound
from ..ports.user_repository import UserRepository
from ..user import User


def check_data_consent_version(version: str | None) -> str:
    """La versión del texto que se aceptó, si es la vigente; si no, `StaleDataConsent`."""

    if version != DATA_CONSENT_VERSION:
        raise StaleDataConsent(version, DATA_CONSENT_VERSION)
    return version


def set_data_consent(
    user_id: str,
    *,
    granted: bool,
    now: datetime,
    user_repository: UserRepository,
    version: str | None = None,
) -> User:
    """Da el permiso para el texto vigente (`version`) o lo retira; devuelve la cuenta.

    Darlo exige la versión del texto que se leyó: si no es la vigente, `StaleDataConsent` y no
    cambia nada. Volver a darlo con el mismo texto conserva la fecha de la primera vez. Retirarlo
    borra la fecha y la versión: la cuenta queda sin permiso.
    """

    user = user_repository.get(user_id)
    if user is None:
        raise UserNotFound(user_id)
    if not granted:
        updated = replace(user, data_consent_at=None, data_consent_version=None)
    else:
        accepted = check_data_consent_version(version)
        if user.data_consent_version == accepted and user.data_consent_at is not None:
            return user
        updated = replace(user, data_consent_at=now, data_consent_version=accepted)
    return user_repository.update(updated)
