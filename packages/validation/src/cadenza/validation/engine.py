"""Motor de validación: orquesta reglas puras y aplana sus hallazgos."""

from __future__ import annotations

from collections.abc import Sequence

from cadenza.domain import Finding, ScoreDocument

from .rules import ValidationRule, get_default_rules


def _finding_sort_key(finding: Finding) -> tuple[tuple[int, int, int, int, int, str], str]:
    return (finding.anchor.sort_key(), finding.rule_id)


class ValidationEngine:
    """Ejecuta las reglas inyectadas sobre un `ScoreDocument` (solo lectura).

    Si no se proporciona una secuencia de reglas explícita (`rules is None`),
    inicializa el catálogo completo de las cinco familias de reglas por defecto.
    Ejecuta `evaluate` en cada regla y devuelve la lista **aplanada** de `Finding`
    en orden determinista. El documento nunca se muta.
    """

    def __init__(self, rules: Sequence[ValidationRule] | None = None) -> None:
        if rules is None:
            self._rules: tuple[ValidationRule, ...] = get_default_rules()
        else:
            self._rules = tuple(rules)

    @property
    def rules(self) -> tuple[ValidationRule, ...]:
        return self._rules

    @property
    def rules_version(self) -> str:
        """Huella estable de las reglas cargadas, para `Provenance.rules_version`."""

        return ",".join(sorted({rule.rule_id for rule in self._rules}))

    def validate(self, document: ScoreDocument) -> list[Finding]:
        findings: list[Finding] = []
        for rule in self._rules:
            findings.extend(rule.evaluate(document))
        return sorted(findings, key=_finding_sort_key)
