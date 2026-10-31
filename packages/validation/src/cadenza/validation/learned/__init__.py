"""Capa de sugerencias que aprende de las correcciones: rasgos e inferencia (ADR-0036).

Vive en el plano en línea y no importa `cadenza.application` ni `cadenza.learning`: el
entrenamiento (`cadenza.learning.suggestions`) importa de aquí los rasgos, nunca al revés.
"""

from __future__ import annotations

from .features import (
    FAMILIES,
    FEATURE_VERSION,
    INSERTION,
    NONE_LABEL,
    EventView,
    Position,
    ScoreFeatures,
    accidental_label,
    decode_accidental,
    decode_duration,
    decode_pitch,
    diatonic_index,
    discretize,
    duration_label,
    figure_of,
    insertion_label,
    key_accidental,
    label_of_edit,
    labels_from_correction,
    pitch_label,
    read_event,
    split_pitch,
)
from .messages import describe_edit, figure_name, note_name
from .model import (
    ARTIFACT_FORMAT,
    ARTIFACT_FORMAT_VERSION,
    LEARNED_PREFIX,
    MAX_SUGGESTIONS,
    MODEL_TYPE,
    FrequencyBackoffModel,
    InvalidSuggestionArtifact,
    Score,
    context_key,
)

__all__ = [
    "ARTIFACT_FORMAT",
    "ARTIFACT_FORMAT_VERSION",
    "FAMILIES",
    "FEATURE_VERSION",
    "INSERTION",
    "LEARNED_PREFIX",
    "MAX_SUGGESTIONS",
    "MODEL_TYPE",
    "NONE_LABEL",
    "EventView",
    "FrequencyBackoffModel",
    "InvalidSuggestionArtifact",
    "Position",
    "Score",
    "ScoreFeatures",
    "accidental_label",
    "context_key",
    "decode_accidental",
    "decode_duration",
    "decode_pitch",
    "describe_edit",
    "diatonic_index",
    "discretize",
    "duration_label",
    "figure_name",
    "figure_of",
    "insertion_label",
    "key_accidental",
    "label_of_edit",
    "labels_from_correction",
    "note_name",
    "pitch_label",
    "read_event",
    "split_pitch",
]
