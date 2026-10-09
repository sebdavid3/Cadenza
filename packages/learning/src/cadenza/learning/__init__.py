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
from .evaluation import (
    SerResult,
    format_clef_symbol,
    format_duration_symbol,
    format_key_signature_symbol,
    format_time_signature_symbol,
    normalized_edit_distance,
    resolve_pitch_with_key_signature,
    score_ser_pair,
    score_to_symbol_sequence,
    score_to_symbols,
    symbol_error_rate,
)
from .omr_metrics import MetricsExtraMissing, OmrNedResult, omr_ned_batch, omr_ned_pair
from .pitch import pitch_to_midi, semitone_distance
from .registry import (
    EvaluationMetrics,
    ModelRegistry,
    ModelVersion,
    PromotionRejected,
    PromotionThreshold,
)
from .trainer import (
    FakeTrainer,
    PyTorchTrainer,
    TrainedArtifact,
    Trainer,
    TrainingConfig,
    create_trainer,
    is_torch_available,
)
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
    "PyTorchTrainer",
    "RandomAcquisition",
    "RepositoryDatasetReader",
    "SerResult",
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
    "create_trainer",
    "dataset_hash",
    "derive_edit_events",
    "deserialize_dataset",
    "evaluate_pair",
    "evaluate_score_measures",
    "feature_distance",
    "format_clef_symbol",
    "format_duration_symbol",
    "format_key_signature_symbol",
    "format_time_signature_symbol",
    "is_structurally_equal",
    "is_torch_available",
    "load_job_config",
    "load_training_config",
    "normalized_edit_distance",
    "omr_ned_batch",
    "omr_ned_pair",
    "pitch_to_midi",
    "resolve_pitch_with_key_signature",
    "score_ser_pair",
    "score_to_symbol_sequence",
    "score_to_symbols",
    "semitone_distance",
    "serialize_dataset",
    "split_pitch",
    "symbol_error_rate",
]
