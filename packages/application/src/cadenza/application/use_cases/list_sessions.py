"""Caso de uso: listar sesiones paginadas con resúmenes ligeros (ADR-0009, ADR-0012, #27)."""

from __future__ import annotations

from ..ports.session_repository import SessionRepository, SessionSummary
from ..user import Role, User


def list_sessions(
    *,
    session_repository: SessionRepository,
    current_user: User,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[SessionSummary, ...]:
    """Lista las sesiones accesibles para el usuario con paginación y filtros.

    - Un transcriptor solo ve sus propias sesiones (`owner_id = current_user.id`).
    - Un investigador ve las sesiones de todos los transcriptores (`owner_id = None`).
    - Orden descendente por fecha de creación, sin cargar los documentos completos.
    """

    if limit <= 0:
        limit = 50
    if offset < 0:
        offset = 0

    owner_id: str | None = None
    if current_user.role == Role.TRANSCRIPTOR:
        owner_id = current_user.id

    return session_repository.list_summaries(
        owner_id=owner_id,
        status=status,
        limit=limit,
        offset=offset,
    )
