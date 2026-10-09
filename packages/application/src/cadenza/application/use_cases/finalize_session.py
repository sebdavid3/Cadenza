"""Caso de uso: finalizar sesión de transcripción (ADR-0009, ADR-0012, ADR-0014, #34)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from cadenza.domain import (
    AnchorIndex,
    Finding,
    ScoreDocument,
    ScoreIR,
    build_anchor_index,
    materialize,
)
from cadenza.validation import ValidationEngine

from ..exceptions import Forbidden, SessionNotFound
from ..ports.edit_event_repository import EditEventRepository
from ..ports.session_repository import PersistedFinding, SessionRepository
from ..session_status import SessionStatus
from ..user import Role, User


@dataclass(frozen=True)
class FinalizeResult:
    """Resultado de la finalización de una sesión (ADR-0014, #34)."""

    session_id: str
    status: str
    final_seq: int
    findings: tuple[PersistedFinding, ...]


def finalize_session(
    session_id: str,
    *,
    validator: ValidationEngine,
    session_repository: SessionRepository,
    edit_repository: EditEventRepository,
    current_user: User,
) -> FinalizeResult:
    """Finaliza una sesión marcándola como cerrada para nuevas ediciones.

    1. Comprueba existencia y propiedad según ADR-0012.
    2. Revalida el documento sobre su estado materializado actual (#11, #34).
    3. Actualiza el estado a `finalized` (#34).
    4. Devuelve el estado, el seq final y los hallazgos vigentes.
    """

    session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)

    if current_user.role == Role.TRANSCRIPTOR and session_data.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    if current_user.role == Role.INVESTIGADOR and session_data.owner_id != current_user.id:
        raise Forbidden("Un investigador solo puede finalizar sus propias sesiones")

    # 1. Recuperar ediciones y determinar secuencia final
    edits = edit_repository.list_events(session_id)
    current_seq = edits[-1].seq if edits else 0

    # 2. Materializar ScoreIR y AnchorIndex
    raw_score = ScoreIR.from_primitive(session_data.document["score"])
    raw_anchors = (
        AnchorIndex.from_primitive(session_data.document["anchors"])
        if "anchors" in session_data.document
        else build_anchor_index(raw_score)
    )

    if edits:
        current_score_ir = materialize(raw_score, edits)
        current_anchors = build_anchor_index(
            current_score_ir,
            raw_anchors=raw_anchors,
            edits=edits,
            at_seq=current_seq,
        )
    else:
        current_score_ir = raw_score
        current_anchors = raw_anchors

    raw_doc = ScoreDocument.from_primitive(session_data.document)
    current_doc = ScoreDocument(
        id=session_data.document_id,
        score=current_score_ir,
        anchors=current_anchors,
        provenance=raw_doc.provenance,
    )

    # 3. Evaluar reglas sobre el documento materializado
    evaluated_findings: list[Finding] = validator.validate(current_doc)
    findings_with_seq = [replace(f, at_seq=current_seq) for f in evaluated_findings]

    # 4. Persistir hallazgos y actualizar validated_at_seq
    persisted = session_repository.replace_findings(
        session_id,
        findings_with_seq,
        at_seq=current_seq,
    )

    # 5. Marcar estado como finalizado
    updated = session_repository.update_status(session_id, SessionStatus.FINALIZED)

    return FinalizeResult(
        session_id=session_id,
        status=updated.status,
        final_seq=current_seq,
        findings=persisted,
    )
