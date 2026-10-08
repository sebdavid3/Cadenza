"""Model Registry con promoción gobernada por umbral (ADR-0008, ARCHITECTURE.md §6.2, #21)."""

from __future__ import annotations

from cadenza.application.ports.model_registry import (
    EvaluationMetrics,
    InMemoryModelRegistry,
    ModelVersionData,
    PromotionRejected,
    PromotionThreshold,
)
from cadenza.application.ports.model_registry import (
    ModelRegistry as AbstractModelRegistry,
)

# Alias de compatibilidad hacia atrás
ModelVersion = ModelVersionData


class ModelRegistry(InMemoryModelRegistry):
    """Catálogo versionado con promoción explícita (nunca automática).

    Implementación en memoria compatible con el puerto abstracto `AbstractModelRegistry`.
    """

    def __init__(self, threshold: PromotionThreshold) -> None:
        super().__init__(threshold=threshold)


__all__ = [
    "AbstractModelRegistry",
    "EvaluationMetrics",
    "InMemoryModelRegistry",
    "ModelRegistry",
    "ModelVersion",
    "ModelVersionData",
    "PromotionRejected",
    "PromotionThreshold",
]
