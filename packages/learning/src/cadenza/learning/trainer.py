"""Puerto `Trainer` y `FakeTrainer` determinista (sin PyTorch ni GPU)."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from .dataset import TrainingSample
from .registry import EvaluationMetrics


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    seed: int
    epochs: int
    learning_rate: float


@dataclass(frozen=True, slots=True)
class TrainedArtifact:
    artifact_hash: str
    dataset_hash: str
    config_hash: str
    metrics: EvaluationMetrics


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


class Trainer(ABC):
    """Entrena un artefacto a partir de muestras y configuración versionada."""

    @abstractmethod
    def train(
        self, samples: Sequence[TrainingSample], config: TrainingConfig
    ) -> TrainedArtifact: ...


class FakeTrainer(Trainer):
    """Entrenador determinista para tests/CI: hashes derivados, sin cómputo pesado.

    Sustituye al `Trainer` PyTorch (pipeline de HOMR) mientras no haya GPU ni
    pesos, igual que `FakeOMREngine` en el plano online.
    """

    def __init__(self, metrics: EvaluationMetrics | None = None) -> None:
        self._metrics = metrics if metrics is not None else EvaluationMetrics(ser=0.1, omr_ned=0.08)

    def train(self, samples: Sequence[TrainingSample], config: TrainingConfig) -> TrainedArtifact:
        dataset_hash = _digest(
            *(
                f"{sample.document_id}:{sample.anchor.sort_key()}:"
                f"{sample.before_pitch}:{sample.after_pitch}:{sample.features}"
                for sample in samples
            )
        )
        config_hash = _digest(str(config.seed), str(config.epochs), str(config.learning_rate))
        return TrainedArtifact(
            artifact_hash=_digest("fake", dataset_hash, config_hash),
            dataset_hash=dataset_hash,
            config_hash=config_hash,
            metrics=self._metrics,
        )
