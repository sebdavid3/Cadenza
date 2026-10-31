"""Motor de validación de Cadenza (M2)."""

from __future__ import annotations

from .engine import ValidationEngine
from .pitch import midi_to_pitch, parse_pitch, pitch_alter, pitch_octave, pitch_step, pitch_to_midi
from .rules import (
    DEFAULT_RULES_CATALOG,
    RULES_CATALOG_VERSION,
    AccidentalRepeatedRule,
    KeyConsistencyRule,
    MeasureBalanceRule,
    PitchRangeRule,
    TieResolutionRule,
    TimeSignatureRule,
    TupletIncompleteRule,
    ValidationRule,
    VoiceCollisionRule,
    get_default_rules,
)

__all__ = [
    "DEFAULT_RULES_CATALOG",
    "RULES_CATALOG_VERSION",
    "AccidentalRepeatedRule",
    "KeyConsistencyRule",
    "MeasureBalanceRule",
    "PitchRangeRule",
    "TieResolutionRule",
    "TimeSignatureRule",
    "TupletIncompleteRule",
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
