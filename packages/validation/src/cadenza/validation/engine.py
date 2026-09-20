"""Motor de validación: orquesta reglas puras y aplana sus hallazgos."""

from __future__ import annotations

from collections.abc import Sequence

from cadenza.domain import Finding, ScoreDocument

from .rules import ValidationRule


def _finding_sort_key(finding: Finding) -> tuple[tuple[int, int, int, int, int, str], str]:
    return (finding.anchor.sort_key(), finding.rule_id)


class ValidationEngine:
    """Ejecuta las reglas inyectadas sobre un `ScoreDocument` (solo lectura).

    El motor no conoce reglas concretas: recibe la lista de `ValidationRule`,
    ejecuta `evaluate` en cada una y devuelve la lista **aplanada** de `Finding`
    en orden determinista. El documento nunca se muta.
    """

    def __init__(self, rules: Sequence[ValidationRule]) -> None:
        self._rules: tuple[ValidationRule, ...] = tuple(rules)

    @property
    def rules(self) -> tuple[ValidationRule, ...]:
        return self._rules

    def validate(self, document: ScoreDocument) -> list[Finding]:
        findings: list[Finding] = []
        for rule in self._rules:
            findings.extend(rule.evaluate(document))
        return sorted(findings, key=_finding_sort_key)
