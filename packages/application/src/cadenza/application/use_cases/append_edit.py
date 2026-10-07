"""Caso de uso: añadir edición al log append-only (ADR-0007, ADR-0009, ADR-0012, #45)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from cadenza.domain import Anchor, EditEvent, EditOp

from ..exceptions import Forbidden, SessionNotFound
from ..ports.edit_event_repository import EditEventRepository
from ..ports.session_repository import SessionRepository
from ..user import Role, User


def append_edit(
    session_id: str,
    *,
    anchor: Anchor,
    op: EditOp,
    session_repository: SessionRepository,
    edit_repository: EditEventRepository,
    current_user: User,
    author: str | None = None,
    edit_id: str | None = None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    created_at: datetime | None = None,
) -> EditEvent:
    """Añade un nuevo evento inmutable al log de la sesión verificando su existencia y propiedad.

    La autoría la fija el servidor a partir del usuario actual (ADR-0012).
    Un transcriptor solo edita sus sesiones (las ajenas se reportan como SessionNotFound).
    Un investigador solo edita sus propias sesiones (las ajenas lanzan Forbidden).
    """

    session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)

    if current_user.role == Role.TRANSCRIPTOR and session_data.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    if current_user.role == Role.INVESTIGADOR and session_data.owner_id != current_user.id:
        raise Forbidden("Un investigador solo puede editar sus propias sesiones")

    seq = edit_repository.next_seq(session_id)
    effective_author = author or current_user.username

    edit = EditEvent(
        id=edit_id or str(uuid.uuid4()),
        document_id=session_data.document_id,
        seq=seq,
        anchor=anchor,
        op=op,
        author=effective_author,
        created_at=created_at or datetime.now(UTC),
        before=before,
        after=after,
    )

    return edit_repository.append(session_id, edit)
