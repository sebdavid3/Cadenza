"""Caso de uso: revalidar partitura tras correcciones (ADR-0009, ADR-0012, ADR-0013, #11)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from cadenza.domain import (
    Anchor,
    AnchorIndex,
    EditEvent,
    Finding,
    ScoreDocument,
    ScoreIR,
    build_anchor_index,
    materialize,
    translate_anchor,
)
from cadenza.validation import ValidationEngine

from ..exceptions import SessionNotFound
from ..ports.edit_event_repository import EditEventRepository
from ..ports.session_repository import PersistedFinding, SessionRepository
from ..user import Role, User


def _anchors_match_position(a: Anchor, b: Anchor) -> bool:
    return (
        a.part == b.part
        and a.staff == b.staff
        and a.measure == b.measure
        and a.voice == b.voice
        and a.event_index == b.event_index
    )


def _was_event_modified_after_dismissal(
    dismissed_anchor: Anchor,
    dismissed_at_seq: int,
    dismissed_at: datetime | None,
    edits: Sequence[EditEvent],
) -> bool:
    if dismissed_at is None:
        return False
    # Normalizar zonas horarias si alguna es naive
    t_dismiss = (
        dismissed_at if dismissed_at.tzinfo is not None else dismissed_at.replace(tzinfo=UTC)
    )
    for edit in edits:
        t_edit = (
            edit.created_at
            if edit.created_at.tzinfo is not None
            else edit.created_at.replace(tzinfo=UTC)
        )
        if t_edit > t_dismiss:
            anchor_before = translate_anchor(
                dismissed_anchor, dismissed_at_seq, edit.seq - 1, edits
            )
            if anchor_before is not None and _anchors_match_position(anchor_before, edit.anchor):
                return True
    return False


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
    5. Preserva el estado descartado previo si el evento señalado no fue modificado (#36).
    6. Persiste los hallazgos vigentes con replace_findings (conservando los históricos).
    """

    session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)

    if current_user.role == Role.TRANSCRIPTOR and session_data.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    # 1. Recuperar ediciones y determinar secuencia actual
    edits = edit_repository.list_events(session_id)
    current_seq = edits[-1].seq if edits else 0

    # Sesión no asistida: no genera hallazgos del validador (#33, D38)
    if session_data.condition == "unassisted":
        session_repository.replace_findings(session_id, (), at_seq=current_seq)
        return RevalidateResult(
            session_id=session_id,
            current_seq=current_seq,
            findings=(),
        )

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

    # 4. Determinar preservación de falsos positivos previamente descartados (#36)
    dismissed_findings = session_repository.list_dismissed_findings(session_id)
    dismissed_statuses: list[PersistedFinding | None] = []

    for f in findings_with_seq:
        matching_dismissal: PersistedFinding | None = None
        for d in dismissed_findings:
            if d.rule_id != f.rule_id:
                continue
            d_anchor = Anchor.from_primitive(d.anchor)
            current_anchor_for_d = translate_anchor(d_anchor, d.at_seq, current_seq, edits)
            if current_anchor_for_d is None:
                continue
            if _anchors_match_position(
                f.anchor, current_anchor_for_d
            ) and not _was_event_modified_after_dismissal(
                d_anchor, d.at_seq, d.dismissed_at, edits
            ):
                matching_dismissal = d
                break
        dismissed_statuses.append(matching_dismissal)

    # 5. Persistir los nuevos hallazgos y actualizar validated_at_seq
    persisted = session_repository.replace_findings(
        session_id,
        findings_with_seq,
        at_seq=current_seq,
        dismissed_statuses=dismissed_statuses,
    )

    # Solo los hallazgos activos se devuelven en el resultado de revalidación (#36)
    active_findings = tuple(p for p in persisted if p.status == "active")

    return RevalidateResult(
        session_id=session_id,
        current_seq=current_seq,
        findings=active_findings,
    )
