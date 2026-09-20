"""Reglas de validación puras y registrables (M2).

`rules/__init__.py` define la interfaz base `ValidationRule`; las reglas
concretas viven en módulos hermanos (p. ej. `rules/measure_balance.py`). Se usa
el paquete (y no un `rules.py`) para evitar la colisión módulo/paquete.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from cadenza.domain import Finding, ScoreDocument


class ValidationRule(ABC):
    """Regla pura de solo lectura sobre un `ScoreDocument`.

    `evaluate` **nunca** muta el documento (el dominio es inmutable) y devuelve
    los `Finding` anclados que correspondan a la regla.
    """

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Identificador estable de la regla, usado en `Finding.rule_id`."""

    @abstractmethod
    def evaluate(self, document: ScoreDocument) -> list[Finding]:
        """Devuelve los hallazgos de la regla sobre el documento."""
