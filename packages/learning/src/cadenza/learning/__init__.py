"""Aprendizaje activo por lotes de Cadenza (M4, ADR-0008)."""

from __future__ import annotations

from .acquisition import AcquisitionStrategy, RandomAcquisition, feature_distance
from .acquisition.diversity import DiversityAcquisition
from .acquisition.hybrid import HybridAcquisition
from .acquisition.uncertainty import ErrorDensityAcquisition, UncertaintyAcquisition
from .alignment import (
    EditDistribution,
    align_voice_events,
    count_edits_by_op,
    derive_edit_events,
    is_structurally_equal,
    split_pitch,
)
from .config import JobConfig, compute_config_hash, load_job_config, load_training_config
from .dataset import (
    DatasetBuilder,
    RepositoryDatasetReader,
    TrainingSample,
    compute_correction_magnitude,
    dataset_hash,
    deserialize_dataset,
    serialize_dataset,
)
from .evaluation import normalized_edit_distance, symbol_error_rate
from .omr_metrics import MetricsExtraMissing, OmrNedResult, omr_ned_batch, omr_ned_pair
from .pitch import pitch_to_midi, semitone_distance
from .registry import (
    EvaluationMetrics,
    ModelRegistry,
    ModelVersion,
    PromotionRejected,
    PromotionThreshold,
)
from .trainer import FakeTrainer, TrainedArtifact, Trainer, TrainingConfig
from .validation_metrics import (
    BinaryMetrics,
    ErrorCategoryCoverage,
    MeasureEvaluationRecord,
    ValidationEvaluationReport,
    aggregate_validation_metrics,
    categorize_edit_op,
    compute_binary_metrics,
    evaluate_pair,
    evaluate_score_measures,
)

__all__ = [
    "AcquisitionStrategy",
    "BinaryMetrics",
    "DatasetBuilder",
    "DiversityAcquisition",
    "EditDistribution",
    "ErrorCategoryCoverage",
    "ErrorDensityAcquisition",
    "EvaluationMetrics",
    "FakeTrainer",
    "HybridAcquisition",
    "JobConfig",
    "MeasureEvaluationRecord",
    "MetricsExtraMissing",
    "ModelRegistry",
    "ModelVersion",
    "OmrNedResult",
    "PromotionRejected",
    "PromotionThreshold",
    "RandomAcquisition",
    "RepositoryDatasetReader",
    "TrainedArtifact",
    "Trainer",
    "TrainingConfig",
    "TrainingSample",
    "UncertaintyAcquisition",
    "ValidationEvaluationReport",
    "aggregate_validation_metrics",
    "align_voice_events",
    "categorize_edit_op",
    "compute_binary_metrics",
    "compute_config_hash",
    "compute_correction_magnitude",
    "count_edits_by_op",
    "dataset_hash",
    "derive_edit_events",
    "deserialize_dataset",
    "evaluate_pair",
    "evaluate_score_measures",
    "feature_distance",
    "is_structurally_equal",
    "load_job_config",
    "load_training_config",
    "normalized_edit_distance",
    "omr_ned_batch",
    "omr_ned_pair",
    "pitch_to_midi",
    "semitone_distance",
    "serialize_dataset",
    "split_pitch",
    "symbol_error_rate",
]
