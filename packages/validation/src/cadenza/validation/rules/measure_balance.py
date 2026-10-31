"""`measure.balance`: duración del compás (ADR-0040 §4).

Detecta una voz de un compás cuyas figuras no llenan su capacidad: la métrica del compás o,
en los compases de un hallazgo de `time.signature`, la suma que da ese hallazgo (§5). Dispara
cuando una voz se pasa, y cuando se queda corta y ninguna otra voz que se ve la llena; si
ninguna la llena, cada voz corta se señala aparte (ADR-0032 §4).

No dispara en los falsos positivos conocidos: la anacrusa, el último compás que la completa,
el silencio de compás, una voz hecha solo de silencios invisibles, lo que explica un tresillo
incompleto (que señala `tuplet.incomplete`) y un compás sin métrica.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from fractions import Fraction

from cadenza.domain import (
    Anchor,
    EditOp,
    Event,
    EventKind,
    Finding,
    Measure,
    ScoreDocument,
    Severity,
    SuggestedEdit,
)

from ..language import (
    Phrase,
    a,
    amount,
    capitalize,
    count_figures,
    de,
    figure_of,
    in_beat_figures,
    measure_phrase,
    meter_name,
    note_name,
    number_word,
    position_phrase,
    single_figure,
    voice_phrases,
)
from .base import ValidationRule
from .support import (
    DURATION_KINDS,
    Capacity,
    Key,
    PartMeter,
    active_keys,
    advance,
    anchor_map,
    first_visible,
    incomplete_tuplets,
    is_measure_rest,
    is_visible,
    measure_sum,
    onsets,
    unmarked_triplets_excess,
    voice_sum,
    voices_of,
)

RULE_ID = "measure.balance"


def _is_figure(duration: Fraction) -> bool:
    """Una figura escribible sin tresillo: potencia de dos, con o sin uno o dos puntillos."""
    figure = figure_of(duration)
    return figure is not None and not figure.tuplet


def _candidates(
    voice_events: Sequence[Event],
    delta: Fraction,
    anchor_of: Mapping[int, Anchor],
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
            or event.kind not in DURATION_KINDS
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


def _explained_by_tuplets(events: Sequence[Event], delta: Fraction) -> bool:
    """Lo que falta (`delta` > 0) o sobra es exactamente lo que explican sus tresillos
    incompletos (§6): entonces solo se señala el tresillo."""
    groups = incomplete_tuplets(events)
    if not groups:
        return False
    if delta > 0:
        return delta == sum((group.deficit for group in groups), Fraction(0))
    return -delta == sum((group.surplus for group in groups), Fraction(0))


def _meter_phrase(capacity: Capacity) -> Phrase:
    """«el 4/4» o, en un tramo de `time.signature`, «las cuatro negras que suman los demás
    compases»."""
    if capacity.span is None:
        return Phrase("el", meter_name(capacity.signature))
    total = in_beat_figures(capacity.value, capacity.signature.beat_type)
    if total.startswith("una "):
        return Phrase("la", f"{total[4:]} que suman los demás compases")
    return Phrase("las", f"{total} que suman los demás compases")


def _event_noun(event: Event, fifths: int) -> str:
    if event.kind is EventKind.REST:
        return "silencio"
    return note_name(event.pitch, fifths=fifths)


class MeasureBalanceRule(ValidationRule):
    """Las figuras de cada voz de cada compás llenan su capacidad, ni más ni menos."""

    @property
    def rule_id(self) -> str:
        return RULE_ID

    def evaluate(self, document: ScoreDocument) -> list[Finding]:
        anchors = anchor_map(document.anchors)
        findings: list[Finding] = []
        for part_index, part in enumerate(document.score.parts):
            meter = PartMeter.of(part, part_index)
            for staff_index, staff in enumerate(part.staves):
                keys = active_keys(staff)
                measures = staff.measures
                for position, measure in enumerate(measures):
                    capacity = meter.capacity(measure)
                    if capacity is None:
                        continue
                    findings.extend(
                        self._evaluate_measure(
                            anchors,
                            (part_index, staff_index),
                            measure,
                            capacity,
                            keys[position],
                            first=position == 0 and len(measures) > 1,
                            last=position == len(measures) - 1 and len(measures) > 1,
                            opening=measures[0],
                            opening_capacity=meter.capacity(measures[0]),
                        )
                    )
        return findings

    def _evaluate_measure(
        self,
        anchors: Mapping[Key, Anchor],
        where: tuple[int, int],
        measure: Measure,
        capacity: Capacity,
        fifths: int,
        *,
        first: bool,
        last: bool,
        opening: Measure,
        opening_capacity: Capacity | None,
    ) -> list[Finding]:
        voices = voices_of(measure)
        seen = {voice: events for voice, events in voices.items() if is_visible(events)}
        if not seen:
            return []
        full = capacity.value
        sums = {voice: voice_sum(events) for voice, events in seen.items()}
        names = voice_phrases(voices)
        completed = any(total == full for total in sums.values())
        opening_sum = measure_sum(opening)
        findings: list[Finding] = []
        for voice, events in seen.items():
            total = sums[voice]
            if total == full or is_measure_rest(
                events, capacity.value, capacity.signature.quarter_length
            ):
                continue
            if total < full:
                if completed or first:
                    continue
                if (
                    last
                    and opening_sum is not None
                    and opening_capacity is not None
                    and opening_sum < opening_capacity.value
                    and opening_sum + total == full
                ):
                    continue
            if _explained_by_tuplets(events, full - total):
                continue
            finding = self._finding(
                anchors, where, measure, voice, events, capacity, fifths, names.get(voice)
            )
            if finding is not None:
                findings.append(finding)
        return findings

    def _finding(
        self,
        anchors: Mapping[Key, Anchor],
        where: tuple[int, int],
        measure: Measure,
        voice: int,
        events: Sequence[Event],
        capacity: Capacity,
        fifths: int,
        name: Phrase | None,
    ) -> Finding | None:
        part_index, staff_index = where
        anchor = first_visible(anchors, part_index, staff_index, measure, voice)
        if anchor is None:
            return None
        full = capacity.value
        total = voice_sum(events)
        delta = full - total
        anchor_of = {
            index: found
            for index in range(len(events))
            if (found := anchors.get((part_index, staff_index, measure.number, voice, index)))
            is not None
        }
        end_anchor = (
            replace(anchor_of[0], event_index=len(events), bbox=None, confidence=None)
            if 0 in anchor_of
            else None
        )
        message, fix = (
            self._short(measure, events, capacity, name)
            if delta > 0
            else self._long(measure, events, capacity, fifths, name)
        )
        return Finding(
            anchor=anchor,
            rule_id=RULE_ID,
            severity=Severity.ERROR,
            message=message,
            suggested_fix=fix,
            candidates=_candidates(events, delta, anchor_of, end_anchor),
        )

    @staticmethod
    def _subject(measure: Measure, name: Phrase | None, verb: str) -> str:
        """«Al compás 3 le falta» o «En el compás 7, a la voz de arriba le falta»; con «sobra»,
        «En el compás 2 sobra»."""
        where = measure_phrase(measure.number)
        if name is not None:
            return f"En {where}, {a(name)} le {verb}"
        if verb == "falta":
            return f"{capitalize(a(where))} le falta"
        return f"En {where} sobra"

    @staticmethod
    def _whose(name: Phrase | None) -> str:
        return "del compás" if name is None else de(name)

    def _short(
        self,
        measure: Measure,
        events: Sequence[Event],
        capacity: Capacity,
        name: Phrase | None,
    ) -> tuple[str, str]:
        delta = capacity.value - voice_sum(events)
        how_much = amount(delta) or "duración"
        ends = position_phrase(voice_sum(events), capacity.signature)
        figures = "las figuras" if name is None else "sus figuras"
        message = (
            f"{self._subject(measure, name, 'falta')} {how_much} para completar "
            f"{_meter_phrase(capacity)}: {figures} se acaban antes {de(ends)}."
        )
        fix = (
            f"Revisa las figuras {self._whose(name)}: puede que alguna sea más larga de lo que "
            "se leyó"
        )
        alone = single_figure(delta)
        fix += f", o que falte una nota o un silencio de {alone}." if alone else "."
        return message, fix

    def _long(
        self,
        measure: Measure,
        events: Sequence[Event],
        capacity: Capacity,
        fifths: int,
        name: Phrase | None,
    ) -> tuple[str, str]:
        full = capacity.value
        excess = voice_sum(events) - full
        how_much = amount(excess)
        head = self._subject(measure, name, "sobra")
        head += f" {how_much}" if how_much else " duración"
        head += f" para {_meter_phrase(capacity)}"
        triplets = unmarked_triplets_excess(capacity.signature, full, events)
        if triplets is not None:
            durations = {event.duration_beats for event in triplets}
            noun = (
                count_figures(len(triplets), next(iter(durations)))
                if len(durations) == 1
                else f"{number_word(len(triplets))} figuras"
            )
            return (
                f"{head}: sus {noun} van en grupos de tres, como los tresillos.",
                "Si en la partitura son tresillos, márcalos como tresillos; si no, revisa las "
                "figuras.",
            )
        starts = onsets(events)
        detail = "el compás ya está lleno"
        for index, event in enumerate(events):
            if event.is_chord or event.hidden:
                continue
            if starts[index] + advance(event) <= full:
                continue
            noun = _event_noun(event, fifths)
            if starts[index] < full:
                where = position_phrase(starts[index], capacity.signature)
                figure = (
                    f", {count_figures(1, event.duration_beats)},"
                    if figure_of(event.duration_beats) is not None
                    else ""
                )
                detail = f"el {noun} {de(where)}{figure} se sale del compás"
            else:
                detail = f"el compás ya está lleno cuando llega el {noun}"
            break
        fix = (
            f"Revisa las figuras {self._whose(name)}: puede que alguna sea más corta de lo que "
            "se leyó"
        )
        alone = single_figure(excess)
        lasts = any(
            not event.is_chord and not event.hidden and event.duration_beats == excess
            for event in events
        )
        fix += f", o que sobre una nota de {alone}." if alone and lasts else "."
        return f"{head}: {detail}.", fix
