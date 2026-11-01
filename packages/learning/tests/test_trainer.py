"""Pruebas del `FakeTrainer` determinista y de la carga de configuración.

`PyTorchTrainer` se retiró en #271: devolvía métricas de reserva y la capa de sugerencias
(ADR-0036) lo sustituye en el flujo de aprendizaje.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import cadenza.learning
import pytest
from cadenza.learning import (
    DatasetBuilder,
    EvaluationMetrics,
    FakeTrainer,
    TrainingConfig,
    TrainingSample,
    load_training_config,
)

from .support import make_anchor, make_document, make_edit

CONFIG = TrainingConfig(seed=42, epochs=10, learning_rate=0.0001)
METRICS = EvaluationMetrics(ser=0.05, omr_ned=0.03)


def _samples() -> tuple[TrainingSample, ...]:
    document = make_document()
    edits = [make_edit(1, make_anchor(0), "C4", "D4")]
    return DatasetBuilder().build(document, edits)


def test_fake_trainer_is_deterministic() -> None:
    trainer = FakeTrainer(METRICS)
    assert trainer.train(_samples(), CONFIG) == trainer.train(_samples(), CONFIG)


def test_config_change_changes_artifact_hash() -> None:
    trainer = FakeTrainer(METRICS)
    other = TrainingConfig(seed=7, epochs=10, learning_rate=0.0001)
    assert (
        trainer.train(_samples(), CONFIG).artifact_hash
        != trainer.train(_samples(), other).artifact_hash
    )


def test_loads_versioned_config() -> None:
    path = Path(__file__).resolve().parents[3] / "configs" / "learning" / "default.json"
    config = load_training_config(path)
    assert config.seed == 42
    assert config.epochs == 10
    assert config.learning_rate == 0.0001


def test_fake_trainer_has_no_reserve_metrics() -> None:
    """Las métricas las da quien llama: el entrenador no trae cifras propias (CLAUDE.md §8.1)."""
    metrics = inspect.signature(FakeTrainer).parameters["metrics"]
    assert metrics.default is inspect.Parameter.empty

    # Sin métricas no se construye; `Any` deja llamarlo sin ellas a propósito.
    trainer_class: Any = FakeTrainer
    with pytest.raises(TypeError):
        trainer_class()


def test_fake_trainer_result_is_marked_simulated() -> None:
    """Ningún entrenador evalúa el modelo que produce (D14): su resultado no es una medición."""
    artifact = FakeTrainer(METRICS).train(_samples(), CONFIG)
    assert artifact.simulated is True
    assert artifact.metrics == METRICS


def test_pytorch_trainer_is_retired() -> None:
    """La red de `PyTorchTrainer` sale del código con #271 (ADR-0036 §9)."""
    for name in ("PyTorchTrainer", "create_trainer", "is_torch_available"):
        assert not hasattr(cadenza.learning, name), name
        assert name not in cadenza.learning.__all__, name


def test_fake_trainer_produces_weights_binary() -> None:
    trainer = FakeTrainer(METRICS)
    art = trainer.train(_samples(), CONFIG)
    assert art.weights_binary is not None
    assert b"ONNX_MOCK_WEIGHTS" in art.weights_binary
