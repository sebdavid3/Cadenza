"""Signatura de compás como valor de dominio neutral.

Es metadato de `Measure`, no un evento: la métrica es una propiedad del compás
que la validación (M2) y la edición (M3) necesitan sin depender de `music21`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any


@dataclass(frozen=True, slots=True)
class TimeSignature:
    """Métrica de un compás, p. ej. ``4/4`` o ``6/8``."""

    beats: int
    beat_type: int

    def __post_init__(self) -> None:
        if self.beats <= 0:
            raise ValueError("beats must be > 0")
        if self.beat_type <= 0 or self.beat_type & (self.beat_type - 1) != 0:
            raise ValueError("beat_type must be a positive power of two")

    @property
    def quarter_length(self) -> Fraction:
        """Duración del compás expresada en negras (beats de quarter note)."""

        return Fraction(self.beats * 4, self.beat_type)

    def __str__(self) -> str:
        return f"{self.beats}/{self.beat_type}"

    def to_primitive(self) -> dict[str, Any]:
        return {"beats": self.beats, "beat_type": self.beat_type}

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> TimeSignature:
        return cls(beats=int(data["beats"]), beat_type=int(data["beat_type"]))
