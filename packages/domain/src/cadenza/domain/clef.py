"""Clave musical como tipo de valor de dominio neutral (ADR-0010)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Clef:
    """Clave musical de un compás o pentagrama (p. ej. sol en 2ª, fa en 4ª)."""

    sign: str
    line: int = 2
    octave_change: int = 0

    def __post_init__(self) -> None:
        if not self.sign:
            raise ValueError("sign must be non-empty")
        if self.line <= 0:
            raise ValueError("line must be positive")

    @classmethod
    def treble(cls) -> Clef:
        """Clave de sol en 2ª línea."""
        return cls(sign="G", line=2)

    @classmethod
    def bass(cls) -> Clef:
        """Clave de fa en 4ª línea."""
        return cls(sign="F", line=4)

    @classmethod
    def alto(cls) -> Clef:
        """Clave de do en 3ª línea."""
        return cls(sign="C", line=3)

    @classmethod
    def tenor(cls) -> Clef:
        """Clave de do en 4ª línea."""
        return cls(sign="C", line=4)

    def to_primitive(self) -> dict[str, Any]:
        return {
            "sign": self.sign,
            "line": self.line,
            "octave_change": self.octave_change,
        }

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> Clef:
        return cls(
            sign=str(data["sign"]),
            line=int(data.get("line", 2)),
            octave_change=int(data.get("octave_change", 0)),
        )
