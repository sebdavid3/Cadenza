"""Adquisición por diversidad: cobertura del espacio de features (farthest-point)."""

from __future__ import annotations

from collections.abc import Sequence

from ..dataset import TrainingSample
from . import AcquisitionStrategy, feature_distance, sorted_candidates


class DiversityAcquisition(AcquisitionStrategy):
    """Selección voraz del punto más lejano, determinista ante empates."""

    @property
    def strategy_id(self) -> str:
        return "diversity"

    def select(self, candidates: Sequence[TrainingSample], budget: int) -> list[TrainingSample]:
        if budget <= 0 or not candidates:
            return []

        remaining = sorted_candidates(candidates)
        selected = [remaining.pop(0)]
        while remaining and len(selected) < budget:
            best_index = 0
            best_score = -1.0
            for index, candidate in enumerate(remaining):
                score = min(feature_distance(candidate, chosen) for chosen in selected)
                if score > best_score:
                    best_score = score
                    best_index = index
            selected.append(remaining.pop(best_index))
        return selected
