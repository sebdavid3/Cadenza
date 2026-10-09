"""Caso de uso: recuperar sesión y proyectar estado actual (ADR-0009, ADR-0012, #45)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cadenza.domain import (
    AnchorIndex,
    EditEvent,
    ScoreIR,
    build_anchor_index,
    materialize,
)

from ..exceptions import SessionNotFound
from ..ports.edit_event_repository import EditEventRepository
from ..ports.session_repository import PersistedFinding, SessionRepository
from ..user import Role, User


@dataclass(frozen=True)
class SessionDetail:
    """Detalle completo de una sesión con su estado actual materializado (ADR-0011, #48)."""

    session_id: str
    document_id: str
    omr_engine: str
    document: dict[str, Any]
    findings: tuple[PersistedFinding, ...]
    edits: tuple[EditEvent, ...]
    current_score: dict[str, Any]
    current_seq: int = 0
    anchor_index: dict[str, Any] | None = None
    image_artifact: str | None = None
    model_version: str | None = None
    status: str = "transcribed"
    condition: str = "assisted"
    test_score_id: str | None = None
    owner_id: str = "default-user"


def get_session(
    session_id: str,
    *,
    session_repository: SessionRepository,
    edit_repository: EditEventRepository,
    current_user: User,
) -> SessionDetail:
    """Recupera la sesión, sus hallazgos, log de ediciones y estado proyectado.

    Devuelve el número de secuencia actual (current_seq), el ScoreIR materializado
    y su índice de anclas con bbox y confidence heredadas del evento de origen (ADR-0011).

    Aplica la regla de acceso (ADR-0012): un transcriptor solo accede a sus propias
    sesiones (las ajenas responden como inexistentes); un investigador puede leer todas.
    """

    session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)

    if current_user.role == Role.TRANSCRIPTOR and session_data.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    findings = session_repository.list_findings(session_id)
    edits = edit_repository.list_events(session_id)

    raw_score = ScoreIR.from_primitive(session_data.document["score"])
    raw_anchors = (
        AnchorIndex.from_primitive(session_data.document["anchors"])
        if "anchors" in session_data.document
        else build_anchor_index(raw_score)
    )

    if edits:
        current_seq = edits[-1].seq
        current_score_ir = materialize(raw_score, edits)
        current_anchors = build_anchor_index(
            current_score_ir,
            raw_anchors=raw_anchors,
            edits=edits,
            at_seq=current_seq,
        )
        current_score = current_score_ir.to_primitive()
        anchor_index = current_anchors.to_primitive()
    else:
        current_seq = 0
        current_score = raw_score.to_primitive()
        anchor_index = raw_anchors.to_primitive()

    return SessionDetail(
        session_id=session_data.id,
        document_id=session_data.document_id,
        omr_engine=session_data.omr_engine,
        document=session_data.document,
        findings=findings,
        edits=edits,
        current_score=current_score,
        current_seq=current_seq,
        anchor_index=anchor_index,
        image_artifact=session_data.image_artifact,
        model_version=session_data.model_version,
        status=session_data.status,
        condition=session_data.condition,
        test_score_id=session_data.test_score_id,
        owner_id=session_data.owner_id,
    )
