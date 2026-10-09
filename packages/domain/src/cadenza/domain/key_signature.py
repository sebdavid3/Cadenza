"""Armadura de clave como tipo de valor de dominio neutral (ADR-0010)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class KeySignature:
    """Armadura de clave de un compás, expresada en quintas respecto a Do mayor.

    `fifths > 0`: número de sostenidos (p. ej. 1 = Sol mayor / Mi menor).
    `fifths < 0`: número de bemoles (p. ej. -1 = Fa mayor / Re menor).
    `fifths == 0`: sin alteraciones (Do mayor / La menor).
    """

    fifths: int
    mode: str | None = None

    def __post_init__(self) -> None:
        if not (-7 <= self.fifths <= 7):
            raise ValueError(f"fifths must be between -7 and 7, got {self.fifths}")

    def to_primitive(self) -> dict[str, Any]:
        return {
            "fifths": self.fifths,
            "mode": self.mode,
        }

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> KeySignature:
        mode = data.get("mode")
        return cls(
            fifths=int(data["fifths"]),
            mode=str(mode) if mode is not None else None,
        )
