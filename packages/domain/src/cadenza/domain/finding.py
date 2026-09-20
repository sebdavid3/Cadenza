"""Hallazgos del motor de validación (Fase 2), anclados a eventos."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .anchor import Anchor


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

    def __post_init__(self) -> None:
        if not self.rule_id:
            raise ValueError("rule_id must be non-empty")
        if not self.message:
            raise ValueError("message must be non-empty")

    def to_primitive(self) -> dict[str, Any]:
        return {
            "anchor": self.anchor.to_primitive(),
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
            "suggested_fix": self.suggested_fix,
        }

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> Finding:
        return cls(
            anchor=Anchor.from_primitive(data["anchor"]),
            rule_id=str(data["rule_id"]),
            severity=Severity(data["severity"]),
            message=str(data["message"]),
            suggested_fix=None if data.get("suggested_fix") is None else str(data["suggested_fix"]),
        )
