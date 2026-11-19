"""Acceso a una sesión: solo la ve y la corrige quien la transcribió (ADR-0012, ADR-0070)."""

from __future__ import annotations

from .exceptions import SessionNotFound
from .user import User


def require_owner(owner_id: str | None, current_user: User, session_id: str) -> None:
    """Lanza `SessionNotFound` si la sesión no es de `current_user`.

    Una sesión ajena responde igual que una que no existe (404), para no revelar que existe.
    """

    if owner_id != current_user.id:
        raise SessionNotFound(session_id)
