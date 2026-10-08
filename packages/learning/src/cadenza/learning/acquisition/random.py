"""Estrategia de adquisición aleatoria (baseline pasivo / control experimental)."""

from __future__ import annotations

import random
from collections.abc import Sequence

from ..dataset import TrainingSample
from . import AcquisitionStrategy


class RandomAcquisition(AcquisitionStrategy):
    """Muestreo aleatorio uniforme determinista con semilla."""

    def __init__(self, seed: int = 42) -> None:
        self._seed = seed

    @property
    def strategy_id(self) -> str:
        return "random"

    def select(self, candidates: Sequence[TrainingSample], budget: int) -> list[TrainingSample]:
        if budget <= 0 or not candidates:
            return []
        items = list(candidates)
        # Orden canónico determinista previo al shuffle para que el resultado sea
        # idéntico sin importar el orden en que se entregaron los candidatos.
        items.sort(key=TrainingSample.key)
        rng = random.Random(self._seed)
        rng.shuffle(items)
        return items[:budget]
