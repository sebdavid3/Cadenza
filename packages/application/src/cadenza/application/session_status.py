"""Estados y transiciones del ciclo de vida de la sesión (ADR-0014, #34)."""

from __future__ import annotations

from enum import StrEnum


class SessionStatus(StrEnum):
    """Estados del ciclo de vida de una sesión de transcripción."""

    TRANSCRIBED = "transcribed"
    CORRECTING = "correcting"
    FINALIZED = "finalized"
    FAILED = "failed"
