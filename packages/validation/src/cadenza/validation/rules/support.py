"""Apoyo común de las reglas: voces, sumas, capacidad de cada compás y tresillos (ADR-0040 §15.2).

Lo usan `measure.balance`, `time.signature` y `tuplet.incomplete`, para que las tres digan lo
mismo de un compás: qué suma cada voz, cuál es su capacidad (la métrica o la suma que da un
hallazgo de `time.signature`) y qué grupos de tresillo tiene.

- Una nota de duración 0 o nula es de adorno (ADR-0028) y suma 0; un silencio así suma una
  negra, que es como se exporta.
- De un acorde solo suma la primera nota.
- El pentagrama es el `Staff` del `ScoreIR` en toda la página, no una línea del sistema.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Final

from cadenza.domain import (
    Anchor,
    AnchorIndex,
    Clef,
    Event,
    EventKind,
    KeySignature,
    Measure,
    Part,
    ScoreDocument,
    Staff,
    TimeSignature,
)

from ..language import is_compound, meter_of

_DURATION_KINDS: Final[frozenset[EventKind]] = frozenset({EventKind.NOTE, EventKind.REST})
_QUARTER: Final[Fraction] = Fraction(1)

Key = tuple[int, int, int, int, int]
"""(parte, pentagrama, número de compás, voz, índice del evento en la voz)."""


# --- Eventos y voces -----------------------------------------------------------------------


def is_grace(event: Event) -> bool:
    """Una nota de adorno: sin duración o con duración 0 (ADR-0028)."""
    return event.kind is EventKind.NOTE and (
        event.duration_beats is None or event.duration_beats <= 0
    )


def advance(event: Event) -> Fraction:
    """Lo que avanza un evento en su voz."""
    if event.kind not in _DURATION_KINDS or event.is_chord:
        return Fraction(0)
    duration = event.duration_beats
    if duration is None or duration <= 0:
        return Fraction(0) if event.kind is EventKind.NOTE else _QUARTER
    return duration


def voices_of(measure: Measure) -> dict[int, tuple[Event, ...]]:
    """Los eventos de cada voz de un compás, en orden de voz."""
    grouped: dict[int, list[Event]] = {}
    for event in measure.events:
        grouped.setdefault(event.voice, []).append(event)
    return {voice: tuple(grouped[voice]) for voice in sorted(grouped)}


def onsets(events: Sequence[Event]) -> list[Fraction]:
    """Dónde empieza cada evento de una voz, desde el principio del compás y con los silencios
    invisibles; las notas de un acorde empiezan con la primera."""
    result: list[Fraction] = []
    position = Fraction(0)
    last_start = Fraction(0)
    for event in events:
        if event.is_chord:
            result.append(last_start)
            continue
        result.append(position)
        last_start = position
        position += advance(event)
    return result


def voice_sum(events: Sequence[Event]) -> Fraction:
    return sum((advance(event) for event in events), Fraction(0))


def is_visible(events: Sequence[Event]) -> bool:
    """Una voz se ve si tiene algo que no es un silencio invisible (ADR-0032)."""
    return any(not event.hidden for event in events)


def measure_sum(measure: Measure) -> Fraction | None:
    """Lo que suma un compás: su voz más larga que se ve, o None si no se ve ninguna."""
    sums = [voice_sum(events) for events in voices_of(measure).values() if is_visible(events)]
    return max(sums) if sums else None


def figures(events: Sequence[Event]) -> list[Event]:
    """Las figuras de una voz que se ven: sin notas de acorde ni de adorno."""
    return [
        event
        for event in events
        if not event.hidden
        and not event.is_chord
        and not is_grace(event)
        and event.kind in _DURATION_KINDS
    ]


def in_unmarked_triplets(events: Sequence[Event]) -> list[Event] | None:
    """Las figuras de la voz si todas van en grupos seguidos de tres iguales, o None."""
    found = figures(events)
    if not found or len(found) % 3:
        return None
    for start in range(0, len(found), 3):
        trio = {event.duration_beats for event in found[start : start + 3]}
        if len(trio) != 1:
            return None
    return found


def unmarked_triplets_excess(
    signature: TimeSignature | None, capacity: Fraction, events: Sequence[Event]
) -> list[Event] | None:
    """Tresillos sin marcar (ADR-0040 §4): en un compás simple, la voz tiene justo la mitad
    de la capacidad de más y todas sus figuras van en grupos seguidos de tres iguales."""
    if signature is None or is_compound(signature):
        return None
    if voice_sum(events) != capacity * Fraction(3, 2):
        return None
    return in_unmarked_triplets(events)


# --- Tresillos -----------------------------------------------------------------------------


def _has_three(duration: Fraction) -> bool:
    return duration.denominator % 3 == 0


@dataclass(frozen=True, slots=True)
class TupletGroup:
    """Una serie de eventos seguidos de una voz con el factor 3 en el denominador (ADR-0040 §6).

    De un acorde solo cuenta la primera nota y las notas de adorno no cuentan.
    """

    indices: tuple[int, ...]
    durations: tuple[Fraction, ...]
    onset: Fraction

    @property
    def total(self) -> Fraction:
        return sum(self.durations, Fraction(0))

    @property
    def unit(self) -> Fraction:
        return min(self.durations)

    @property
    def complete(self) -> bool:
        """Su suma es una figura sin tresillo: su denominador es una potencia de dos."""
        denominator = self.total.denominator
        return denominator & (denominator - 1) == 0

    @property
    def units(self) -> int | None:
        count = self.total / self.unit
        return int(count) if count.denominator == 1 else None

    @property
    def missing_units(self) -> int | None:
        """Unidades que le faltan a la suma para llegar al siguiente múltiplo de tres."""
        units = self.units
        if self.complete or units is None:
            return None
        return (3 - units % 3) % 3 or None

    @property
    def deficit(self) -> Fraction:
        missing = self.missing_units
        return Fraction(0) if missing is None else missing * self.unit

    @property
    def surplus(self) -> Fraction:
        units = self.units
        if self.complete or units is None:
            return Fraction(0)
        return (units % 3) * self.unit


def tuplet_groups(events: Sequence[Event]) -> list[TupletGroup]:
    """Los grupos de tresillo de una voz (ADR-0040 §6). Los de cinco o siete no son tresillos."""
    groups: list[TupletGroup] = []
    starts = onsets(events)
    current: list[int] = []
    durations: list[Fraction] = []

    def close() -> None:
        if current:
            groups.append(TupletGroup(tuple(current), tuple(durations), starts[current[0]]))
        current.clear()
        durations.clear()

    for index, event in enumerate(events):
        if event.is_chord or is_grace(event) or event.kind not in _DURATION_KINDS:
            continue
        duration = event.duration_beats
        if duration is not None and duration > 0 and _has_three(duration):
            current.append(index)
            durations.append(duration)
        else:
            close()
    close()
    return groups


def incomplete_tuplets(events: Sequence[Event]) -> list[TupletGroup]:
    return [group for group in tuplet_groups(events) if group.missing_units is not None]


# --- Capacidad del compás: tramos y rachas de `time.signature` -----------------------------


@dataclass(frozen=True, slots=True)
class MeterSpan:
    """Un tramo o una racha cuyos compases suman otra cosa que su métrica (ADR-0040 §5).

    `capacity` (S) es la capacidad de los compases de `numbers`, en todos los pentagramas de
    la parte. `whole` dice si es el caso 1 (todo el tramo) o el 2 (desde un compás).
    """

    part: int
    signature: TimeSignature
    capacity: Fraction
    numbers: tuple[int, ...]
    matching: tuple[int, ...]
    measured: tuple[int, ...]
    whole: bool

    @property
    def start(self) -> int:
        return self.numbers[0]

    @property
    def proposed(self) -> TimeSignature | None:
        return meter_of(self.capacity, self.signature.beat_type)


def _tramos(staff: Staff) -> list[list[int]]:
    """Posiciones seguidas de un pentagrama con la misma métrica leída."""
    tramos: list[list[int]] = []
    previous: TimeSignature | None = None
    for position, measure in enumerate(staff.measures):
        signature = measure.time_signature
        if signature is None:
            previous = None
            continue
        if tramos and signature == previous:
            tramos[-1].append(position)
        else:
            tramos.append([position])
        previous = signature
    return tramos


def _triplet_sums(staff: Staff, positions: Sequence[int], signature: TimeSignature) -> bool:
    """Si los compases que suman la métrica más su mitad van en tresillos sin marcar."""
    if is_compound(signature):
        return False
    for position in positions:
        measure = staff.measures[position]
        voices = [events for events in voices_of(measure).values() if is_visible(events)]
        longest = max(voices, key=voice_sum)
        if in_unmarked_triplets(longest) is None:
            return False
    return True


@dataclass(frozen=True, slots=True)
class _Admissible:
    """Si una suma S de un tramo da un hallazgo: S es otra que la métrica, se escribe como
    métrica y los compases que la suman no son tresillos sin marcar (ADR-0040 §5)."""

    staff: Staff
    signature: TimeSignature

    def __call__(self, total: Fraction, positions: Sequence[int]) -> bool:
        meter = self.signature.quarter_length
        if total == meter or meter_of(total, self.signature.beat_type) is None:
            return False
        tuplets = total == meter * Fraction(3, 2)
        return not (tuplets and _triplet_sums(self.staff, positions, self.signature))


def meter_spans(part: Part, part_index: int) -> list[MeterSpan]:
    """Los hallazgos de `time.signature` de una parte, calculados sobre su pentagrama de
    arriba (ADR-0040 §5)."""
    if not part.staves:
        return []
    staff = part.staves[0]
    last = len(staff.measures) - 1
    spans: list[MeterSpan] = []
    for tramo in _tramos(staff):
        signature = staff.measures[tramo[0]].time_signature
        assert signature is not None
        meter = signature.quarter_length
        measured = [position for position in tramo if 0 < position < last]
        sums: dict[int, Fraction] = {}
        for position in measured:
            total = measure_sum(staff.measures[position])
            if total is not None:
                sums[position] = total

        admissible = _Admissible(staff, signature)
        numbers = [staff.measures[position].number for position in tramo]
        measured_numbers = tuple(staff.measures[position].number for position in measured)
        if len(measured) >= 2:
            counts = Counter(sums.values())
            whole = [
                total
                for total, count in counts.most_common()
                if total != meter and count >= 2 and count * 2 > len(measured)
            ]
            if whole:
                total = whole[0]
                matching = [position for position in measured if sums.get(position) == total]
                if admissible(total, matching):
                    spans.append(
                        MeterSpan(
                            part=part_index,
                            signature=signature,
                            capacity=total,
                            numbers=tuple(numbers),
                            matching=tuple(staff.measures[p].number for p in matching),
                            measured=measured_numbers,
                            whole=True,
                        )
                    )
                    continue
        spans.extend(_runs(staff, part_index, signature, measured, sums, admissible))
    return spans


def _runs(
    staff: Staff,
    part_index: int,
    signature: TimeSignature,
    measured: Sequence[int],
    sums: Mapping[int, Fraction],
    admissible: _Admissible,
) -> Iterator[MeterSpan]:
    """Rachas de tres o más medibles seguidos con la misma suma distinta de la métrica."""
    run: list[int] = []

    def flush() -> Iterator[MeterSpan]:
        if len(run) >= 3 and admissible(sums[run[0]], run):
            numbers = tuple(staff.measures[position].number for position in run)
            yield MeterSpan(
                part=part_index,
                signature=signature,
                capacity=sums[run[0]],
                numbers=numbers,
                matching=numbers,
                measured=numbers,
                whole=False,
            )

    for position in measured:
        total = sums.get(position)
        follows = bool(run) and position == run[-1] + 1 and total == sums[run[0]]
        if follows:
            run.append(position)
            continue
        yield from flush()
        run = [position] if total is not None and total != signature.quarter_length else []
    yield from flush()


@dataclass(frozen=True, slots=True)
class Capacity:
    """Lo que tiene que sumar un compás: su métrica o la S de un hallazgo de `time.signature`."""

    value: Fraction
    signature: TimeSignature
    span: MeterSpan | None = None


@dataclass(slots=True)
class PartMeter:
    """La capacidad de cada compás de una parte (por número de compás), común a sus pentagramas."""

    spans: list[MeterSpan] = field(default_factory=list)
    _by_number: dict[int, MeterSpan] = field(default_factory=dict)

    @classmethod
    def of(cls, part: Part, part_index: int) -> PartMeter:
        meter = cls(spans=meter_spans(part, part_index))
        for span in meter.spans:
            for number in span.numbers:
                meter._by_number[number] = span
        return meter

    def capacity(self, measure: Measure) -> Capacity | None:
        signature = measure.time_signature
        if signature is None:
            return None
        span = self._by_number.get(measure.number)
        if span is not None and span.signature == signature:
            return Capacity(span.capacity, signature, span)
        return Capacity(signature.quarter_length, signature)


# --- Contexto de las reglas ----------------------------------------------------------------


def anchor_map(anchors: AnchorIndex) -> dict[Key, Anchor]:
    return {
        (anchor.part, anchor.staff, anchor.measure, anchor.voice, anchor.event_index): anchor
        for anchor in anchors.anchors()
    }


def first_visible(
    anchors: Mapping[Key, Anchor],
    part: int,
    staff: int,
    measure: Measure,
    voice: int | None = None,
) -> Anchor | None:
    """El primer evento que se ve de una voz (o, sin voz, del compás): un silencio invisible no
    se puede elegir (ADR-0032)."""
    for current, events in voices_of(measure).items():
        if voice is not None and current != voice:
            continue
        for index, event in enumerate(events):
            if not event.hidden:
                found = anchors.get((part, staff, measure.number, current, index))
                if found is not None:
                    return found
    return None


def active_keys(staff: Staff) -> list[int]:
    """La armadura vigente (quintas) en cada compás de un pentagrama."""
    fifths = 0
    result: list[int] = []
    for measure in staff.measures:
        key: KeySignature | None = measure.key_signature
        if key is not None:
            fifths = key.fifths
        result.append(fifths)
    return result


def active_clefs(staff: Staff, default: Clef) -> list[Clef]:
    """La clave vigente en cada compás de un pentagrama."""
    clef = default
    result: list[Clef] = []
    for measure in staff.measures:
        clef = measure.clef or clef
        result.append(clef)
    return result


def staves(document: ScoreDocument) -> Iterator[tuple[int, Part, int, Staff]]:
    for part_index, part in enumerate(document.score.parts):
        for staff_index, staff in enumerate(part.staves):
            yield part_index, part, staff_index, staff
