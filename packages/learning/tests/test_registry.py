"""Pruebas del Model Registry y la promoción gobernada por umbral."""

from __future__ import annotations

import pytest
from cadenza.learning import (
    EvaluationMetrics,
    ModelRegistry,
    ModelVersion,
    PromotionRejected,
    PromotionThreshold,
)

THRESHOLD = PromotionThreshold(max_ser=0.2, max_omr_ned=0.15)


def _version(version: str, ser: float, omr_ned: float) -> ModelVersion:
    return ModelVersion(
        version=version,
        artifact_hash="artifact",
        dataset_hash="dataset",
        config_hash="config",
        metrics=EvaluationMetrics(ser=ser, omr_ned=omr_ned),
    )


def test_promotes_version_within_threshold() -> None:
    registry = ModelRegistry(THRESHOLD)
    registry.register(_version("v1", 0.1, 0.1))

    promoted = registry.promote("v1")

    assert promoted.promoted
    assert registry.active() == promoted


def test_rejects_version_above_threshold() -> None:
    registry = ModelRegistry(THRESHOLD)
    registry.register(_version("v1", 0.5, 0.1))

    with pytest.raises(PromotionRejected):
        registry.promote("v1")

    assert registry.active() is None


def test_promotion_replaces_previous_active() -> None:
    registry = ModelRegistry(THRESHOLD)
    registry.register(_version("v1", 0.1, 0.1))
    registry.register(_version("v2", 0.05, 0.05))

    registry.promote("v1")
    registry.promote("v2")

    active = registry.active()
    assert active is not None
    assert active.version == "v2"
    assert [version.promoted for version in registry.versions()] == [False, True]


def test_duplicate_registration_and_unknown_promotion() -> None:
    registry = ModelRegistry(THRESHOLD)
    registry.register(_version("v1", 0.1, 0.1))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(_version("v1", 0.1, 0.1))
    with pytest.raises(KeyError):
        registry.promote("missing")
