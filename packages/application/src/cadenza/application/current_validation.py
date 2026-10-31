"""Validar el estado actual de una sesión y guardar sus hallazgos (ADR-0013, ADR-0035, ADR-0043).

Lo comparten `revalidate` y `finalize_session`, para que finalizar valide exactamente como una
revalidación (D65): las reglas y, tras ellas, la capa de sugerencias sobre el estado
materializado; los rechazos y los descartes de la validación vigente se heredan mientras su evento
no cambie; y en una sesión `unassisted` no corre nada y se guardan los hallazgos vacíos
(ADR-0040 §13).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

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

from .ports.session_repository import PersistedFinding, SessionData, SessionRepository
from .ports.suggestion_model import SuggestionModel
from .suggestions import (
    anchors_match_position,
    suggest,
    was_event_modified_after,
    with_inherited_rejections,
)


@dataclass(frozen=True)
class CurrentValidation:
    """La validación guardada: el `seq` validado y sus hallazgos activos."""

    seq: int
    active: tuple[PersistedFinding, ...]


def _current_document(session_data: SessionData, edits: Sequence[EditEvent]) -> ScoreDocument:
    """El documento en su estado actual: el `ScoreIR` materializado y su índice de anclas."""
    raw_score = ScoreIR.from_primitive(session_data.document["score"])
    raw_anchors = (
        AnchorIndex.from_primitive(session_data.document["anchors"])
        if "anchors" in session_data.document
        else build_anchor_index(raw_score)
    )
    if edits:
        current_seq = edits[-1].seq
        score = materialize(raw_score, edits)
        anchors = build_anchor_index(
            score, raw_anchors=raw_anchors, edits=edits, at_seq=current_seq
        )
    else:
        score, anchors = raw_score, raw_anchors
    raw_doc = ScoreDocument.from_primitive(session_data.document)
    return ScoreDocument(
        id=session_data.document_id,
        score=score,
        anchors=anchors,
        provenance=raw_doc.provenance,
    )


def inherited_dismissals(
    findings: Sequence[Finding],
    dismissed: Sequence[PersistedFinding],
    *,
    current_seq: int,
    edits: Sequence[EditEvent],
) -> list[PersistedFinding | None]:
    """El descarte que hereda cada hallazgo nuevo, o None (#36, ADR-0035 §13).

    `dismissed` son los descartes de la validación vigente. Un hallazgo hereda el de la misma
    regla cuya ancla, traducida al estado actual, es la suya, si su evento no cambió desde el
    descarte.
    """
    statuses: list[PersistedFinding | None] = []
    for finding in findings:
        match: PersistedFinding | None = None
        for old in dismissed:
            if old.rule_id != finding.rule_id:
                continue
            old_anchor = Anchor.from_primitive(old.anchor)
            moved = translate_anchor(old_anchor, old.at_seq, current_seq, edits)
            if moved is None:
                continue
            if anchors_match_position(finding.anchor, moved) and not was_event_modified_after(
                old_anchor, old.at_seq, old.dismissed_at, edits
            ):
                match = old
                break
        statuses.append(match)
    return statuses


def store_current_validation(
    session_data: SessionData,
    edits: Sequence[EditEvent],
    *,
    validator: ValidationEngine,
    session_repository: SessionRepository,
    suggestion_model: SuggestionModel | None = None,
) -> CurrentValidation:
    """Valida el estado actual de la sesión y sustituye los hallazgos de ese `seq`.

    1. En `unassisted` no corren ni las reglas ni la capa: se guardan los hallazgos vacíos (D38,
       ADR-0040 §13).
    2. Materializa el estado actual y ejecuta las reglas y, tras ellas, la capa (ADR-0036 §4).
    3. Las sugerencias heredan los rechazos, y los hallazgos los descartes, de la validación
       vigente (`validated_at_seq`), leídos antes de sustituirla: los de validaciones anteriores
       son historia (ADR-0013 §3, ADR-0035 §13).
    4. Guarda los hallazgos con `replace_findings`, que conserva los de otros estados.
    """
    session_id = session_data.id
    current_seq = edits[-1].seq if edits else 0

    if session_data.condition == "unassisted":
        session_repository.replace_findings(session_id, (), at_seq=current_seq)
        return CurrentValidation(seq=current_seq, active=())

    document = _current_document(session_data, edits)
    evaluated: list[Finding] = validator.validate(document)
    suggested = suggest(document, evaluated, suggestion_model)
    findings = [replace(f, at_seq=current_seq) for f, _ in suggested]
    suggestions = with_inherited_rejections(
        suggested,
        session_repository.list_suggestions(session_id, at_seq=session_data.validated_at_seq),
        current_seq=current_seq,
        edits=edits,
    )
    dismissed = tuple(
        d
        for d in session_repository.list_dismissed_findings(session_id)
        if d.at_seq == session_data.validated_at_seq
    )
    persisted = session_repository.replace_findings(
        session_id,
        findings,
        at_seq=current_seq,
        dismissed_statuses=inherited_dismissals(
            findings, dismissed, current_seq=current_seq, edits=edits
        ),
        suggestions=suggestions,
    )
    return CurrentValidation(
        seq=current_seq,
        active=tuple(p for p in persisted if p.status == "active"),
    )
