"""Puerto abstracto de Model Registry (ADR-0008, ARCHITECTURE.md §6.2, #21)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import UTC, datetime


class PromotionRejected(Exception):
    """La versión no supera el umbral de promoción y no debe activarse."""


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    """Métricas de evaluación del modelo OMR sobre el corpus de validación."""

    ser: float
    omr_ned: float


@dataclass(frozen=True, slots=True)
class PromotionThreshold:
    """Umbral de calidad requerido para promover un modelo al plano online."""

    max_ser: float
    max_omr_ned: float

    def accepts(self, metrics: EvaluationMetrics) -> bool:
        return metrics.ser <= self.max_ser and metrics.omr_ned <= self.max_omr_ned


@dataclass(frozen=True, slots=True)
class ModelVersionData:
    """Metadatos desacoplados de una versión del modelo OMR."""

    version: str
    artifact_hash: str
    dataset_hash: str
    config_hash: str
    metrics: EvaluationMetrics
    promoted: bool = False
    created_at: datetime | None = None


class ModelRegistry(ABC):
    """Contrato del Model Registry para registrar, promover y consultar el modelo activo."""

    @abstractmethod
    def register(self, version: ModelVersionData) -> ModelVersionData:
        """Registra una nueva versión de modelo."""

    @abstractmethod
    def promote(self, version_id: str) -> ModelVersionData:
        """Promueve una versión si cumple el umbral."""

    @abstractmethod
    def active(self) -> ModelVersionData | None:
        """Devuelve la versión de modelo actualmente activa o None si no hay ninguna promovida."""

    @abstractmethod
    def versions(self) -> tuple[ModelVersionData, ...]:
        """Devuelve todas las versiones registradas."""


class InMemoryModelRegistry(ModelRegistry):
    """Implementación en memoria de ModelRegistry para pruebas unitarias."""

    def __init__(self, threshold: PromotionThreshold | None = None) -> None:
        self._threshold = threshold or PromotionThreshold(max_ser=1.0, max_omr_ned=1.0)
        self._versions: list[ModelVersionData] = []

    def register(self, version: ModelVersionData) -> ModelVersionData:
        if any(existing.version == version.version for existing in self._versions):
            raise ValueError(f"version already registered: {version.version}")
        created = (
            version
            if version.created_at is not None
            else replace(version, created_at=datetime.now(UTC))
        )
        self._versions.append(created)
        return created

    def promote(self, version_id: str) -> ModelVersionData:
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

    def active(self) -> ModelVersionData | None:
        return next((version for version in self._versions if version.promoted), None)

    def versions(self) -> tuple[ModelVersionData, ...]:
        return tuple(self._versions)

    def _find(self, version_id: str) -> ModelVersionData:
        for version in self._versions:
            if version.version == version_id:
                return version
        raise KeyError(version_id)
