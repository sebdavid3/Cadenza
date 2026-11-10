"""Permiso de uso de los datos de una cuenta (#378, ADR-0065).

El texto del permiso vive en la web (`apps/web/src/pages/consent/consent.ts`), con la misma
versión que esta: una prueba comprueba que coinciden. Al cambiar el texto, se cambian las dos, y
los permisos dados para la versión anterior dejan de estar vigentes hasta que se vuelvan a dar.

El permiso solo se guarda (cuándo y qué versión): usarlo para incluir datos será otro issue.
"""

from __future__ import annotations

from .user import User

DATA_CONSENT_VERSION = "2026-11-09"
"""Versión vigente del texto del permiso: la fecha en que se redactó."""


def has_current_data_consent(user: User) -> bool:
    """Si la cuenta tiene el permiso dado para el texto vigente."""

    return user.data_consent_at is not None and user.data_consent_version == DATA_CONSENT_VERSION
