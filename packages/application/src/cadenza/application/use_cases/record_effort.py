"""Caso de uso: registrar métricas de esfuerzo de corrección (#13, ADR-0012)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from ..exceptions import Forbidden, SessionNotFound
from ..ports.effort_repository import EffortMetricsData, EffortRepository
from ..ports.session_repository import SessionRepository
from ..user import Role, User


def record_effort(
    session_repo: SessionRepository,
    effort_repo: EffortRepository,
    *,
    session_id: str,
    duration_ms: int,
    time_to_first_edit_ms: int | None = None,
    interventions: Mapping[Any, int] | None = None,
    current_user: User,
    metrics_id: str | None = None,
    created_at: datetime | None = None,
) -> EffortMetricsData:
    """Registra y persiste las métricas de esfuerzo de una sesión de corrección humana.

    - Control de acceso ADR-0012:
      * Transcriptor ajeno recibe SessionNotFound (404).
      * Investigador ajeno recibe Forbidden (403): solo el dueño puede registrar su propio esfuerzo.
    - Valida que duration_ms y time_to_first_edit_ms sean no negativos.
    - Normaliza las claves de intervenciones a cadenas de texto ('1', '2', ...).
    """
    session = session_repo.get(session_id)
    if session is None:
        raise SessionNotFound(session_id)

    # Control de acceso ADR-0012
    if current_user.role == Role.TRANSCRIPTOR and session.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    if current_user.role == Role.INVESTIGADOR and session.owner_id != current_user.id:
        raise Forbidden("Un investigador solo puede registrar esfuerzo en sus propias sesiones")

    if duration_ms < 0:
        raise ValueError("duration_ms debe ser mayor o igual a 0")

    if time_to_first_edit_ms is not None and time_to_first_edit_ms < 0:
        raise ValueError("time_to_first_edit_ms debe ser mayor o igual a 0")

    normalized_interventions: dict[str, int] = {}
    if interventions:
        for k, v in interventions.items():
            if v < 0:
                raise ValueError(
                    f"El conteo de intervenciones para el compás {k} no puede ser negativo"
                )
            normalized_interventions[str(k)] = int(v)

    data = EffortMetricsData(
        id=metrics_id or str(uuid.uuid4()),
        session_id=session_id,
        duration_ms=duration_ms,
        time_to_first_edit_ms=time_to_first_edit_ms,
        interventions=normalized_interventions,
        created_at=created_at or datetime.now(UTC),
    )

    return effort_repo.add(data)
