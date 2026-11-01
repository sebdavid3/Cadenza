"""Signatura de compás como valor de dominio neutral.

Es metadato de `Measure`, no un evento: la métrica es una propiedad del compás
que la validación (M2) y la edición (M3) necesitan sin depender de `music21`.

`symbol` es la grafía de la indicación (ADR-0044): ``common`` (C) para 4/4 y ``cut`` (¢) para
2/2, o None si se escribe con números. Es grafía, no métrica: la igualdad y el hash solo miran
``beats`` y ``beat_type`` (C y 4/4 son la misma métrica), como las marcas de notación, que
tampoco entran en las métricas de los experimentos (ADR-0031 §6). Lo que compara la grafía
(exportar, cambiar el compás) usa `same_notation`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Final

COMMON: Final[str] = "common"
CUT: Final[str] = "cut"

# La métrica que escribe cada símbolo.
SYMBOL_METERS: Final[dict[str, tuple[int, int]]] = {COMMON: (4, 4), CUT: (2, 2)}


@dataclass(frozen=True, slots=True)
class TimeSignature:
    """Métrica de un compás, p. ej. ``4/4`` o ``6/8``, y su símbolo (C o ¢) si lo lleva."""

    beats: int
    beat_type: int
    symbol: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.beats <= 0:
            raise ValueError("beats must be > 0")
        if self.beat_type <= 0 or self.beat_type & (self.beat_type - 1) != 0:
            raise ValueError("beat_type must be a positive power of two")
        if self.symbol is not None:
            meter = SYMBOL_METERS.get(self.symbol)
            if meter is None:
                raise ValueError(f"symbol must be 'common', 'cut' or None, got {self.symbol!r}")
            if meter != (self.beats, self.beat_type):
                raise ValueError(
                    f"symbol {self.symbol!r} must be {meter[0]}/{meter[1]}, "
                    f"got {self.beats}/{self.beat_type}"
                )

    @property
    def quarter_length(self) -> Fraction:
        """Duración del compás expresada en negras (beats de quarter note)."""

        return Fraction(self.beats * 4, self.beat_type)

    def same_notation(self, other: TimeSignature | None) -> bool:
        """Misma métrica y misma grafía: C y 4/4 son la misma métrica, pero no se escriben igual."""

        return other is not None and self == other and self.symbol == other.symbol

    def __str__(self) -> str:
        # La métrica en números, también con símbolo: es lo que leen los rasgos de la capa de
        # sugerencias (ADR-0036) y el corpus de correcciones.
        return f"{self.beats}/{self.beat_type}"

    def to_primitive(self) -> dict[str, Any]:
        primitive: dict[str, Any] = {"beats": self.beats, "beat_type": self.beat_type}
        # Sin símbolo no se serializa: un compás con números se guarda como antes de #236.
        if self.symbol is not None:
            primitive["symbol"] = self.symbol
        return primitive

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> TimeSignature:
        symbol = data.get("symbol")
        return cls(
            beats=int(data["beats"]),
            beat_type=int(data["beat_type"]),
            symbol=None if symbol is None else str(symbol),
        )


def same_time_notation(a: TimeSignature | None, b: TimeSignature | None) -> bool:
    """Dos indicaciones de compás (o su ausencia) iguales en métrica y en grafía."""

    if a is None or b is None:
        return a is None and b is None
    return a.same_notation(b)
