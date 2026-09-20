"""Adquisición híbrida: densidad de errores + magnitud de corrección + diversidad.

Es la **apuesta principal** de Cadenza (ADR-0008): usa la señal del validador
como *proxy* de incertidumbre y la mitiga con diversidad.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..dataset import TrainingSample
from . import AcquisitionStrategy, feature_distance, sorted_candidates


class HybridAcquisition(AcquisitionStrategy):
    def __init__(
        self,
        *,
        error_weight: float = 0.5,
        magnitude_weight: float = 0.3,
        diversity_weight: float = 0.2,
    ) -> None:
        self._error_weight = error_weight
        self._magnitude_weight = magnitude_weight
        self._diversity_weight = diversity_weight

    @property
    def strategy_id(self) -> str:
        return "hybrid"

    def select(self, candidates: Sequence[TrainingSample], budget: int) -> list[TrainingSample]:
        if budget <= 0 or not candidates:
            return []

        remaining = sorted_candidates(candidates)
        max_error = max(sample.error_density for sample in remaining) or 1.0
        max_magnitude = max(sample.correction_magnitude for sample in remaining) or 1.0
        max_distance = self._max_distance(remaining) or 1.0

        def utility(sample: TrainingSample) -> float:
            return self._error_weight * (
                sample.error_density / max_error
            ) + self._magnitude_weight * (sample.correction_magnitude / max_magnitude)

        selected: list[TrainingSample] = []
        while remaining and len(selected) < budget:
            best_index = 0
            best_score = -1.0
            for index, candidate in enumerate(remaining):
                diversity = (
                    min(feature_distance(candidate, chosen) for chosen in selected)
                    if selected
                    else max_distance
                )
                score = utility(candidate) + self._diversity_weight * (diversity / max_distance)
                if score > best_score:
                    best_score = score
                    best_index = index
            selected.append(remaining.pop(best_index))
        return selected

    @staticmethod
    def _max_distance(samples: Sequence[TrainingSample]) -> float:
        maximum = 0.0
        for index, left in enumerate(samples):
            for right in samples[index + 1 :]:
                maximum = max(maximum, feature_distance(left, right))
        return maximum
