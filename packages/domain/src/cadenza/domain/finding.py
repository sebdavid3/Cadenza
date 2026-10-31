"""Hallazgos del motor de validación (Fase 2), anclados a eventos."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from .anchor import Anchor
from .edit import EditEvent
from .projection import translate_anchor
from .suggestion import SuggestedEdit


class Severity(StrEnum):
    """Gravedad de un hallazgo de validación."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Finding:
    """Inconsistencia detectada, referida a un evento mediante un ancla.

    `candidates` son los arreglos que la regla sabe que cuadran (ADR-0036 §3): la capa de
    sugerencias los ordena. Vacíos por defecto y, vacíos, no se serializan, así que los
    hallazgos guardados antes se leen igual.
    """

    anchor: Anchor
    rule_id: str
    severity: Severity
    message: str
    suggested_fix: str | None = None
    at_seq: int = 0
    candidates: tuple[SuggestedEdit, ...] = ()

    def __post_init__(self) -> None:
        if not self.rule_id:
            raise ValueError("rule_id must be non-empty")
        if not self.message:
            raise ValueError("message must be non-empty")
        if self.at_seq < 0:
            raise ValueError("at_seq must be >= 0")
        object.__setattr__(self, "candidates", tuple(self.candidates))

    def to_primitive(self) -> dict[str, Any]:
        primitive: dict[str, Any] = {
            "anchor": self.anchor.to_primitive(),
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
            "suggested_fix": self.suggested_fix,
            "at_seq": self.at_seq,
        }
        if self.candidates:
            primitive["candidates"] = [c.to_primitive() for c in self.candidates]
        return primitive

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> Finding:
        return cls(
            anchor=Anchor.from_primitive(data["anchor"]),
            rule_id=str(data["rule_id"]),
            severity=Severity(data["severity"]),
            message=str(data["message"]),
            suggested_fix=None if data.get("suggested_fix") is None else str(data["suggested_fix"]),
            at_seq=int(data.get("at_seq", 0)),
            candidates=tuple(
                SuggestedEdit.from_primitive(item) for item in data.get("candidates") or ()
            ),
        )


@dataclass(frozen=True, slots=True)
class SuggestedFinding:
    """Un hallazgo con las sugerencias que lleva, ordenadas por confianza (ADR-0036 §4)."""

    finding: Finding
    suggestions: tuple[SuggestedEdit, ...] = ()


@dataclass(frozen=True, slots=True)
class SuggestionResult:
    """Lo que devuelve la capa: los hallazgos de las reglas, en su orden, con sus sugerencias,
    y detrás los posibles errores propios (`learned.*`, ADR-0036 §3)."""

    findings: tuple[SuggestedFinding, ...] = ()


def translate_finding(
    finding: Finding,
    to_seq: int,
    edits: Iterable[EditEvent],
) -> Finding | None:
    """Traduce un finding desde su estado `at_seq` hasta el estado `to_seq`.

    Si el evento referenciado fue borrado por alguna edición en el intervalo, devuelve None.
    Sus candidatos se traducen igual; el que apunta a un evento borrado se pierde.
    """
    edit_list = list(edits)
    new_anchor = translate_anchor(finding.anchor, finding.at_seq, to_seq, edit_list)
    if new_anchor is None:
        return None
    candidates: list[SuggestedEdit] = []
    for candidate in finding.candidates:
        moved = translate_anchor(candidate.anchor, finding.at_seq, to_seq, edit_list)
        if moved is not None:
            candidates.append(replace(candidate, anchor=moved))
    return replace(finding, anchor=new_anchor, at_seq=to_seq, candidates=tuple(candidates))
