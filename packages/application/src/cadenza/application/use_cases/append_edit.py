"""Caso de uso: añadir un evento de edición al log append-only (ADR-0007, ADR-0009)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from cadenza.domain import Anchor, EditEvent, EditOp

from ..exceptions import SessionNotFound
from ..ports.edit_event_repository import EditEventRepository
from ..ports.session_repository import SessionRepository


def append_edit(
    session_id: str,
    *,
    anchor: Anchor,
    op: EditOp,
    author: str,
    session_repository: SessionRepository,
    edit_repository: EditEventRepository,
    edit_id: str | None = None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    created_at: datetime | None = None,
) -> EditEvent:
    """Añade un nuevo evento inmutable al log de la sesión verificando su existencia."""

    session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)

    seq = edit_repository.next_seq(session_id)
    edit = EditEvent(
        id=edit_id or str(uuid.uuid4()),
        document_id=session_data.document_id,
        seq=seq,
        anchor=anchor,
        op=op,
        author=author,
        created_at=created_at or datetime.now(UTC),
        before=before,
        after=after,
    )

    return edit_repository.append(session_id, edit)
