"""Regla de balance de compás (M2).

Comprueba que la suma de duraciones de notas y silencios de un compás coincida
con su métrica. La duración esperada la aporta el propio valor de dominio
`TimeSignature.quarter_length`, sin dependencias externas. La regla es de **solo
lectura** y ancla el hallazgo al primer evento del compás problemático.

Con varias voces en el compás de un pentagrama, cada voz se comprueba aparte, y una
voz puede salir antes del final del compás si otra que se ve lo completa (ADR-0032):
MusicXML no obliga a rellenarla. Un silencio invisible (el hueco de una voz que entra
a mitad del compás) cuenta como cualquier silencio, pero una voz hecha solo de
silencios invisibles no completa el compás.
"""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

from cadenza.domain import (
    Anchor,
    AnchorIndex,
    EditOp,
    Event,
    EventKind,
    Finding,
    Measure,
    ScoreDocument,
    Severity,
    SuggestedEdit,
    TimeSignature,
)

from ..learned.features import figure_of
from .base import ValidationRule
from .utils import build_event_anchor_map

RULE_ID = "measure.balance"
_DURATION_KINDS = frozenset({EventKind.NOTE, EventKind.REST})


def _is_figure(duration: Fraction) -> bool:
    """Una figura escribible: potencia de dos, con o sin uno o dos puntillos."""
    return figure_of(duration) is not None


def _candidates(
    voice_events: list[Event],
    delta: Fraction,
    anchor_of: dict[int, Anchor],
    end_anchor: Anchor | None,
) -> tuple[SuggestedEdit, ...]:
    """Los arreglos que cuadran el compás de una voz a la que le falta (`delta` > 0) o le
    sobra (`delta` < 0) tiempo (ADR-0036 §3): cambiar la figura de un evento, añadir al
    final un silencio con lo que falta o borrar un evento que dura lo que sobra.

    No toca silencios invisibles ni el primer evento de un acorde, cuya duración comparten
    las demás notas del acorde.
    """
    candidates: list[SuggestedEdit] = []
    deletions: list[SuggestedEdit] = []
    for index, event in enumerate(voice_events):
        anchor = anchor_of.get(index)
        duration = event.duration_beats
        starts_chord = index + 1 < len(voice_events) and voice_events[index + 1].is_chord
        if (
            anchor is None
            or duration is None
            or duration <= 0
            or event.is_chord
            or event.hidden
            or starts_chord
            or event.kind not in _DURATION_KINDS
        ):
            continue
        target = duration + delta
        if target > 0 and _is_figure(target):
            candidates.append(
                SuggestedEdit(
                    op=EditOp.SET_DURATION,
                    anchor=anchor,
                    after={"duration_beats": str(target)},
                )
            )
        if delta < 0 and duration == -delta:
            deletions.append(SuggestedEdit(op=EditOp.DELETE_EVENT, anchor=anchor, after=None))
    if delta > 0 and end_anchor is not None and _is_figure(delta):
        candidates.append(
            SuggestedEdit(
                op=EditOp.INSERT_EVENT,
                anchor=end_anchor,
                after={"kind": EventKind.REST.value, "duration_beats": str(delta)},
            )
        )
    return (*candidates, *deletions)


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
        anchor_map = build_event_anchor_map(document.anchors)
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
                            anchor_map,
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
        anchor_map: dict[tuple[int, int, int, int, int], Anchor],
    ) -> list[Finding]:
        if measure.time_signature is None:
            return []
        expected = _expected_quarter_length(measure.time_signature)

        events_by_voice: dict[int, list[Event]] = {}
        for event in measure.events:
            events_by_voice.setdefault(event.voice, []).append(event)

        if not events_by_voice:
            return []

        sums = {
            voice: _voice_durations_sum(voice_events)
            for voice, voice_events in sorted(events_by_voice.items())
        }
        # Con varias voces, la que sale antes del final no es un error si otra que se ve completa
        # el compás: una voz hecha solo de silencios invisibles no lo completa.
        completed = len(sums) > 1 and any(
            sums[voice] == expected and not all(event.hidden for event in voice_events)
            for voice, voice_events in events_by_voice.items()
        )

        findings: list[Finding] = []
        for voice, actual in sums.items():
            if actual is None or actual == expected or (completed and actual < expected):
                continue
            anchor = first_by_voice.get(
                (part_index, staff_index, measure.number, voice)
            ) or first_by_measure.get((part_index, staff_index, measure.number))
            if anchor is None:
                continue
            voice_info = f" (voz {voice})" if len(events_by_voice) > 1 else ""
            voice_events = events_by_voice[voice]
            anchor_of = {
                index: found
                for index in range(len(voice_events))
                if (
                    found := anchor_map.get((part_index, staff_index, measure.number, voice, index))
                )
                is not None
            }
            end_anchor = (
                replace(anchor_of[0], event_index=len(voice_events), bbox=None, confidence=None)
                if 0 in anchor_of
                else None
            )
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
                    candidates=_candidates(voice_events, expected - actual, anchor_of, end_anchor),
                )
            )
        return findings
