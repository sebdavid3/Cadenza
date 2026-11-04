"""Caso de uso: obtener el mapa de tiempos de la sesión (#42, D12, ADR-0009, ADR-0012)."""

from __future__ import annotations

from fractions import Fraction

from cadenza.domain import TimingMap

from ..exceptions import SessionNotFound
from ..ports.edit_event_repository import EditEventRepository
from ..ports.score_state_cache import ScoreStateCache
from ..ports.session_repository import SessionRepository
from ..score_state import load_state, timing_of
from ..stage_timing import timed_stage
from ..user import Role, User


def get_timing(
    session_id: str,
    *,
    session_repository: SessionRepository,
    edit_repository: EditEventRepository,
    current_user: User,
    score_cache: ScoreStateCache | None = None,
) -> TimingMap:
    """Recupera la sesión, materializa su ScoreIR actual y calcula su TimingMap determinista.

    Aplica la regla de acceso (ADR-0012): un transcriptor solo accede a sus propias
    sesiones; un investigador puede consultar todas. Con `score_cache`, el estado y su mapa
    salen de la caché si están (#275, ADR-0037).
    """
    with timed_stage("db"):
        session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)

    if current_user.role != Role.INVESTIGADOR and session_data.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    raw_score_data = session_data.document.get("score")
    if raw_score_data is None:
        return TimingMap(events=(), total_beats=Fraction(0), measure_offsets={})

    with timed_stage("db"):
        edits = edit_repository.list_events(session_id)
    key, state = load_state(session_id, session_data.document, edits, score_cache)
    _, timing = timing_of(key, state, score_cache)
    return timing
