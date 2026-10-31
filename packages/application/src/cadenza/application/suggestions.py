"""La capa de sugerencias en los casos de uso (ADR-0036 §3, §4, §5).

Los casos de uso que validan combinan reglas y capa: primero `validator.validate(doc)` y
después `model.suggest(doc, findings)`. Sin capa, los hallazgos son exactamente los de las
reglas y no llevan sugerencias, tampoco los candidatos de las reglas (§3.4). Antes de
guardarse, cada sugerencia pasa `validate_after` y se le fija `before` con la instantánea del
servidor sobre el estado `at_seq` (ADR-0017): la que no pasa se descarta.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any, Final

from cadenza.domain import (
    Anchor,
    EditEvent,
    EditOp,
    Finding,
    InvalidEditPayload,
    ScoreDocument,
    SuggestedEdit,
    normalize_accidental,
    snapshot_before,
    translate_anchor,
    validate_after,
)

from .ports.session_repository import NewSuggestion, PersistedSuggestion
from .ports.suggestion_model import SuggestionModel

logger = logging.getLogger("cadenza.application.suggestions")

MAX_SUGGESTIONS_PER_FINDING: Final[int] = 3
REJECTED: Final[str] = "rejected"
ACCEPTED: Final[str] = "accepted"
LEARNED_PREFIX: Final[str] = "learned."


def anchors_match_position(a: Anchor, b: Anchor) -> bool:
    """Dos anclas apuntan al mismo sitio (sin mirar caja ni confianza)."""
    return (a.part, a.staff, a.measure, a.voice, a.event_index) == (
        b.part,
        b.staff,
        b.measure,
        b.voice,
        b.event_index,
    )


def was_event_modified_after(
    anchor: Anchor,
    at_seq: int,
    when: datetime | None,
    edits: Sequence[EditEvent],
    *,
    inclusive: bool = False,
) -> bool:
    """Si alguna edición posterior a `when` tocó el evento de `anchor` (relativo a `at_seq`).

    Con `inclusive`, una edición del mismo instante cuenta como posterior: el reloj puede dar
    el mismo microsegundo a una respuesta y a la edición que la sigue.
    """
    if when is None:
        return False
    moment = when if when.tzinfo is not None else when.replace(tzinfo=UTC)
    for edit in edits:
        created = (
            edit.created_at
            if edit.created_at.tzinfo is not None
            else edit.created_at.replace(tzinfo=UTC)
        )
        if created > moment or (inclusive and created == moment):
            before_edit = translate_anchor(anchor, at_seq, edit.seq - 1, edits)
            if before_edit is not None and anchors_match_position(before_edit, edit.anchor):
                return True
    return False


def normalize_after(op: EditOp, after: Mapping[str, Any] | None) -> Any:
    """El `after` de una edición en forma comparable: la normalización de `validate_after`
    (una duración como fracción, una alteración en su forma canónica)."""
    if after is None:
        return None
    data = dict(after)
    if op is EditOp.SET_DURATION or op is EditOp.INSERT_EVENT:
        raw = data.get("duration_beats")
        if raw is not None:
            data["duration_beats"] = str(Fraction(str(raw)))
    if op is EditOp.SET_ACCIDENTAL:
        data["accidental"] = normalize_accidental(data.get("accidental"))
    if op is EditOp.INSERT_EVENT:
        # Sin los valores que equivalen a no darlos (None, False, una lista vacía); un 0 sí
        # cuenta (`voice: 0`).
        data = {key: value for key, value in data.items() if not _is_absent(value)}
    return data


def _is_absent(value: object) -> bool:
    if value is None or value is False:
        return True
    return isinstance(value, list | tuple | dict) and len(value) == 0


def same_after(op: EditOp, a: Mapping[str, Any] | None, b: Mapping[str, Any] | None) -> bool:
    try:
        return bool(normalize_after(op, a) == normalize_after(op, b))
    except (ValueError, ZeroDivisionError, TypeError):
        return False


def _admissible(
    document: ScoreDocument, edits: Sequence[SuggestedEdit]
) -> tuple[SuggestedEdit, ...]:
    kept: list[SuggestedEdit] = []
    seen: list[tuple[EditOp, Anchor, Any]] = []
    for edit in edits:
        try:
            validate_after(document.score, edit.anchor, edit.op, edit.after)
            before = snapshot_before(document.score, edit.anchor, edit.op)
            key = (edit.op, edit.anchor, normalize_after(edit.op, edit.after))
        except (InvalidEditPayload, IndexError, ValueError, TypeError, ZeroDivisionError):
            continue
        if any(
            op is key[0] and anchors_match_position(anchor, key[1]) and after == key[2]
            for op, anchor, after in seen
        ):
            continue
        seen.append(key)
        kept.append(replace(edit, before=before))
        if len(kept) == MAX_SUGGESTIONS_PER_FINDING:
            break
    return tuple(kept)


def _is_learned(finding: Finding) -> bool:
    return finding.rule_id.startswith(LEARNED_PREFIX)


def suggest(
    document: ScoreDocument,
    findings: Sequence[Finding],
    model: SuggestionModel | None,
) -> list[tuple[Finding, tuple[SuggestedEdit, ...]]]:
    """Los hallazgos con sus sugerencias admisibles, y detrás los de la capa.

    Sin capa, o si la capa falla, los hallazgos de las reglas sin sugerencias: la validación
    nunca depende de que la capa funcione (§3.4).
    """
    if model is None:
        return [(finding, ()) for finding in findings]
    try:
        result = model.suggest(document, findings)
    except Exception:
        logger.exception("suggestion_layer_failed version=%s", getattr(model, "version", None))
        return [(finding, ()) for finding in findings]
    ruled = [item.finding for item in result.findings if not _is_learned(item.finding)]
    if ruled != list(findings):
        # El puerto debe devolver los hallazgos de las reglas, en su orden: si no, ninguno se
        # pierde en silencio y se valida sin capa.
        logger.error("suggestion_layer_dropped_rule_findings version=%s", model.version)
        return [(finding, ()) for finding in findings]
    suggested: list[tuple[Finding, tuple[SuggestedEdit, ...]]] = []
    for item in result.findings:
        admissible = _admissible(document, item.suggestions)
        # Un posible error propio existe por su arreglo: sin arreglo admisible, no se muestra.
        if _is_learned(item.finding) and not admissible:
            continue
        suggested.append((item.finding, admissible))
    return suggested


def with_inherited_rejections(
    suggested: Sequence[tuple[Finding, tuple[SuggestedEdit, ...]]],
    rejected: Sequence[PersistedSuggestion],
    *,
    current_seq: int,
    edits: Sequence[EditEvent],
) -> list[list[NewSuggestion]]:
    """Las sugerencias a guardar, heredando `rejected` de la validación vigente (§4).

    Una sugerencia hereda el rechazo de otra con la misma `op` y el mismo `after`, cuya ancla,
    traducida al estado actual, es la suya, y cuyo evento no se ha modificado desde el
    rechazo. Cada rechazo se hereda una vez.
    """
    # Solo las que mostró la validación vigente: una fila desvinculada es de una validación
    # anterior del mismo estado, que ya no manda (ADR-0035, ADR-0036 §4).
    pending = [s for s in rejected if s.response == REJECTED and s.finding_id is not None]
    used: set[int] = set()
    stored: list[list[NewSuggestion]] = []
    for _, edits_of_finding in suggested:
        news: list[NewSuggestion] = []
        for edit in edits_of_finding:
            inherited: PersistedSuggestion | None = None
            for old in pending:
                if old.id in used or old.op != edit.op.value:
                    continue
                if not same_after(edit.op, old.after, edit.after):
                    continue
                old_anchor = Anchor.from_primitive(old.anchor)
                moved = translate_anchor(old_anchor, old.at_seq, current_seq, edits)
                if moved is None or not anchors_match_position(moved, edit.anchor):
                    continue
                if was_event_modified_after(
                    old_anchor, old.at_seq, old.responded_at, edits, inclusive=True
                ):
                    continue
                inherited = old
                used.add(old.id)
                break
            news.append(NewSuggestion(edit=edit, inherited=inherited))
        stored.append(news)
    return stored
