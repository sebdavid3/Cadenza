"""Aprendizaje activo por lotes de Cadenza (M4, ADR-0008)."""

from __future__ import annotations

from .acquisition import AcquisitionStrategy, feature_distance
from .acquisition.diversity import DiversityAcquisition
from .acquisition.hybrid import HybridAcquisition
from .acquisition.uncertainty import UncertaintyAcquisition
from .config import load_training_config
from .dataset import DatasetBuilder, TrainingSample
from .evaluation import normalized_edit_distance, symbol_error_rate
from .pitch import pitch_to_midi, semitone_distance
from .registry import (
    EvaluationMetrics,
    ModelRegistry,
    ModelVersion,
    PromotionRejected,
    PromotionThreshold,
)
from .trainer import FakeTrainer, TrainedArtifact, Trainer, TrainingConfig

__all__ = [
    "AcquisitionStrategy",
    "DatasetBuilder",
    "DiversityAcquisition",
    "EvaluationMetrics",
    "FakeTrainer",
    "HybridAcquisition",
    "ModelRegistry",
    "ModelVersion",
    "PromotionRejected",
    "PromotionThreshold",
    "TrainedArtifact",
    "Trainer",
    "TrainingConfig",
    "TrainingSample",
    "UncertaintyAcquisition",
    "feature_distance",
    "load_training_config",
    "normalized_edit_distance",
    "pitch_to_midi",
    "semitone_distance",
    "symbol_error_rate",
]
