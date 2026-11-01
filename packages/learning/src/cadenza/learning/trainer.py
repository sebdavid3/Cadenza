"""Puerto `Trainer` y `FakeTrainer` determinista (ADR-0008, #22).

Ningún entrenador de este puerto evalúa el modelo que produce: el ajuste fino real del modelo
de reconocimiento no existe (D14, #103). Por eso `FakeTrainer` no trae métricas propias, las
recibe de quien lo llama, y su resultado va siempre marcado como simulado (CLAUDE.md §8).

`PyTorchTrainer`, una red auxiliar que devolvía métricas de reserva, se retiró en #271: el
aprendizaje de las correcciones lo hace la capa de sugerencias (`ml suggestions`, ADR-0036).
"""

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
    # Si las métricas no salen de evaluar el modelo entrenado (CLAUDE.md §8.2).
    simulated: bool
    weights_binary: bytes | None = None


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


class Trainer(ABC):
    """Puerto abstracto para entrenadores de aprendizaje activo."""

    @abstractmethod
    def train(
        self, samples: Sequence[TrainingSample], config: TrainingConfig
    ) -> TrainedArtifact: ...


class FakeTrainer(Trainer):
    """Entrenador determinista para tests/CI: hashes derivados, sin cómputo pesado.

    Devuelve las métricas que recibe, sin valores de reserva, y marca su resultado como
    simulado: no evalúa nada.
    """

    def __init__(self, metrics: EvaluationMetrics) -> None:
        self._metrics = metrics

    def train(self, samples: Sequence[TrainingSample], config: TrainingConfig) -> TrainedArtifact:
        dataset_hash = _digest(
            *(
                f"{sample.document_id}:{sample.anchor.sort_key()}:"
                f"{sample.before_pitch}:{sample.after_pitch}:{sample.features}"
                for sample in samples
            )
        )
        config_hash = _digest(str(config.seed), str(config.epochs), str(config.learning_rate))
        fake_payload = (
            b"ONNX_MOCK_WEIGHTS_V1\n"
            + f"artifact_hash={_digest('fake', dataset_hash, config_hash)}\n".encode()
            + f"dataset_hash={dataset_hash}\n".encode()
            + f"config_hash={config_hash}\n".encode()
            + f"seed={config.seed}\n".encode()
        )
        return TrainedArtifact(
            artifact_hash=_digest("fake", dataset_hash, config_hash),
            dataset_hash=dataset_hash,
            config_hash=config_hash,
            metrics=self._metrics,
            simulated=True,
            weights_binary=fake_payload,
        )
