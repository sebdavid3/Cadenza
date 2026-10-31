"""Caso de uso: cambiar el título, el compositor y los instrumentos de una sesión (#235).

ADR-0041 §4: no es una edición del log (ADR-0007) ni cuenta en las métricas de esfuerzo; solo
el dueño la hace (ADR-0012), también con la sesión finalizada (ADR-0014); y, como cambia el
MusicXML sin cambiar el `seq`, invalida la caché del estado (ADR-0037, D66).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Final

from cadenza.domain import PartMetadata, ScoreMetadata

from ..exceptions import Forbidden, InvalidSessionMetadata, SessionNotFound
from ..ports.score_state_cache import ScoreStateCache
from ..ports.session_repository import SessionData, SessionRepository
from ..user import Role, User


class Unchanged(Enum):
    """Un campo que la petición no trae: se queda como estaba."""

    UNCHANGED = "unchanged"


UNCHANGED: Final = Unchanged.UNCHANGED


def _part_count(document: object) -> int:
    """Cuántas partes tiene la partitura: las ediciones no añaden ni quitan partes.

    Cuenta las del documento guardado (primitivo o ya construido) sin reconstruir el `ScoreIR`.
    """
    score = document.get("score") if isinstance(document, Mapping) else None
    if score is None:
        score = getattr(document, "score", None)
    parts = score.get("parts") if isinstance(score, Mapping) else getattr(score, "parts", None)
    if isinstance(parts, Sequence) and not isinstance(parts, str):
        return len(parts)
    return 0


def update_session_metadata(
    session_id: str,
    *,
    session_repository: SessionRepository,
    current_user: User,
    title: str | Unchanged | None = UNCHANGED,
    composer: str | Unchanged | None = UNCHANGED,
    parts: Sequence[PartMetadata] | Unchanged = UNCHANGED,
    score_cache: ScoreStateCache | None = None,
) -> SessionData:
    """Cambia lo que se da y deja lo demás; None (o una lista vacía) lo borra.

    - Transcriptor ajeno: `SessionNotFound` (404); investigador ajeno: `Forbidden` (403).
    - `InvalidSessionMetadata` (422) si un texto es demasiado largo o hay instrumentos para más
      partes de las que tiene la partitura.
    - No cambia el estado de la sesión, el log ni los hallazgos.
    """

    session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)
    if current_user.role == Role.TRANSCRIPTOR and session_data.owner_id != current_user.id:
        raise SessionNotFound(session_id)
    if current_user.role == Role.INVESTIGADOR and session_data.owner_id != current_user.id:
        raise Forbidden("Un investigador solo puede cambiar los datos de sus propias sesiones")

    current = session_data.metadata
    try:
        metadata = ScoreMetadata(
            title=current.title if isinstance(title, Unchanged) else title,
            composer=current.composer if isinstance(composer, Unchanged) else composer,
            parts=current.parts if isinstance(parts, Unchanged) else tuple(parts),
        )
    except ValueError as exc:
        raise InvalidSessionMetadata(str(exc)) from exc

    part_count = _part_count(session_data.document)
    if len(metadata.parts) > part_count:
        raise InvalidSessionMetadata(
            f"La partitura tiene {part_count} partes y se dieron instrumentos para "
            f"{len(metadata.parts)}"
        )

    updated = session_repository.update_metadata(session_id, metadata)
    if score_cache is not None:
        score_cache.invalidate(session_id)
    return updated
