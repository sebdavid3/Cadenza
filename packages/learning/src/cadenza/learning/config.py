"""Carga de configuraciones de entrenamiento versionadas (`configs/`)."""

from __future__ import annotations

import json
from pathlib import Path

from .trainer import TrainingConfig


def load_training_config(path: Path) -> TrainingConfig:
    """Lee una configuración de entrenamiento reproducible desde JSON."""

    data = json.loads(path.read_text(encoding="utf-8"))
    return TrainingConfig(
        seed=int(data["seed"]),
        epochs=int(data["epochs"]),
        learning_rate=float(data["learning_rate"]),
    )
