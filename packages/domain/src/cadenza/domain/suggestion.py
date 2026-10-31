"""Sugerencia estructurada: una edición propuesta, no aplicada (ADR-0036 §4).

Una regla que sabe qué arreglos cuadran los entrega como candidatos de su `Finding`, y la
capa de sugerencias los ordena o propone los suyos. Aplicar una sugerencia es una edición
normal de la persona (ADR-0012): aquí solo se describe.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from .anchor import Anchor
from .edit import EditOp

CONFIDENCE_LEVELS: Final[frozenset[str]] = frozenset({"high", "medium"})
SUGGESTION_SOURCES: Final[frozenset[str]] = frozenset({"rule", "learned"})


def _freeze(value: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    return None if value is None else MappingProxyType(dict(value))


def _fingerprint(value: Mapping[str, Any] | None) -> int | None:
    if value is None:
        return None
    return hash(repr(sorted(value.items(), key=lambda item: item[0])))


@dataclass(frozen=True, slots=True)
class SuggestedEdit:
    """Una edición propuesta sobre el estado `at_seq` de su hallazgo (ADR-0011).

    `op`, `anchor`, `before` y `after` son los mismos datos que `POST /sessions/{id}/edits`.
    `confidence` es la probabilidad que da la capa (de 0 a 1) o None si no la pudo puntuar;
    `source` dice si la ordenó o la propuso la capa (`learned`) o si es un candidato de una
    regla sin puntuar (`rule`). `explanation` va en lenguaje musical.
    """

    op: EditOp
    anchor: Anchor
    after: Mapping[str, Any] | None
    before: Mapping[str, Any] | None = None
    confidence: float | None = None
    confidence_level: str | None = None
    explanation: str = ""
    source: str = "rule"
    model_version: str | None = None

    def __post_init__(self) -> None:
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")
        if self.confidence_level is not None and self.confidence_level not in CONFIDENCE_LEVELS:
            raise ValueError(f"confidence_level must be high or medium: {self.confidence_level}")
        if self.source not in SUGGESTION_SOURCES:
            raise ValueError(f"source must be rule or learned: {self.source}")
        object.__setattr__(self, "after", _freeze(self.after))
        object.__setattr__(self, "before", _freeze(self.before))

    def __hash__(self) -> int:
        return hash(
            (
                self.op,
                self.anchor,
                _fingerprint(self.after),
                _fingerprint(self.before),
                self.confidence,
                self.confidence_level,
                self.explanation,
                self.source,
                self.model_version,
            )
        )

    def to_primitive(self) -> dict[str, Any]:
        return {
            "op": self.op.value,
            "anchor": self.anchor.to_primitive(),
            "after": None if self.after is None else dict(self.after),
            "before": None if self.before is None else dict(self.before),
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
            "explanation": self.explanation,
            "source": self.source,
            "model_version": self.model_version,
        }

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> SuggestedEdit:
        after = data.get("after")
        before = data.get("before")
        confidence = data.get("confidence")
        level = data.get("confidence_level")
        version = data.get("model_version")
        return cls(
            op=EditOp(data["op"]),
            anchor=Anchor.from_primitive(data["anchor"]),
            after=None if after is None else dict(after),
            before=None if before is None else dict(before),
            confidence=None if confidence is None else float(confidence),
            confidence_level=None if level is None else str(level),
            explanation=str(data.get("explanation") or ""),
            source=str(data.get("source") or "rule"),
            model_version=None if version is None else str(version),
        )
