"""Reglas de validación puras y registrables (M2).

Expone la interfaz base `ValidationRule` y el catálogo completo de las cinco
familias de reglas musicales de la arquitectura objetivo:
1. Balance de compás (`MeasureBalanceRule`)
2. Rango tonal por clave (`PitchRangeRule`)
3. Consistencia de armadura y alteraciones (`KeyConsistencyRule`)
4. Colisión de voces y solapamiento temporal (`VoiceCollisionRule`)
5. Resolución y cierre de ligaduras (`TieResolutionRule`)
"""

from __future__ import annotations

from .base import ValidationRule
from .key_consistency import KeyConsistencyRule
from .measure_balance import MeasureBalanceRule
from .pitch_range import PitchRangeRule
from .tie_resolution import TieResolutionRule
from .voice_collision import VoiceCollisionRule

DEFAULT_RULES_CATALOG: tuple[type[ValidationRule], ...] = (
    KeyConsistencyRule,
    MeasureBalanceRule,
    PitchRangeRule,
    TieResolutionRule,
    VoiceCollisionRule,
)


def get_default_rules() -> tuple[ValidationRule, ...]:
    """Instancia y devuelve el catálogo estándar completo de las cinco reglas."""
    return tuple(cls() for cls in DEFAULT_RULES_CATALOG)


__all__ = [
    "DEFAULT_RULES_CATALOG",
    "KeyConsistencyRule",
    "MeasureBalanceRule",
    "PitchRangeRule",
    "TieResolutionRule",
    "ValidationRule",
    "VoiceCollisionRule",
    "get_default_rules",
]
