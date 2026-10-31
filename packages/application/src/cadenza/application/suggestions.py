"""La capa de sugerencias en los casos de uso (ADR-0036 §3, §4, §5).

Los casos de uso que validan combinan reglas y capa: primero `validator.validate(doc)` y
después `model.suggest(doc, findings)`. Sin capa, los hallazgos son exactamente los de las
reglas y no llevan sugerencias, tampoco los candidatos de las reglas (§3.4). Antes de
guardarse, cada sugerencia pasa `validate_after` y se le fija `before` con la instantánea del
servidor sobre el estado `at_seq` (ADR-0017): la que no pasa se descarta.

Qué se muestra lo decide una política (`SuggestionPolicy`, enmienda 19): la API envuelve la
capa con `PolicySuggestionModel`, que filtra su respuesta por nivel de confianza y familia
antes de ese filtro, y `exp_14` puede medir la misma política por el mismo camino.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
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
    SuggestedFinding,
    SuggestionResult,
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
            before = snapshot_before(document.score, edit.anchor, edit.op, edit.after)
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


# --- Qué se muestra (ADR-0036, enmienda 19) -------------------------------------------------

# Las familias de una sugerencia: las de los posibles errores propios (§3.2) y las inserciones,
# que solo llegan como candidatos de las reglas (§1).
SUGGESTION_FAMILIES: Final[tuple[str, ...]] = (
    "accidental",
    "duration",
    "pitch",
    "delete",
    "insertion",
)
_FAMILY_OF_OP: Final[Mapping[EditOp, str]] = {
    EditOp.SET_ACCIDENTAL: "accidental",
    EditOp.SET_DURATION: "duration",
    EditOp.SET_PITCH: "pitch",
    EditOp.DELETE_EVENT: "delete",
    EditOp.INSERT_EVENT: "insertion",
}
# Del menor al mayor. Un candidato sin nivel cuenta como `medium`, como uno sin puntuar
# (enmienda 6).
CONFIDENCE_ORDER: Final[tuple[str, ...]] = ("medium", "high")


def suggestion_family(edit: SuggestedEdit) -> str | None:
    """La familia de una sugerencia, por su operación (None si no es de ninguna)."""
    return _FAMILY_OF_OP.get(edit.op)


@dataclass(frozen=True, slots=True)
class SuggestionPolicy:
    """Qué sugerencias se muestran: las de nivel de confianza al menos `min_level` y de una
    familia de `families`. Lo decide el responsable (#244) y se configura en la API."""

    min_level: str
    families: frozenset[str]

    def __post_init__(self) -> None:
        if self.min_level not in CONFIDENCE_ORDER:
            raise ValueError(
                f"nivel de confianza mínimo no válido: {self.min_level!r} "
                f"(admite {', '.join(CONFIDENCE_ORDER)})"
            )
        if not self.families:
            raise ValueError("la política de sugerencias necesita al menos una familia")
        unknown = sorted(self.families - set(SUGGESTION_FAMILIES))
        if unknown:
            raise ValueError(
                f"familias de sugerencias no válidas: {', '.join(unknown)} "
                f"(admite {', '.join(SUGGESTION_FAMILIES)})"
            )

    @classmethod
    def parse(cls, min_level: str, families: str) -> SuggestionPolicy:
        """La política a partir de su configuración: un nivel y las familias separadas por
        comas, sin distinguir mayúsculas. ValueError si no es válida."""
        names = frozenset(name.strip().lower() for name in families.split(",") if name.strip())
        return cls(min_level=min_level.strip().lower(), families=names)

    def shows(self, edit: SuggestedEdit) -> bool:
        level = edit.confidence_level or CONFIDENCE_ORDER[0]
        if level not in CONFIDENCE_ORDER:
            return False
        return (
            CONFIDENCE_ORDER.index(level) >= CONFIDENCE_ORDER.index(self.min_level)
            and suggestion_family(edit) in self.families
        )

    def apply(self, result: SuggestionResult) -> SuggestionResult:
        """La respuesta de la capa con solo lo que se muestra.

        Los hallazgos de las reglas siguen todos, en su orden, aunque se queden sin
        sugerencias; un posible error propio de una familia no permitida, o sin ninguna
        sugerencia que pase, no se emite.
        """
        kept: list[SuggestedFinding] = []
        for item in result.findings:
            shown = tuple(edit for edit in item.suggestions if self.shows(edit))
            if _is_learned(item.finding):
                family = item.finding.rule_id.removeprefix(LEARNED_PREFIX)
                if family not in self.families or not shown:
                    continue
            kept.append(SuggestedFinding(finding=item.finding, suggestions=shown))
        return SuggestionResult(findings=tuple(kept))


class PolicySuggestionModel:
    """La capa con la política de qué se muestra: cumple el puerto `SuggestionModel` y filtra
    la respuesta del modelo antes del filtro de admisibilidad de `suggest`. El modelo no
    cambia: su versión es la de las sugerencias y la de la procedencia."""

    def __init__(self, model: SuggestionModel, policy: SuggestionPolicy) -> None:
        self._model = model
        self._policy = policy

    @property
    def version(self) -> str:
        return self._model.version

    @property
    def model(self) -> SuggestionModel:
        return self._model

    @property
    def policy(self) -> SuggestionPolicy:
        return self._policy

    def suggest(self, document: ScoreDocument, findings: Sequence[Finding]) -> SuggestionResult:
        return self._policy.apply(self._model.suggest(document, findings))


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
