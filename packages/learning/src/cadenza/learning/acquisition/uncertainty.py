"""Adquisición por incertidumbre: línea base clásica (AL-003)."""

from __future__ import annotations

from collections.abc import Sequence

from ..dataset import TrainingSample
from . import AcquisitionStrategy


class UncertaintyAcquisition(AcquisitionStrategy):
    """Selecciona las muestras con mayor densidad de errores del validador.

    Se incluye como **baseline reproducible** para contrastar el hallazgo negativo
    de AL-003 (la incertidumbre no siempre es efectiva en datos escasos).
    """

    @property
    def strategy_id(self) -> str:
        return "uncertainty"

    def select(self, candidates: Sequence[TrainingSample], budget: int) -> list[TrainingSample]:
        if budget <= 0:
            return []
        ordered = sorted(candidates, key=lambda sample: (-sample.error_density, sample.key()))
        return ordered[:budget]
