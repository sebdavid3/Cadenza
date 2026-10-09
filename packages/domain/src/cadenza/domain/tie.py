"""Ligadura de prolongación (tie) como tipo de dominio neutral (ADR-0010)."""

from __future__ import annotations

from enum import StrEnum


class Tie(StrEnum):
    """Estado de ligadura de un evento de nota: inicio, continuación o cierre."""

    START = "start"
    CONTINUE = "continue"
    STOP = "stop"
