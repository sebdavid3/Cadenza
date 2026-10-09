"""Motor de validación de Cadenza (M2)."""

from __future__ import annotations

from .engine import ValidationEngine
from .pitch import midi_to_pitch, parse_pitch, pitch_alter, pitch_octave, pitch_step, pitch_to_midi
from .rules import (
    DEFAULT_RULES_CATALOG,
    KeyConsistencyRule,
    MeasureBalanceRule,
    PitchRangeRule,
    TieResolutionRule,
    ValidationRule,
    VoiceCollisionRule,
    get_default_rules,
)

__all__ = [
    "DEFAULT_RULES_CATALOG",
    "KeyConsistencyRule",
    "MeasureBalanceRule",
    "PitchRangeRule",
    "TieResolutionRule",
    "ValidationEngine",
    "ValidationRule",
    "VoiceCollisionRule",
    "get_default_rules",
    "midi_to_pitch",
    "parse_pitch",
    "pitch_alter",
    "pitch_octave",
    "pitch_step",
    "pitch_to_midi",
]
