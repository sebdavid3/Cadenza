"""Adquisición por incertidumbre: línea base clásica y variante neuro-simbólica.

Referencia: AL-003, INV-0001.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..dataset import TrainingSample
from . import AcquisitionStrategy


class ErrorDensityAcquisition(AcquisitionStrategy):
    """Selecciona las muestras con mayor densidad de errores del validador de teoría musical.

    Opera como un estimador neuro-simbólico de incertidumbre ante la ausencia de
    probabilidades posteriores calibradas en el decodificador de HOMR (ver INV-0001).
    """

    @property
    def strategy_id(self) -> str:
        return "error_density"

    def select(self, candidates: Sequence[TrainingSample], budget: int) -> list[TrainingSample]:
        if budget <= 0:
            return []
        ordered = sorted(candidates, key=lambda sample: (-sample.error_density, sample.key()))
        return ordered[:budget]


class UncertaintyAcquisition(ErrorDensityAcquisition):
    """Línea base clásica de incertidumbre (AL-003).

    Mantiene el identificador 'uncertainty' para reproducibilidad de los experimentos
    previos, utilizando la densidad de errores del validador como señal de incertidumbre.
    """

    @property
    def strategy_id(self) -> str:
        return "uncertainty"
