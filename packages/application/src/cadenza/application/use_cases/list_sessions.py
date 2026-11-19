"""Caso de uso: listar sesiones paginadas con resúmenes ligeros (ADR-0009, ADR-0012, #27)."""

from __future__ import annotations

from ..ports.session_repository import SessionRepository, SessionSummary
from ..user import User


def list_sessions(
    *,
    session_repository: SessionRepository,
    current_user: User,
    status: str | None = None,
    condition: str | None = None,
    test_score_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[SessionSummary, ...]:
    """Lista las sesiones accesibles para el usuario con paginación y filtros.

    - Cada cuenta ve solo sus propias sesiones (`owner_id = current_user.id`).
    - Orden descendente por fecha de creación, sin cargar los documentos completos.
    """

    if limit <= 0:
        limit = 50
    if offset < 0:
        offset = 0

    return session_repository.list_summaries(
        owner_id=current_user.id,
        status=status,
        condition=condition,
        test_score_id=test_score_id,
        limit=limit,
        offset=offset,
    )
