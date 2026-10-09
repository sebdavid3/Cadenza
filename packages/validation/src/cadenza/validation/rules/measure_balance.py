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
    Event,
    EventKind,
    Finding,
    Measure,
    ScoreDocument,
    Severity,
    TimeSignature,
)

from .base import ValidationRule

RULE_ID = "measure.balance"
_DURATION_KINDS = frozenset({EventKind.NOTE, EventKind.REST})


def _expected_quarter_length(signature: TimeSignature) -> Fraction:
    """Duración esperada del compás en negras, derivada del dominio."""

    return signature.quarter_length


def _voice_durations_sum(events: list[Event]) -> Fraction | None:
    """Suma de duraciones de una voz en un compás (descontando notas de acordes simultáneas)."""

    total = Fraction(0)
    for event in events:
        if event.kind not in _DURATION_KINDS:
            continue
        if event.is_chord:
            continue
        if event.duration_beats is None:
            return None
        total += event.duration_beats
    return total


def _first_anchor_by_measure_and_voice(
    index: AnchorIndex,
) -> dict[tuple[int, int, int, int], Anchor]:
    """Primer ancla de cada (part, staff, measure, voice)."""

    result: dict[tuple[int, int, int, int], Anchor] = {}
    for anchor in index.anchors():
        result.setdefault((anchor.part, anchor.staff, anchor.measure, anchor.voice), anchor)
    return result


def _first_anchor_by_measure(index: AnchorIndex) -> dict[tuple[int, int, int], Anchor]:
    """Primer ancla (evento) de cada compás, en orden determinista (fallback)."""

    result: dict[tuple[int, int, int], Anchor] = {}
    for anchor in index.anchors():
        result.setdefault((anchor.part, anchor.staff, anchor.measure), anchor)
    return result


class MeasureBalanceRule(ValidationRule):
    """La suma de duraciones de cada voz en cada compás debe igualar su métrica."""

    @property
    def rule_id(self) -> str:
        return RULE_ID

    def evaluate(self, document: ScoreDocument) -> list[Finding]:
        first_by_voice = _first_anchor_by_measure_and_voice(document.anchors)
        first_by_measure = _first_anchor_by_measure(document.anchors)
        findings: list[Finding] = []
        for part_index, part in enumerate(document.score.parts):
            for staff_index, staff in enumerate(part.staves):
                for measure in staff.measures:
                    findings.extend(
                        self._evaluate_measure(
                            part_index,
                            staff_index,
                            measure,
                            first_by_voice,
                            first_by_measure,
                        )
                    )
        return findings

    def _evaluate_measure(
        self,
        part_index: int,
        staff_index: int,
        measure: Measure,
        first_by_voice: dict[tuple[int, int, int, int], Anchor],
        first_by_measure: dict[tuple[int, int, int], Anchor],
    ) -> list[Finding]:
        if measure.time_signature is None:
            return []
        expected = _expected_quarter_length(measure.time_signature)

        events_by_voice: dict[int, list[Event]] = {}
        for event in measure.events:
            events_by_voice.setdefault(event.voice, []).append(event)

        if not events_by_voice:
            return []

        findings: list[Finding] = []
        for voice, voice_events in sorted(events_by_voice.items()):
            actual = _voice_durations_sum(voice_events)
            if actual is None or actual == expected:
                continue
            anchor = first_by_voice.get(
                (part_index, staff_index, measure.number, voice)
            ) or first_by_measure.get((part_index, staff_index, measure.number))
            if anchor is None:
                continue
            voice_info = f" (voz {voice})" if len(events_by_voice) > 1 else ""
            findings.append(
                Finding(
                    anchor=anchor,
                    rule_id=RULE_ID,
                    severity=Severity.ERROR,
                    message=(
                        f"El compás {measure.number}{voice_info} suma {actual} negras y su métrica "
                        f"{measure.time_signature} exige {expected}."
                    ),
                    suggested_fix=(
                        f"Ajustar las duraciones del compás {measure.number}{voice_info} "
                        f"para sumar {expected} negras."
                    ),
                )
            )
        return findings
