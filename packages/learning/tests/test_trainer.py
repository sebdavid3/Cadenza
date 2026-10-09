"""Pruebas del `FakeTrainer` determinista, `PyTorchTrainer` y la carga de configuración."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cadenza.learning import (
    DatasetBuilder,
    EvaluationMetrics,
    FakeTrainer,
    PyTorchTrainer,
    TrainingConfig,
    TrainingSample,
    create_trainer,
    is_torch_available,
    load_training_config,
)

from .support import make_anchor, make_document, make_edit

CONFIG = TrainingConfig(seed=42, epochs=10, learning_rate=0.0001)


def _samples() -> tuple[TrainingSample, ...]:
    document = make_document()
    edits = [make_edit(1, make_anchor(0), "C4", "D4")]
    return DatasetBuilder().build(document, edits)


def test_fake_trainer_is_deterministic() -> None:
    trainer = FakeTrainer()
    assert trainer.train(_samples(), CONFIG) == trainer.train(_samples(), CONFIG)


def test_config_change_changes_artifact_hash() -> None:
    trainer = FakeTrainer()
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


def test_create_trainer_backends() -> None:
    fake = create_trainer(backend="fake", metrics=EvaluationMetrics(ser=0.05, omr_ned=0.03))
    assert isinstance(fake, FakeTrainer)

    torch_trainer = create_trainer(backend="torch")
    assert isinstance(torch_trainer, PyTorchTrainer)

    auto_trainer = create_trainer(backend="auto")
    if is_torch_available():
        assert isinstance(auto_trainer, PyTorchTrainer)
    else:
        assert isinstance(auto_trainer, FakeTrainer)

    with pytest.raises(ValueError, match="Backend de entrenador desconocido"):
        create_trainer(backend="unsupported_backend")


def test_pytorch_trainer_raises_when_torch_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_import(name: str) -> None:
        raise ImportError("No module named 'torch'")

    monkeypatch.setattr("cadenza.learning.trainer.importlib.import_module", fake_import)
    trainer = PyTorchTrainer()

    with pytest.raises(RuntimeError, match=r"learning\[torch\]"):
        trainer.train(_samples(), CONFIG)


def test_pytorch_trainer_deterministic_with_mocked_torch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_torch = MagicMock()
    mock_nn = MagicMock()
    mock_optim = MagicMock()
    mock_onnx = MagicMock()

    mock_torch.nn = mock_nn
    mock_torch.optim = mock_optim
    mock_torch.onnx = mock_onnx

    def fake_export(model: object, dummy: object, buf: io.BytesIO, **kwargs: object) -> None:
        buf.write(b"ONNX_SIMULATED_GRAPH_BYTES_MODEL_WEIGHTS")

    mock_onnx.export.side_effect = fake_export

    monkeypatch.setitem(sys.modules, "torch", mock_torch)
    monkeypatch.setitem(sys.modules, "torch.nn", mock_nn)
    monkeypatch.setitem(sys.modules, "torch.optim", mock_optim)
    monkeypatch.setitem(sys.modules, "torch.onnx", mock_onnx)
    monkeypatch.setattr("cadenza.learning.trainer.importlib.import_module", lambda name: mock_torch)

    trainer = PyTorchTrainer()
    artifact = trainer.train(_samples(), CONFIG)

    assert artifact.artifact_hash != ""
    assert artifact.weights_binary == b"ONNX_SIMULATED_GRAPH_BYTES_MODEL_WEIGHTS"
    assert artifact.dataset_hash != ""
    assert artifact.config_hash != ""
    mock_torch.manual_seed.assert_called_once_with(CONFIG.seed)


def test_fake_trainer_produces_weights_binary() -> None:
    trainer = FakeTrainer()
    art = trainer.train(_samples(), CONFIG)
    assert art.weights_binary is not None
    assert b"ONNX_MOCK_WEIGHTS" in art.weights_binary
