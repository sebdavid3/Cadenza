"""Hallazgos del motor de validación (Fase 2), anclados a eventos."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from .anchor import Anchor
from .edit import EditEvent
from .projection import translate_anchor


class Severity(StrEnum):
    """Gravedad de un hallazgo de validación."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Finding:
    """Inconsistencia detectada, referida a un evento mediante un ancla."""

    anchor: Anchor
    rule_id: str
    severity: Severity
    message: str
    suggested_fix: str | None = None
    at_seq: int = 0

    def __post_init__(self) -> None:
        if not self.rule_id:
            raise ValueError("rule_id must be non-empty")
        if not self.message:
            raise ValueError("message must be non-empty")
        if self.at_seq < 0:
            raise ValueError("at_seq must be >= 0")

    def to_primitive(self) -> dict[str, Any]:
        return {
            "anchor": self.anchor.to_primitive(),
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
            "suggested_fix": self.suggested_fix,
            "at_seq": self.at_seq,
        }

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> Finding:
        return cls(
            anchor=Anchor.from_primitive(data["anchor"]),
            rule_id=str(data["rule_id"]),
            severity=Severity(data["severity"]),
            message=str(data["message"]),
            suggested_fix=None if data.get("suggested_fix") is None else str(data["suggested_fix"]),
            at_seq=int(data.get("at_seq", 0)),
        )


def translate_finding(
    finding: Finding,
    to_seq: int,
    edits: Iterable[EditEvent],
) -> Finding | None:
    """Traduce un finding desde su estado `at_seq` hasta el estado `to_seq`.

    Si el evento referenciado fue borrado por alguna edición en el intervalo, devuelve None.
    """
    new_anchor = translate_anchor(finding.anchor, finding.at_seq, to_seq, edits)
    if new_anchor is None:
        return None
    return replace(finding, anchor=new_anchor, at_seq=to_seq)
