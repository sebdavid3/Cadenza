"""Etapa de Cadenza tras HOMR: el compás por tramos, C y ¢, y los tresillos implícitos (ADR-0059).

HOMR 0.7.0 solo lee el denominador del compás (`timeSignature/{denominador}`) y le pone a todos
los compases de un pentagrama el mismo numerador, la mediana de lo que suman sus compases; no
distingue C de 4/4 ni ¢ de 2/2; y quita los tresillos de los compases que suman menos que la
mediana de la página. Esta etapa corre después, sobre el `ScoreIR` que HOMR da, y fuera de
`HOMREngine`, de modo que los experimentos que miden HOMR solo no cambian.

Cada rasgo se activa por separado (`MeterFeature`):

- **`numerator`**: el numerador de cada tramo, entre los cambios de compás que leyó HOMR, sale
  de lo que suman sus compases: la suma más repetida (a igualdad, la mayor) de las que dan un
  numerador entero, sin el primer compás si suma menos que la mediana de los demás (la
  anacrusa) ni el último si también suma menos (el compás que la completa o un incipit
  cortado). El denominador es el leído.
- **`symbol`**: un tramo en 4/4 se escribe C, y uno en 2/2, ¢. HOMR no ve el símbolo; es lo
  que se imprime casi siempre (en PrIMuS, 775 C frente a 5 4/4 y 284 ¢ frente a 19 2/2).
- **`implicit_tuplets`**: un compás que suma más que el tramo y cuadra exactamente si todas sus
  figuras de un mismo valor (en múltiplo de tres) pasan a tresillo se lee con tresillos; los
  tresillos que HOMR ya leyó no se tocan. Hace falta una señal: tresillos marcados de esa figura
  en el pentagrama, o dos compases o más que cuadran con la duración de otro pentagrama de la
  parte. Con `numerator`, el compás del tramo se decide a la vez que los tresillos: 3/2 con
  corcheas y ¢ con tresillos de corchea cuadran igual, y gana la medida que explica más compases.

Lo que la etapa cambió queda en la procedencia del documento (`Provenance.omr_stages`).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from fractions import Fraction
from typing import Any, Final

from cadenza.domain import (
    Measure,
    Part,
    ScoreDocument,
    ScoreIR,
    TimeSignature,
    build_anchor_index,
)
from cadenza.domain.time_signature import COMMON, CUT, same_time_notation

METER_STAGE_ID: Final[str] = "meter"
# Sube cuando cambia lo que la etapa decide con la misma entrada.
METER_STAGE_VERSION: Final[str] = "1"

_MAX_BEATS: Final[int] = 32
# Figuras sin puntillo que pueden pasar a tresillo de 3:2, en negras: de la redonda a la fusa.
_PLAIN_FIGURES: Final[frozenset[Fraction]] = frozenset(Fraction(2) ** k for k in range(-3, 3))
_TRIPLET: Final[Fraction] = Fraction(2, 3)


class MeterFeature(StrEnum):
    """Cada rasgo de la etapa, que se activa por separado (ADR-0059 §3)."""

    NUMERATOR = "numerator"
    SYMBOL = "symbol"
    IMPLICIT_TUPLETS = "implicit_tuplets"


ALL_METER_FEATURES: Final[frozenset[MeterFeature]] = frozenset(MeterFeature)


def parse_meter_features(text: str | None) -> frozenset[MeterFeature]:
    """Lee una lista de rasgos separada por comas (``""`` o ``"none"``: ninguno; ``"all"``: todos).

    Un nombre desconocido es un error: una errata no debe apagar un rasgo en silencio."""

    if text is None:
        return frozenset()
    names = [item.strip().lower() for item in text.split(",") if item.strip()]
    if names in ([], ["none"]):
        return frozenset()
    if names == ["all"]:
        return ALL_METER_FEATURES
    known = {feature.value: feature for feature in MeterFeature}
    unknown = sorted(name for name in names if name not in known)
    if unknown:
        raise ValueError(
            f"rasgos de la etapa del compás desconocidos: {', '.join(unknown)} "
            f"(válidos: {', '.join(sorted(known))}, 'all' o 'none')"
        )
    return frozenset(known[name] for name in names)


def features_label(features: Collection[MeterFeature]) -> list[str]:
    """Los rasgos en un orden estable, para la procedencia y los resultados."""

    return [feature.value for feature in MeterFeature if feature in features]


# --------------------------------------------------------------------------------------------
# Sumas de un compás
# --------------------------------------------------------------------------------------------


def _voice_sums(measure: Measure) -> dict[int, Fraction]:
    sums: dict[int, Fraction] = {}
    for event in measure.events:
        if event.is_chord or event.duration_beats is None:
            continue
        sums[event.voice] = sums.get(event.voice, Fraction(0)) + event.duration_beats
    return sums


def measure_sum(measure: Measure) -> Fraction:
    """Lo que dura un compás en negras: la voz más larga (sin las notas de un acorde)."""

    return max(_voice_sums(measure).values(), default=Fraction(0))


def _triplet_plan(
    measure: Measure, capacity: Fraction, allowed: Collection[Fraction]
) -> dict[int, Fraction] | None:
    """Qué figura pasa a tresillo en cada voz para que el compás dure `capacity`, o None.

    Una voz que dura más que el compás cuadra si todas sus figuras de un valor sin puntillo de
    `allowed` (notas y silencios, en múltiplo de tres) pasan a tresillo de 3:2 y entonces dura
    justo `capacity`. Si cuadra con más de una figura, es ambiguo y no cuenta. Todas las voces
    tienen que acabar durando como mucho `capacity`, y alguna, cambiar. Las figuras que ya son
    de tresillo (las que HOMR leyó marcadas) y los silencios invisibles (el hueco de una voz,
    ADR-0032) no se tocan."""

    plan: dict[int, Fraction] = {}
    for voice, total in _voice_sums(measure).items():
        if total <= capacity:
            continue
        counts: Counter[Fraction] = Counter(
            event.duration_beats
            for event in measure.events
            if event.voice == voice
            and not event.is_chord
            and not event.hidden
            and event.duration_beats is not None
            and event.duration_beats in allowed
        )
        fits = [
            figure
            for figure, count in counts.items()
            if count % 3 == 0 and total - count * figure / 3 == capacity
        ]
        if len(fits) != 1:
            return None
        plan[voice] = fits[0]
    return plan or None


def _apply_triplets(measure: Measure, plan: Mapping[int, Fraction]) -> Measure:
    events = tuple(
        (
            replace(event, duration_beats=event.duration_beats * _TRIPLET)
            if event.duration_beats is not None
            and not event.hidden
            and plan.get(event.voice) == event.duration_beats
            else event
        )
        for event in measure.events
    )
    return replace(measure, events=events)


def marked_figures(measures: Sequence[Measure]) -> list[frozenset[Fraction]]:
    """Para cada compás de un pentagrama, las figuras que ya salieron en tresillo hasta él.

    Un tresillo marcado (una figura con un 3 en el denominador, ADR-0044 §3) dice la figura sin
    puntillo que vale 3/2 de ella: los tresillos de corchea (1/3) dicen «corchea» (1/2). Cuenta
    el propio compás y los anteriores del tramo, no los siguientes. Un silencio invisible no es un
    tresillo marcado: es un hueco calculado al importar (ADR-0032)."""

    seen: set[Fraction] = set()
    result: list[frozenset[Fraction]] = []
    for measure in measures:
        for event in measure.events:
            duration = event.duration_beats
            if duration is not None and not event.hidden and duration.denominator % 3 == 0:
                base = duration / _TRIPLET
                if base in _PLAIN_FIGURES:
                    seen.add(base)
        result.append(frozenset(seen))
    return result


# --------------------------------------------------------------------------------------------
# Tramos y capacidad
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Segment:
    """Un tramo de una parte: compases [start, end) con la misma indicación leída por HOMR."""

    start: int
    end: int
    read: TimeSignature


def _part_columns(part: Part) -> list[tuple[Measure, ...]] | None:
    """Los compases de la parte por posición (uno por pentagrama), o None si no se alinean."""

    if not part.staves:
        return None
    count = len(part.staves[0].measures)
    if any(len(staff.measures) != count for staff in part.staves):
        return None
    columns = [tuple(staff.measures[i] for staff in part.staves) for i in range(count)]
    for column in columns:
        first = column[0]
        if any(
            m.number != first.number
            or not same_time_notation(m.time_signature, first.time_signature)
            for m in column[1:]
        ):
            return None
    return columns


def segments(columns: Sequence[Sequence[Measure]]) -> list[Segment]:
    """Los tramos entre los cambios de compás que leyó HOMR; sin indicación no hay tramo."""

    found: list[Segment] = []
    start = 0
    for index in range(1, len(columns) + 1):
        if index < len(columns) and same_time_notation(
            columns[index][0].time_signature, columns[start][0].time_signature
        ):
            continue
        read = columns[start][0].time_signature
        if read is not None:
            found.append(Segment(start, index, read))
        start = index
    return found


def _numerator(capacity: Fraction, beat_type: int) -> int | None:
    beats = capacity * beat_type / 4
    if beats.denominator != 1 or not 1 <= beats <= _MAX_BEATS:
        return None
    return int(beats)


@dataclass(frozen=True, slots=True)
class _Cell:
    staff: int
    position: int
    measure: Measure
    total: Fraction
    marked: frozenset[Fraction]


def _cells(columns: Sequence[Sequence[Measure]]) -> list[_Cell]:
    """Los compases de un tramo, por pentagrama, con lo que suman y sus tresillos marcados."""

    staves = len(columns[0]) if columns else 0
    marked = [marked_figures([column[s] for column in columns]) for s in range(staves)]
    return [
        _Cell(s, i, column[s], measure_sum(column[s]), marked[s][i])
        for i, column in enumerate(columns)
        for s in range(staves)
    ]


def _usual(values: Iterable[Fraction]) -> Fraction:
    """La mediana (la menor de las dos centrales, si son pares) de lo que suman los demás."""

    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 2]


def _core(cells: Sequence[_Cell]) -> list[_Cell]:
    """Los compases con contenido, sin la anacrusa ni el último compás si suman menos que lo que
    suelen sumar los demás (el que completa la anacrusa o el de un incipit cortado). Se compara
    con la mediana de los demás, no con el más largo: un compás leído de más no debe quitarle el
    voto a un primer o un último compás completos."""

    longest: dict[int, Fraction] = {}
    for cell in cells:
        if cell.total > 0:
            longest[cell.position] = max(longest.get(cell.position, Fraction(0)), cell.total)
    positions = sorted(longest)
    first, last = 0, len(positions)
    if last - first >= 3 and longest[positions[first]] < _usual(
        longest[p] for p in positions[first + 1 : last]
    ):
        first += 1
    if last - first >= 3 and longest[positions[last - 1]] < _usual(
        longest[p] for p in positions[first : last - 1]
    ):
        last -= 1
    kept = set(positions[first:last])
    return [cell for cell in cells if cell.position in kept and cell.total > 0]


def _triplet_plans(
    cells: Sequence[_Cell], capacity: Fraction, signal: Sequence[_Cell]
) -> dict[tuple[int, int], dict[int, Fraction]]:
    """Los compases (pentagrama, posición) que pasan a tresillos para durar `capacity`.

    Hace falta una señal de que hay tresillos sin marcar:

    - que el pentagrama ya tenga tresillos marcados de esa figura en el tramo, en ese compás o
      antes (al estilo de `implicitTuplets` de Audiveris); o
    - que otro pentagrama de la parte tenga compases que duran justo `capacity` (la duración del
      compás es de la parte) y que **al menos dos** compases del pentagrama cuadren así: un solo
      compás leído de más que cuadra por casualidad no basta.

    `signal` son los compases que cuentan para la segunda señal, los mismos al votar el compás
    del tramo y al aplicar los tresillos: sin la anacrusa ni el último si suman menos."""

    confirmed = {cell.staff for cell in signal if cell.total == capacity}
    marked: dict[tuple[int, int], dict[int, Fraction]] = {}
    by_part: dict[tuple[int, int], dict[int, Fraction]] = {}
    for cell in cells:
        if cell.total <= capacity:
            continue
        plan = _triplet_plan(cell.measure, capacity, cell.marked) if cell.marked else None
        if plan is not None:
            marked[(cell.staff, cell.position)] = plan
        elif confirmed - {cell.staff}:
            plan = _triplet_plan(cell.measure, capacity, _PLAIN_FIGURES)
            if plan is not None:
                by_part[(cell.staff, cell.position)] = plan
    per_staff = Counter(staff for staff, _ in by_part)
    return marked | {key: plan for key, plan in by_part.items() if per_staff[key[0]] >= 2}


def choose_capacity(
    columns: Sequence[Sequence[Measure]], beat_type: int, *, with_triplets: bool
) -> Fraction | None:
    """La duración (en negras) del compás de un tramo a partir de lo que suman sus compases.

    Cada compás de cada pentagrama vota por lo que suma, si esa suma da un numerador entero de 1
    a 32 con el denominador leído (una que no lo da es una lectura de más o de menos: con
    denominador 4, nueve corcheas no son ningún compás); con `with_triplets`, también por la
    duración a la que cuadra con tresillos (`_triplet_plans`). Gana la más votada y, a igualdad,
    la mayor. Sin ninguna suma así, None: se queda la lectura del motor."""

    cells = _core(_cells(columns))
    candidates = {cell.total for cell in cells if _numerator(cell.total, beat_type) is not None}
    if not candidates:
        return None
    votes: Counter[Fraction] = Counter()
    for capacity in candidates:
        votes[capacity] = sum(1 for cell in cells if cell.total == capacity)
        if with_triplets:
            votes[capacity] += len(_triplet_plans(cells, capacity, cells))
    return max(votes.items(), key=lambda item: (item[1], item[0]))[0]


# --------------------------------------------------------------------------------------------
# La etapa
# --------------------------------------------------------------------------------------------


def _signature(read: TimeSignature, beats: int, with_symbol: bool) -> TimeSignature:
    """La indicación reconocida: la métrica del tramo y, con `symbol`, C o ¢. Si la métrica es
    la leída y no se pide el símbolo, se queda la lectura tal cual (con su grafía, si el motor
    la diera)."""

    meter = (beats, read.beat_type)
    if with_symbol and meter == (4, 4):
        return TimeSignature(4, 4, COMMON)
    if with_symbol and meter == (2, 2):
        return TimeSignature(2, 2, CUT)
    if meter == (read.beats, read.beat_type) and (not with_symbol or read.symbol is None):
        return read
    return TimeSignature(*meter)


def _label(signature: TimeSignature) -> str:
    return {COMMON: "C", CUT: "¢"}.get(signature.symbol or "", str(signature))


@dataclass(frozen=True, slots=True)
class MeterStageReport:
    """Lo que la etapa decidió y cambió, para la procedencia (ADR-0059 §5)."""

    features: tuple[str, ...]
    segments: tuple[dict[str, Any], ...] = ()
    tuplets: tuple[dict[str, Any], ...] = ()
    skipped_parts: tuple[int, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.tuplets) or any(item["changed"] for item in self.segments)

    def to_primitive(self) -> dict[str, Any]:
        return {
            "version": METER_STAGE_VERSION,
            "features": list(self.features),
            "segments": [dict(item) for item in self.segments],
            "tuplets": [dict(item) for item in self.tuplets],
            "skipped_parts": list(self.skipped_parts),
        }


@dataclass(slots=True)
class _Changes:
    segments: list[dict[str, Any]] = field(default_factory=list)
    tuplets: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[int] = field(default_factory=list)


def _recognize_part(
    part: Part, part_index: int, features: frozenset[MeterFeature], changes: _Changes
) -> Part:
    columns = _part_columns(part)
    if columns is None:
        changes.skipped.append(part_index)
        return part
    with_symbol = MeterFeature.SYMBOL in features
    with_triplets = MeterFeature.IMPLICIT_TUPLETS in features
    new_columns = [list(column) for column in columns]
    for segment in segments(columns):
        span = columns[segment.start : segment.end]
        read = segment.read
        beats: int | None = read.beats
        if MeterFeature.NUMERATOR in features:
            capacity = choose_capacity(span, read.beat_type, with_triplets=with_triplets)
            if capacity is not None:
                beats = _numerator(capacity, read.beat_type)
        signature = _signature(read, beats or read.beats, with_symbol)
        changes.segments.append(
            {
                "part": part_index,
                "measures": [span[0][0].number, span[-1][0].number],
                "read": _label(read),
                "recognized": _label(signature),
                "changed": not signature.same_notation(read),
            }
        )
        cells = _cells(span)
        plans = (
            _triplet_plans(cells, signature.quarter_length, _core(cells)) if with_triplets else {}
        )
        for cell in cells:
            updated = replace(cell.measure, time_signature=signature)
            plan = plans.get((cell.staff, cell.position))
            if plan is not None:
                updated = _apply_triplets(updated, plan)
                changes.tuplets.append(
                    {
                        "part": part_index,
                        "staff": cell.staff,
                        "measure": cell.measure.number,
                        "voices": {str(v): str(f) for v, f in sorted(plan.items())},
                    }
                )
            new_columns[segment.start + cell.position][cell.staff] = updated
    staves = tuple(
        replace(staff, measures=tuple(column[staff_index] for column in new_columns))
        for staff_index, staff in enumerate(part.staves)
    )
    return replace(part, staves=staves)


def recognize_meter(
    score: ScoreIR, features: Iterable[MeterFeature]
) -> tuple[ScoreIR, MeterStageReport]:
    """Aplica los rasgos pedidos a la lectura de HOMR y dice qué cambió.

    Sin rasgos, devuelve la misma partitura. Una parte cuyos pentagramas no tienen los mismos
    compases con la misma indicación (no ocurre con HOMR) no se toca y se dice."""

    active = frozenset(features)
    label = tuple(features_label(active))
    if not active:
        return score, MeterStageReport(features=label)
    changes = _Changes()
    parts = tuple(
        _recognize_part(part, index, active, changes) for index, part in enumerate(score.parts)
    )
    report = MeterStageReport(
        features=label,
        segments=tuple(changes.segments),
        tuplets=tuple(changes.tuplets),
        skipped_parts=tuple(changes.skipped),
    )
    return (replace(score, parts=parts) if report.changed else score), report


class MeterStage:
    """La etapa como paso del caso de uso de transcribir, tras el motor OMR (ADR-0059 §4)."""

    def __init__(self, features: Iterable[MeterFeature]) -> None:
        self._features = frozenset(features)

    @property
    def features(self) -> frozenset[MeterFeature]:
        return self._features

    def apply(self, document: ScoreDocument) -> ScoreDocument:
        """El documento con el compás reconocido y la etapa en su procedencia.

        Las anclas se derivan de nuevo: la etapa no añade ni quita eventos, solo cambia
        figuras e indicaciones, así que cada ancla sigue señalando el mismo evento."""

        score, report = recognize_meter(document.score, self._features)
        stages = dict(document.provenance.omr_stages or {})
        stages[METER_STAGE_ID] = report.to_primitive()
        return replace(
            document,
            score=score,
            anchors=build_anchor_index(score) if score is not document.score else document.anchors,
            provenance=replace(document.provenance, omr_stages=stages),
        )


__all__ = [
    "ALL_METER_FEATURES",
    "METER_STAGE_ID",
    "METER_STAGE_VERSION",
    "MeterFeature",
    "MeterStage",
    "MeterStageReport",
    "Segment",
    "choose_capacity",
    "features_label",
    "marked_figures",
    "measure_sum",
    "parse_meter_features",
    "recognize_meter",
    "segments",
]
