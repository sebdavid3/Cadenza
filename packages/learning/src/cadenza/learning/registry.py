"""Model Registry con promoción gobernada por umbral (ADR-0008)."""

from __future__ import annotations

from dataclasses import dataclass, replace


class PromotionRejected(Exception):
    """La versión no supera el umbral de promoción y no debe activarse."""


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    ser: float
    omr_ned: float


@dataclass(frozen=True, slots=True)
class PromotionThreshold:
    max_ser: float
    max_omr_ned: float

    def accepts(self, metrics: EvaluationMetrics) -> bool:
        return metrics.ser <= self.max_ser and metrics.omr_ned <= self.max_omr_ned


@dataclass(frozen=True, slots=True)
class ModelVersion:
    version: str
    artifact_hash: str
    dataset_hash: str
    config_hash: str
    metrics: EvaluationMetrics
    promoted: bool = False


class ModelRegistry:
    """Catálogo versionado con promoción explícita (nunca automática)."""

    def __init__(self, threshold: PromotionThreshold) -> None:
        self._threshold = threshold
        self._versions: list[ModelVersion] = []

    def register(self, version: ModelVersion) -> ModelVersion:
        if any(existing.version == version.version for existing in self._versions):
            raise ValueError(f"version already registered: {version.version}")
        self._versions.append(version)
        return version

    def promote(self, version_id: str) -> ModelVersion:
        target = self._find(version_id)
        if not self._threshold.accepts(target.metrics):
            raise PromotionRejected(
                f"{version_id} no supera el umbral "
                f"(ser={target.metrics.ser}, omr_ned={target.metrics.omr_ned})"
            )
        self._versions = [
            replace(version, promoted=version.version == version_id) for version in self._versions
        ]
        return self._find(version_id)

    def active(self) -> ModelVersion | None:
        return next((version for version in self._versions if version.promoted), None)

    def versions(self) -> tuple[ModelVersion, ...]:
        return tuple(self._versions)

    def _find(self, version_id: str) -> ModelVersion:
        for version in self._versions:
            if version.version == version_id:
                return version
        raise KeyError(version_id)
