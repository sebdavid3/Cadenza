"""Puerto `AcquisitionStrategy`: selección de muestras de mayor valor (ADR-0008)."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..dataset import TrainingSample


class AcquisitionStrategy(ABC):
    """Estrategia de adquisición intercambiable y comparable experimentalmente."""

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Identificador estable de la estrategia."""

    @abstractmethod
    def select(self, candidates: Sequence[TrainingSample], budget: int) -> list[TrainingSample]:
        """Selecciona hasta `budget` muestras, de forma determinista."""


def feature_distance(left: TrainingSample, right: TrainingSample) -> float:
    """Distancia euclídea entre los vectores de features de dos muestras."""

    if len(left.features) != len(right.features):
        return 0.0
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left.features, right.features, strict=True)))


def sorted_candidates(candidates: Sequence[TrainingSample]) -> list[TrainingSample]:
    return sorted(candidates, key=TrainingSample.key)
