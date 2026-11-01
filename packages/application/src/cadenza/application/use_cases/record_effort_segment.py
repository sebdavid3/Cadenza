"""Caso de uso: sumar un tramo al registro de esfuerzo de la sesión (#188, ADR-0050)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Final

from ..effort import merge_segment, refreshed_effort, total_active_ms
from ..exceptions import Forbidden, InvalidEffortSegment, SessionClosed, SessionNotFound
from ..ports.edit_event_repository import EditEventRepository
from ..ports.effort_repository import (
    EffortMetricsData,
    EffortRepository,
    EffortSegment,
    empty_accumulated,
)
from ..ports.session_repository import SessionRepository
from ..session_status import SessionStatus
from ..user import Role, User

MAX_EFFORT_SEGMENTS: Final[int] = 500
"""Tramos como mucho por sesión: una pestaña por carga sin `sessionStorage` sería uno por
recarga; quinientos sobran para una corrección y acotan lo que guarda el registro."""

MAX_DURATION_MS: Final[int] = 2**31 - 1
"""Lo que cabe en `effort_metrics.duration_ms` (INTEGER), unos 24 días."""

_SEGMENT_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def refresh_accumulated_effort(
    session_id: str,
    *,
    session_repository: SessionRepository,
    edit_repository: EditEventRepository,
    effort_repository: EffortRepository,
    now: datetime | None = None,
) -> EffortMetricsData | None:
    """Vuelve a calcular lo que el registro acumulado deriva del log y de las sugerencias, si lo
    hay (al finalizar, ADR-0050 §3). Sin registro no crea ninguno: nada se midió."""
    record = effort_repository.get_accumulated(session_id)
    if record is None:
        return None
    return effort_repository.save_accumulated(
        refreshed_effort(
            record,
            segments=record.segments,
            edits=edit_repository.list_events(session_id),
            suggestions=session_repository.list_suggestions(session_id),
            now=now or datetime.now(UTC),
        )
    )


def record_effort_segment(
    session_id: str,
    segment_id: str,
    *,
    active_ms: int,
    first_edit_ms: int | None,
    session_repository: SessionRepository,
    edit_repository: EditEventRepository,
    effort_repository: EffortRepository,
    current_user: User,
    idle_threshold_ms: int | None = None,
    now: datetime | None = None,
) -> EffortMetricsData:
    """Suma al registro acumulado de la sesión lo que midió una pestaña hasta ahora.

    - Solo mide quien la transcribió (ADR-0012): un transcriptor ajeno recibe 404 y un
      investigador ajeno 403.
    - Una sesión finalizada no suma más tiempo: 409 (`SessionClosed`). El registro acumula
      hasta la última finalización; al reabrirla se sigue sumando (protocolo §3.4).
    - El tramo solo crece (`merge_segment`): repetir o retrasar una petición no cuenta dos veces.
    - Con cada tramo se vuelve a calcular lo que sale del log y de las sugerencias.
    """
    session = session_repository.get(session_id)
    if session is None:
        raise SessionNotFound(session_id)
    if current_user.role == Role.TRANSCRIPTOR and session.owner_id != current_user.id:
        raise SessionNotFound(session_id)
    if current_user.role == Role.INVESTIGADOR and session.owner_id != current_user.id:
        raise Forbidden("Solo quien transcribió la sesión mide su esfuerzo")
    if session.status == SessionStatus.FINALIZED:
        raise SessionClosed(session_id)

    if not _SEGMENT_ID.fullmatch(segment_id):
        raise InvalidEffortSegment(
            "El tramo se identifica con 1 a 64 letras, cifras, guiones o guiones bajos"
        )
    if active_ms < 0:
        raise InvalidEffortSegment("El tiempo de un tramo no puede ser negativo")
    if first_edit_ms is not None and not 0 <= first_edit_ms <= active_ms:
        raise InvalidEffortSegment(
            "La primera edición no puede ser negativa ni posterior al tiempo del tramo"
        )
    if idle_threshold_ms is not None and idle_threshold_ms < 1:
        raise InvalidEffortSegment("El umbral de las pausas tiene que ser positivo")

    moment = now or datetime.now(UTC)
    record = effort_repository.get_accumulated(session_id) or empty_accumulated(session_id, moment)
    segments = merge_segment(
        record.segments,
        EffortSegment(segment_id, active_ms, first_edit_ms, idle_threshold_ms),
    )
    if len(segments) > MAX_EFFORT_SEGMENTS:
        raise InvalidEffortSegment(f"Una sesión admite {MAX_EFFORT_SEGMENTS} tramos como mucho")
    if total_active_ms(segments) > MAX_DURATION_MS:
        raise InvalidEffortSegment("La duración acumulada no cabe en el registro")

    return effort_repository.save_accumulated(
        refreshed_effort(
            record,
            segments=segments,
            edits=edit_repository.list_events(session_id),
            suggestions=session_repository.list_suggestions(session_id),
            now=moment,
        )
    )
