"""Caso de uso: revalidar partitura tras correcciones (ADR-0009, ADR-0012, ADR-0013, #11)."""

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

from ..exceptions import SessionNotFound
from ..ports.edit_event_repository import EditEventRepository
from ..ports.session_repository import PersistedFinding, SessionRepository
from ..user import Role, User


@dataclass(frozen=True)
class RevalidateResult:
    """Resultado de la revalidación de la partitura (ADR-0013, #11)."""

    session_id: str
    current_seq: int
    findings: tuple[PersistedFinding, ...]


def revalidate(
    session_id: str,
    *,
    validator: ValidationEngine,
    session_repository: SessionRepository,
    edit_repository: EditEventRepository,
    current_user: User,
) -> RevalidateResult:
    """Revalida la partitura sobre su estado materializado actual.

    1. Recupera la sesión y comprueba permisos (ADR-0012).
    2. Materializa el ScoreIR con el log existente y construye el AnchorIndex enriquecido.
    3. Construye un ScoreDocument representativo y ejecuta ValidationEngine.
    4. Asigna at_seq igual al último seq aplicado a cada hallazgo.
    5. Persiste los hallazgos vigentes con replace_findings (conservando los históricos).
    """

    session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)

    if current_user.role == Role.TRANSCRIPTOR and session_data.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    # 1. Recuperar ediciones y determinar secuencia actual
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

    # 4. Persistir los nuevos hallazgos y actualizar validated_at_seq
    persisted = session_repository.replace_findings(
        session_id,
        findings_with_seq,
        at_seq=current_seq,
    )

    return RevalidateResult(
        session_id=session_id,
        current_seq=current_seq,
        findings=persisted,
    )
