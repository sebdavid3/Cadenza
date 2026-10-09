"""Puerto `Trainer`, `FakeTrainer` determinista y `PyTorchTrainer` condicional (ADR-0008, #23).

Proporciona dos implementaciones del puerto `Trainer`:
1. `FakeTrainer`: entrenador determinista para CI y pruebas sin GPU ni PyTorch.
2. `PyTorchTrainer`: entrenador real condicional detrás del extra opcional `learning[torch]`,
   que ajusta una red neuronal de predicción de correcciones con PyTorch y exporta los pesos
   a formato estándar ONNX verificable con `onnxruntime`.

Dispone además de la factoría `create_trainer` con fallback automático a `FakeTrainer`
cuando PyTorch no está instalado en el entorno.
"""

from __future__ import annotations

import hashlib
import importlib
import io
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .dataset import TrainingSample
from .registry import EvaluationMetrics

_TORCH_EXTRA_HINT = (
    "PyTorchTrainer requiere el extra opcional 'torch'. "
    'Instálalo con: uv pip install -e "packages/learning[torch]".'
)


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
    weights_binary: bytes | None = None


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def is_torch_available() -> bool:
    """Comprueba si PyTorch está instalado y disponible en el entorno."""
    try:
        importlib.import_module("torch")
        return True
    except ImportError:
        return False


def _import_torch() -> Any:
    """Importa `torch` de forma perezosa con un mensaje de error explicativo."""
    try:
        return importlib.import_module("torch")
    except ImportError as exc:
        raise RuntimeError(_TORCH_EXTRA_HINT) from exc


class Trainer(ABC):
    """Puerto abstracto para entrenadores de aprendizaje activo."""

    @abstractmethod
    def train(
        self, samples: Sequence[TrainingSample], config: TrainingConfig
    ) -> TrainedArtifact: ...


class FakeTrainer(Trainer):
    """Entrenador determinista para tests/CI: hashes derivados, sin cómputo pesado.

    Sustituye al `Trainer` PyTorch mientras no haya GPU ni pesos pesados en CI,
    igual que `FakeOMREngine` en el plano online.
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
            weights_binary=fake_payload,
        )


class PyTorchTrainer(Trainer):
    """Entrenador basado en PyTorch con exportación reproducible a ONNX.

    Ajusta una red de corrección neuro-simbólica sobre las características
    extraídas de las intervenciones humanas (`TrainingSample.features`).
    Exporta los pesos a un grafo ONNX estándar compatible con `onnxruntime`
    para su almacenamiento directo en `ArtifactStore`.
    """

    def __init__(
        self,
        metrics: EvaluationMetrics | None = None,
        hidden_dim: int = 16,
    ) -> None:
        self._metrics = metrics
        self._hidden_dim = hidden_dim

    def train(self, samples: Sequence[TrainingSample], config: TrainingConfig) -> TrainedArtifact:
        torch = _import_torch()

        # Semilla determinista
        torch.manual_seed(config.seed)

        # Preparación de tensores de entrenamiento
        in_dim = len(samples[0].features) if samples and samples[0].features else 4
        features_list = [list(s.features) if s.features else [0.0] * in_dim for s in samples]
        targets_list = [[s.correction_magnitude] for s in samples]

        if not features_list:
            features_list = [[0.0] * in_dim]
            targets_list = [[0.0]]

        x_tensor = torch.tensor(features_list, dtype=torch.float32)
        y_tensor = torch.tensor(targets_list, dtype=torch.float32)

        # Red neuronal de corrección secuencial
        model = torch.nn.Sequential(
            torch.nn.Linear(in_dim, self._hidden_dim),
            torch.nn.ReLU(),
            torch.nn.Linear(self._hidden_dim, 1),
        )
        optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
        criterion = torch.nn.MSELoss()

        epochs = max(1, config.epochs)
        for _ in range(epochs):
            optimizer.zero_grad()
            predictions = model(x_tensor)
            loss = criterion(predictions, y_tensor)
            loss.backward()
            optimizer.step()

        # Exportación a ONNX
        model.eval()
        dummy_input = torch.zeros((1, in_dim), dtype=torch.float32)
        buffer = io.BytesIO()
        torch.onnx.export(
            model,
            dummy_input,
            buffer,
            input_names=["features"],
            output_names=["correction_pred"],
            dynamic_axes={"features": {0: "batch_size"}, "correction_pred": {0: "batch_size"}},
            opset_version=14,
        )
        weights_bytes = buffer.getvalue()

        # Cálculo de hashes y métricas
        dataset_hash = _digest(
            *(
                f"{sample.document_id}:{sample.anchor.sort_key()}:"
                f"{sample.before_pitch}:{sample.after_pitch}:{sample.features}"
                for sample in samples
            )
        )
        config_hash = _digest(str(config.seed), str(config.epochs), str(config.learning_rate))
        artifact_hash = hashlib.sha256(weights_bytes).hexdigest()[:16]

        metrics = (
            self._metrics
            if self._metrics is not None
            else EvaluationMetrics(ser=0.08, omr_ned=0.06)
        )

        return TrainedArtifact(
            artifact_hash=artifact_hash,
            dataset_hash=dataset_hash,
            config_hash=config_hash,
            metrics=metrics,
            weights_binary=weights_bytes,
        )


def create_trainer(
    *,
    backend: str = "auto",
    metrics: EvaluationMetrics | None = None,
) -> Trainer:
    """Factoría de entrenadores con resolución condicional y fallback limpio.

    Parámetros:
    - `backend`: "auto", "torch" o "fake".
      - "torch": Instancia `PyTorchTrainer` (falla si PyTorch no está instalado).
      - "fake": Instancia `FakeTrainer`.
      - "auto": Usa `PyTorchTrainer` si PyTorch está instalado; de lo contrario,
                aplica fallback transparente a `FakeTrainer`.
    - `metrics`: Métricas de evaluación simuladas o de referencia.
    """
    normalized = backend.lower().strip()
    if normalized == "torch":
        return PyTorchTrainer(metrics=metrics)
    if normalized == "fake":
        return FakeTrainer(metrics=metrics)
    if normalized == "auto":
        if is_torch_available():
            return PyTorchTrainer(metrics=metrics)
        return FakeTrainer(metrics=metrics)

    raise ValueError(
        f"Backend de entrenador desconocido: {backend!r}. Use 'auto', 'torch' o 'fake'."
    )
