"""Carga de configuraciones de entrenamiento versionadas (`configs/`)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .registry import PromotionThreshold
from .trainer import TrainingConfig


@dataclass(frozen=True, slots=True)
class JobConfig:
    """Configuración completa y reproducible de un job de aprendizaje activo (D16)."""

    seed: int = 42
    epochs: int = 10
    learning_rate: float = 0.0001
    strategy: str = "hybrid"
    budget: int = 10
    promotion_threshold: PromotionThreshold = field(
        default_factory=lambda: PromotionThreshold(max_ser=0.2, max_omr_ned=0.15)
    )
    raw_data: Mapping[str, Any] | None = None

    @property
    def config_hash(self) -> str:
        """Hash SHA-256 canónico de la configuración."""
        if self.raw_data is not None:
            canonical = json.dumps(
                dict(self.raw_data), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        else:
            payload = {
                "seed": self.seed,
                "epochs": self.epochs,
                "learning_rate": self.learning_rate,
                "strategy": self.strategy,
                "budget": self.budget,
                "promotion": {
                    "max_ser": self.promotion_threshold.max_ser,
                    "max_omr_ned": self.promotion_threshold.max_omr_ned,
                },
            }
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def to_training_config(self) -> TrainingConfig:
        return TrainingConfig(
            seed=self.seed,
            epochs=self.epochs,
            learning_rate=self.learning_rate,
        )


def compute_config_hash(path_or_data: Path | Mapping[str, Any]) -> str:
    """Calcula el hash SHA-256 canónico de una configuración JSON."""
    if isinstance(path_or_data, Path):
        data = json.loads(path_or_data.read_text(encoding="utf-8"))
    else:
        data = dict(path_or_data)
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def load_training_config(path: Path) -> TrainingConfig:
    """Lee una configuración de entrenamiento reproducible desde JSON."""

    data = json.loads(path.read_text(encoding="utf-8"))
    return TrainingConfig(
        seed=int(data["seed"]),
        epochs=int(data["epochs"]),
        learning_rate=float(data["learning_rate"]),
    )


def load_job_config(path: Path) -> JobConfig:
    """Lee y valida una configuración de job de aprendizaje activo desde JSON."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    promotion_raw = raw.get("promotion", {})
    max_ser = float(promotion_raw.get("max_ser", 0.2))
    max_omr_ned = float(promotion_raw.get("max_omr_ned", 0.15))
    return JobConfig(
        seed=int(raw.get("seed", 42)),
        epochs=int(raw.get("epochs", 10)),
        learning_rate=float(raw.get("learning_rate", 0.0001)),
        strategy=str(raw.get("strategy", "hybrid")),
        budget=int(raw.get("budget", 10)),
        promotion_threshold=PromotionThreshold(max_ser=max_ser, max_omr_ned=max_omr_ned),
        raw_data=raw,
    )
