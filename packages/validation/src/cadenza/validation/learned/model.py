"""Inferencia de la capa de sugerencias: frecuencias suavizadas con retroceso (ADR-0036 §1, §3).

El artefacto es un JSON con, por familia, los niveles de retroceso (listas de nombres de
rasgos, de lo particular a lo general) y, por nivel, cuántas veces cada clave de contexto
tuvo cada corrección. Se lee sin código de entrenamiento: la API lo carga del registro y lo
inyecta como `SuggestionModel` (el puerto de `cadenza.application`, que este módulo cumple
por estructura sin importarlo).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Any, Final

from cadenza.domain import (
    Anchor,
    EditOp,
    Finding,
    ScoreDocument,
    Severity,
    SuggestedEdit,
    SuggestedFinding,
    SuggestionResult,
)

from .features import (
    FAMILIES,
    FEATURE_VERSION,
    INSERTION,
    NONE_LABEL,
    EventView,
    Position,
    ScoreFeatures,
    decode_accidental,
    decode_duration,
    decode_pitch,
    insertion_label,
    label_of_edit,
)
from .messages import describe_edit, learned_message, ranking_note

ARTIFACT_FORMAT: Final[str] = "cadenza.suggestions"
ARTIFACT_FORMAT_VERSION: Final[int] = 1
MODEL_TYPE: Final[str] = "frequency_backoff"
MAX_SUGGESTIONS: Final[int] = 3
LEARNED_PREFIX: Final[str] = "learned."
# Contextos distintos que se recuerdan entre validaciones: acota la memoria de la API.
_CACHE_LIMIT: Final[int] = 50_000


class InvalidSuggestionArtifact(ValueError):
    """El artefacto no es de la capa, no coincide con su huella o con los rasgos del código."""


@dataclass(frozen=True, slots=True)
class Score:
    """Probabilidad de una corrección y la evidencia que la respalda (para explicarla)."""

    probability: float
    count: int
    support: int


@dataclass(frozen=True, slots=True)
class _Family:
    name: str
    levels: tuple[tuple[str, ...], ...]
    tables: tuple[Mapping[str, Mapping[str, int]], ...]
    labels: tuple[str, ...]
    threshold: float | None
    high_threshold: float | None
    active: bool

    @classmethod
    def from_primitive(cls, name: str, data: Mapping[str, Any]) -> _Family:
        levels = tuple(tuple(str(f) for f in level) for level in data["levels"])
        tables = tuple(
            {
                str(key): {str(label): int(n) for label, n in counts.items()}
                for key, counts in table.items()
            }
            for table in data["tables"]
        )
        if len(levels) != len(tables) or not levels or levels[-1]:
            raise InvalidSuggestionArtifact(
                f"la familia {name} necesita una tabla por nivel y acabar en el nivel vacío"
            )
        labels = sorted(
            {label for table in tables for counts in table.values() for label in counts}
        )
        threshold = data.get("threshold")
        high = data.get("high_threshold")
        return cls(
            name=name,
            levels=levels,
            tables=tables,
            labels=tuple(labels),
            threshold=None if threshold is None else float(threshold),
            high_threshold=None if high is None else float(high),
            active=bool(data.get("active", False)) and threshold is not None,
        )


def context_key(features: Mapping[str, str], level: Sequence[str]) -> str:
    """Clave de contexto de un nivel: los valores de sus rasgos unidos por ``|``."""
    return "|".join(features.get(name, "-") for name in level)


class FrequencyBackoffModel:
    """Capa de sugerencias de frecuencias suavizadas con retroceso (`model_type`
    `frequency_backoff`). Cumple `cadenza.application.SuggestionModel` por estructura."""

    model_type: Final[str] = MODEL_TYPE

    def __init__(
        self,
        artifact: Mapping[str, Any],
        *,
        version: str,
    ) -> None:
        if artifact.get("format") != ARTIFACT_FORMAT:
            raise InvalidSuggestionArtifact("el artefacto no es de la capa de sugerencias")
        if int(artifact.get("format_version", -1)) != ARTIFACT_FORMAT_VERSION:
            raise InvalidSuggestionArtifact(
                f"formato del artefacto no admitido: {artifact.get('format_version')}"
            )
        if artifact.get("model_type") != MODEL_TYPE:
            raise InvalidSuggestionArtifact(f"tipo de modelo: {artifact.get('model_type')}")
        feature_version = int(artifact.get("feature_version", -1))
        if feature_version != FEATURE_VERSION:
            raise InvalidSuggestionArtifact(
                f"el artefacto usa los rasgos v{feature_version} y el código, "
                f"v{FEATURE_VERSION}"
            )
        params = artifact.get("params") or {}
        self.version = version
        self.feature_version = feature_version
        self.alpha = float(params.get("alpha", 1.0))
        self.min_support = int(params.get("min_support", 1))
        families = artifact.get("families") or {}
        self._families: dict[str, _Family] = {
            name: _Family.from_primitive(name, data) for name, data in families.items()
        }
        self._cache: dict[tuple[str, str], dict[str, Score]] = {}

    # -- Carga ---------------------------------------------------------------------------

    @classmethod
    def from_bytes(
        cls, content: bytes, *, version: str, expected_sha256: str | None = None
    ) -> FrequencyBackoffModel:
        """Lee el artefacto y, si se da, comprueba su `sha256` antes de usarlo (ADR-0036 §8)."""
        if expected_sha256 is not None:
            actual = hashlib.sha256(content).hexdigest()
            if actual != expected_sha256:
                raise InvalidSuggestionArtifact(
                    f"el sha256 del artefacto ({actual}) no es el registrado ({expected_sha256})"
                )
        try:
            data = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidSuggestionArtifact(f"el artefacto no es JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise InvalidSuggestionArtifact("el artefacto no es un objeto JSON")
        return cls(data, version=version)

    # -- Probabilidades ------------------------------------------------------------------

    def family(self, name: str) -> _Family | None:
        return self._families.get(name)

    def active_families(self) -> tuple[str, ...]:
        return tuple(name for name, family in self._families.items() if family.active)

    def distribution(self, name: str, features: Mapping[str, str]) -> dict[str, Score]:
        """Probabilidad de cada corrección de la familia en el contexto de `features`.

        La de la clave más específica con al menos `min_support` observaciones, suavizada
        hacia la de su clave más general con peso `alpha`; el nivel vacío (todo) se suaviza
        hacia la uniforme. Vacía si la familia no tiene datos.
        """
        family = self._families.get(name)
        if family is None or not family.labels:
            return {}
        full_key = (
            context_key(features, family.levels[0])
            + "#"
            + "#".join(context_key(features, level) for level in family.levels[1:])
        )
        cached = self._cache.get((name, full_key))
        if cached is not None:
            return cached
        uniform = 1.0 / len(family.labels)
        probabilities = dict.fromkeys(family.labels, uniform)
        count = dict.fromkeys(family.labels, 0)
        support = 0
        for level, table in zip(reversed(family.levels), reversed(family.tables), strict=True):
            counts = table.get(context_key(features, level))
            if counts is None:
                continue
            total = sum(counts.values())
            if total < self.min_support and level:
                continue
            probabilities = {
                label: (counts.get(label, 0) + self.alpha * probabilities[label])
                / (total + self.alpha)
                for label in family.labels
            }
            count = {label: counts.get(label, 0) for label in family.labels}
            support = total
        if support == 0:
            self._cache[(name, full_key)] = {}
            return {}
        result = {
            label: Score(probability=probabilities[label], count=count[label], support=support)
            for label in family.labels
        }
        if len(self._cache) >= _CACHE_LIMIT:
            self._cache.clear()
        self._cache[(name, full_key)] = result
        return result

    def score(self, name: str, features: Mapping[str, str], label: str) -> Score | None:
        """La probabilidad de una corrección concreta, o None si la capa no tiene datos."""
        dist = self.distribution(name, features)
        if not dist:
            return None
        found = dist.get(label)
        if found is not None:
            return found
        # Una corrección que nunca se vio en el entrenamiento: sin evidencia a favor.
        support = next(iter(dist.values())).support
        return Score(probability=0.0, count=0, support=support)

    def best(self, name: str, features: Mapping[str, str]) -> tuple[str, Score] | None:
        """La corrección más probable distinta de «ninguna», o None."""
        dist = self.distribution(name, features)
        candidates = [(label, s) for label, s in dist.items() if label != NONE_LABEL]
        if not candidates:
            return None
        return max(candidates, key=lambda item: (item[1].probability, item[0]))

    def level_of(self, name: str, confidence: float | None) -> str:
        family = self._families.get(name)
        if (
            confidence is not None
            and family is not None
            and family.high_threshold is not None
            and confidence >= family.high_threshold
        ):
            return "high"
        return "medium"

    # -- Sugerir -------------------------------------------------------------------------

    def suggest(self, document: ScoreDocument, findings: Sequence[Finding]) -> SuggestionResult:
        """Ordena los candidatos de las reglas y añade los posibles errores propios (§3)."""
        features = ScoreFeatures.of(document.score)
        ranked = [
            SuggestedFinding(finding=finding, suggestions=self._rank(finding, features))
            for finding in findings
        ]
        excluded_events: set[Position] = set()
        excluded_family: set[tuple[Position, str]] = set()
        for finding in findings:
            excluded_events.add(_position(finding.anchor))
            for candidate in finding.candidates:
                position = _position(candidate.anchor)
                labelled = label_of_edit(
                    candidate.op, candidate.after, features.events.get(position)
                )
                if labelled is not None:
                    excluded_family.add((position, labelled[0]))
        anchors = {_position(a): a for a in document.anchors.anchors()}
        learned: list[SuggestedFinding] = []
        for position, view in features.events.items():
            if position in excluded_events or view.event.hidden:
                continue
            proposal = self._propose(view, excluded_family)
            if proposal is None:
                continue
            family, suggestion = proposal
            anchor = anchors.get(position) or suggestion.anchor
            suggestion = replace(suggestion, anchor=anchor)
            learned.append(
                SuggestedFinding(
                    finding=Finding(
                        anchor=anchor,
                        rule_id=f"{LEARNED_PREFIX}{family}",
                        severity=Severity.WARNING,
                        message=learned_message(family, view, suggestion),
                        suggested_fix=describe_edit(suggestion.op, suggestion.after, view),
                    ),
                    suggestions=(suggestion,),
                )
            )
        return SuggestionResult(findings=(*ranked, *learned))

    def _rank(self, finding: Finding, features: ScoreFeatures) -> tuple[SuggestedEdit, ...]:
        scored: list[tuple[int, float, int, SuggestedEdit]] = []
        for order, candidate in enumerate(finding.candidates):
            position = _position(candidate.anchor)
            view = features.events.get(position)
            family_label: tuple[str, str] | None
            context_features: Mapping[str, str] | None
            if candidate.op is EditOp.INSERT_EVENT:
                after = candidate.after or {}
                label = insertion_label(after.get("kind"), after.get("duration_beats"))
                family_label = None if label is None else (INSERTION, label)
                context_features = features.gap(position)
            else:
                family_label = label_of_edit(candidate.op, candidate.after, view)
                context_features = None if view is None else view.features
            result: Score | None = None
            if family_label is not None and context_features is not None:
                result = self.score(family_label[0], context_features, family_label[1])
            description = describe_edit(candidate.op, candidate.after, view)
            if result is None:
                suggestion = replace(
                    candidate,
                    confidence=None,
                    confidence_level="medium",
                    explanation=candidate.explanation or description,
                    source="rule",
                    model_version=self.version,
                )
                scored.append((1, 0.0, order, suggestion))
                continue
            assert family_label is not None
            suggestion = replace(
                candidate,
                confidence=round(result.probability, 4),
                confidence_level=self.level_of(family_label[0], result.probability),
                explanation=f"{candidate.explanation or description} {ranking_note(result)}",
                source="learned",
                model_version=self.version,
            )
            scored.append((0, -result.probability, order, suggestion))
        scored.sort(key=lambda item: item[:3])
        return tuple(item[3] for item in scored[:MAX_SUGGESTIONS])

    def _propose(
        self, view: EventView, excluded: set[tuple[Position, str]]
    ) -> tuple[str, SuggestedEdit] | None:
        best: tuple[str, SuggestedEdit] | None = None
        for name in FAMILIES:
            family = self._families.get(name)
            if family is None or not family.active or family.threshold is None:
                continue
            if (view.position, name) in excluded:
                continue
            found = self.best(name, view.features)
            if found is None or found[1].probability < family.threshold:
                continue
            edit = _decode(name, found[0], view)
            if edit is None:
                continue
            op, after = edit
            result = found[1]
            suggestion = SuggestedEdit(
                op=op,
                anchor=_anchor_at(view),
                after=after,
                confidence=round(result.probability, 4),
                confidence_level=self.level_of(name, result.probability),
                explanation=f"{describe_edit(op, after, view)} {ranking_note(result)}",
                source="learned",
                model_version=self.version,
            )
            if best is None or (suggestion.confidence or 0) > (best[1].confidence or 0):
                best = (name, suggestion)
        return best


def _position(anchor: Anchor) -> Position:
    return (anchor.part, anchor.staff, anchor.measure, anchor.voice, anchor.event_index)


def _anchor_at(view: EventView) -> Anchor:
    part, staff, measure, voice, index = view.position
    return Anchor(
        part=part,
        staff=staff,
        measure=measure,
        voice=voice,
        event_index=index,
        staff_id=view.staff_id,
    )


def _decode(name: str, label: str, view: EventView) -> tuple[EditOp, dict[str, Any] | None] | None:
    """La edición que corresponde a una etiqueta en el contexto de un evento leído."""
    if name == "delete":
        return (EditOp.DELETE_EVENT, None) if label == "delete" else None
    if name == "accidental":
        accidental = decode_accidental(label, view.context)
        if accidental is None or accidental == view.context.get("accidental"):
            return None
        return (EditOp.SET_ACCIDENTAL, {"accidental": accidental})
    if name == "duration":
        duration = decode_duration(label, view.read.get("duration_beats"))
        if (
            duration is None
            or duration <= 0
            or duration == Fraction(str(view.read.get("duration_beats")))
        ):
            return None
        return (EditOp.SET_DURATION, {"duration_beats": str(duration)})
    if name == "pitch":
        pitch = decode_pitch(label, view.event.pitch, int(view.context.get("key_fifths") or 0))
        if pitch is None or pitch == view.event.pitch:
            return None
        return (EditOp.SET_PITCH, {"pitch": pitch})
    return None
