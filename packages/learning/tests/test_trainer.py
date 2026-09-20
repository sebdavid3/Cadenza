"""Pruebas del `FakeTrainer` determinista y la carga de configuración."""

from __future__ import annotations

from pathlib import Path

from cadenza.learning import (
    DatasetBuilder,
    FakeTrainer,
    TrainingConfig,
    TrainingSample,
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
