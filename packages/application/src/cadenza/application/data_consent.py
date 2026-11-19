"""Permiso de uso de los datos de una cuenta (#378, ADR-0065).

El texto del permiso vive en la web (`apps/web/src/pages/consent/consent.ts`), con la misma
versión que esta: una prueba comprueba que coinciden. Al cambiar el texto, se cambian las dos, y
los permisos dados para la versión anterior dejan de estar vigentes hasta que se vuelvan a dar.

Se guarda cuándo se dio y para qué versión. Desde #422, las exportaciones y los datasets de `ml`
lo leen para decidir qué sesiones de las cuentas del registro entran (`cadenza.learning.consent`).
"""

from __future__ import annotations

from .user import User

DATA_CONSENT_VERSION = "2026-11-19"
"""Versión vigente del texto del permiso: la fecha en que se redactó."""


def has_current_data_consent(user: User) -> bool:
    """Si la cuenta tiene el permiso dado para el texto vigente."""

    return user.data_consent_at is not None and user.data_consent_version == DATA_CONSENT_VERSION
