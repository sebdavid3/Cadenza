"""Reglas de validación puras y registrables: el catálogo de ADR-0040.

| Regla | Título en la vista |
|---|---|
| `measure.balance` (`MeasureBalanceRule`) | Duración del compás |
| `time.signature` (`TimeSignatureRule`) | Indicación de compás |
| `tuplet.incomplete` (`TupletIncompleteRule`) | Tresillo incompleto |
| `accidental.repeated` (`AccidentalRepeatedRule`) | Alteración repetida |
| `key.consistency` (`KeyConsistencyRule`) | Armaduras distintas |
| `pitch.range` (`PitchRangeRule`) | Altura fuera de registro |
| `tie.resolution` (`TieResolutionRule`) | Ligadura sin cerrar |
| `voice.collision` (`VoiceCollisionRule`) | Acorde mal formado |

Cambiar lo que hace una regla no cambia su identificador (lo guardan los hallazgos de las
sesiones y `exp_06` cuenta por él), así que el catálogo lleva su propia versión,
`RULES_CATALOG_VERSION`, que `exp_06` y `exp_14` guardan junto a `rules_version` (§3).
"""

from __future__ import annotations

from typing import Final

from .accidental_repeated import AccidentalRepeatedRule
from .base import ValidationRule
from .key_consistency import KeyConsistencyRule
from .measure_balance import MeasureBalanceRule
from .pitch_range import PitchRangeRule
from .tie_resolution import TieResolutionRule
from .time_signature import TimeSignatureRule
from .tuplet_incomplete import TupletIncompleteRule
from .voice_collision import VoiceCollisionRule

RULES_CATALOG_VERSION: Final[int] = 2
"""Versión del catálogo: 1, las cinco reglas de la fase 7; 2, el catálogo de ADR-0040 (#246)."""

DEFAULT_RULES_CATALOG: tuple[type[ValidationRule], ...] = (
    MeasureBalanceRule,
    TimeSignatureRule,
    TupletIncompleteRule,
    AccidentalRepeatedRule,
    KeyConsistencyRule,
    PitchRangeRule,
    TieResolutionRule,
    VoiceCollisionRule,
)


def get_default_rules() -> tuple[ValidationRule, ...]:
    """Instancia y devuelve el catálogo completo de reglas."""
    return tuple(cls() for cls in DEFAULT_RULES_CATALOG)


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
    "ValidationRule",
    "VoiceCollisionRule",
    "get_default_rules",
]
