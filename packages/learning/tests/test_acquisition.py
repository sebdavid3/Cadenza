"""Pruebas de las estrategias de adquisición (puerto intercambiable)."""

from __future__ import annotations

from cadenza.learning import (
    DiversityAcquisition,
    HybridAcquisition,
    TrainingSample,
    UncertaintyAcquisition,
)

from .support import make_anchor


def _sample(
    event_index: int, error_density: float, magnitude: float, features: tuple[float, ...]
) -> TrainingSample:
    return TrainingSample(
        document_id="doc-1",
        anchor=make_anchor(event_index),
        before_pitch="C4",
        after_pitch="D4",
        correction_magnitude=magnitude,
        error_density=error_density,
        features=features,
    )


def _candidates() -> list[TrainingSample]:
    return [
        _sample(0, 0.1, 1.0, (0.0, 0.0)),
        _sample(1, 0.9, 1.0, (1.0, 0.0)),
        _sample(2, 0.2, 5.0, (0.0, 10.0)),
        _sample(3, 0.2, 1.0, (10.0, 0.0)),
    ]


def test_uncertainty_picks_highest_error_density() -> None:
    selected = UncertaintyAcquisition().select(_candidates(), 1)
    assert [sample.anchor.event_index for sample in selected] == [1]


def test_diversity_selects_spread_samples() -> None:
    selected = DiversityAcquisition().select(_candidates(), 2)
    assert len(selected) == 2
    assert len({sample.anchor.event_index for sample in selected}) == 2


def test_hybrid_is_deterministic_and_respects_budget() -> None:
    strategy = HybridAcquisition()
    assert strategy.select(_candidates(), 3) == strategy.select(_candidates(), 3)
    assert len(strategy.select(_candidates(), 3)) == 3


def test_strategies_handle_empty_and_zero_budget() -> None:
    strategies = (UncertaintyAcquisition(), DiversityAcquisition(), HybridAcquisition())
    for strategy in strategies:
        assert strategy.select([], 5) == []
        assert strategy.select(_candidates(), 0) == []


def test_strategy_ids() -> None:
    assert UncertaintyAcquisition().strategy_id == "uncertainty"
    assert DiversityAcquisition().strategy_id == "diversity"
    assert HybridAcquisition().strategy_id == "hybrid"
