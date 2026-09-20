"""Regla de balance de compás (M2).

Comprueba que la suma de duraciones de notas y silencios de un compás coincida
con su métrica. La duración esperada la aporta el propio valor de dominio
`TimeSignature.quarter_length`, sin dependencias externas. La regla es de **solo
lectura** y ancla el hallazgo al primer evento del compás problemático.
"""

from __future__ import annotations

from fractions import Fraction

from cadenza.domain import (
    Anchor,
    AnchorIndex,
    EventKind,
    Finding,
    Measure,
    ScoreDocument,
    Severity,
    TimeSignature,
)

from . import ValidationRule

RULE_ID = "measure.balance"
_DURATION_KINDS = frozenset({EventKind.NOTE, EventKind.REST})


def _expected_quarter_length(signature: TimeSignature) -> Fraction:
    """Duración esperada del compás en negras, derivada del dominio."""

    return signature.quarter_length


def _durations_sum(measure: Measure) -> Fraction | None:
    """Suma de duraciones del compás, o `None` si algún evento no la declara."""

    total = Fraction(0)
    for event in measure.events:
        if event.kind not in _DURATION_KINDS:
            continue
        if event.duration_beats is None:
            return None
        total += event.duration_beats
    return total


def _first_anchor_by_measure(index: AnchorIndex) -> dict[tuple[int, int, int], Anchor]:
    """Primer ancla (evento) de cada compás, en orden determinista."""

    result: dict[tuple[int, int, int], Anchor] = {}
    for anchor in index.anchors():
        result.setdefault((anchor.part, anchor.staff, anchor.measure), anchor)
    return result


class MeasureBalanceRule(ValidationRule):
    """La suma de duraciones de cada compás debe igualar su métrica."""

    @property
    def rule_id(self) -> str:
        return RULE_ID

    def evaluate(self, document: ScoreDocument) -> list[Finding]:
        first_anchor = _first_anchor_by_measure(document.anchors)
        findings: list[Finding] = []
        for part_index, part in enumerate(document.score.parts):
            for staff_index, staff in enumerate(part.staves):
                for measure in staff.measures:
                    finding = self._evaluate_measure(part_index, staff_index, measure, first_anchor)
                    if finding is not None:
                        findings.append(finding)
        return findings

    def _evaluate_measure(
        self,
        part_index: int,
        staff_index: int,
        measure: Measure,
        first_anchor: dict[tuple[int, int, int], Anchor],
    ) -> Finding | None:
        if measure.time_signature is None:
            return None
        expected = _expected_quarter_length(measure.time_signature)
        actual = _durations_sum(measure)
        if actual is None or actual == expected:
            return None
        anchor = first_anchor.get((part_index, staff_index, measure.number))
        if anchor is None:
            return None
        return Finding(
            anchor=anchor,
            rule_id=RULE_ID,
            severity=Severity.ERROR,
            message=(
                f"El compás {measure.number} suma {actual} negras y su métrica "
                f"{measure.time_signature} exige {expected}."
            ),
            suggested_fix=(
                f"Ajustar las duraciones del compás {measure.number} para sumar "
                f"{expected} negras."
            ),
        )
