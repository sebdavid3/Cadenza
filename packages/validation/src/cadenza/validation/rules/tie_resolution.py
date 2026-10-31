"""`tie.resolution`: ligadura sin cerrar (ADR-0040 §10).

Una ligadura de prolongación une una nota con la nota siguiente de su misma altura:

- dentro del compás, el evento de la misma voz que empieza donde acaba la nota ligada (una
  nota, un acorde, con la nota de su misma altura, o un silencio);
- al cruzar la barra, los eventos que empiezan con el compás siguiente, en el mismo pentagrama
  y en cualquier voz, prefiriendo la misma: las voces se numeran desde 0 en cada compás
  (ADR-0032 §3), así que la ligadura puede llegar a otra voz con otro número. Una nota más
  adelante en el compás no cuenta.

Si alguna de esas notas tiene su altura, la ligadura está resuelta, aunque no lleve la marca
de final. Se señala un solo posible error por ligadura, en la nota donde empieza: no llega, un
final sin principio o una ligadura en un silencio. No se señalan los bordes de la página (una
ligadura que llega al primer compás o sale del último). Las notas de adorno no cuentan, y no
hay operación para las ligaduras: sin candidatos.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from cadenza.domain import Event, EventKind, Finding, Measure, ScoreDocument, Severity, Tie

from ..language import de, figure_name, note_name, position_phrase, split_pitch
from .base import ValidationRule
from .support import active_keys, anchor_map, is_grace, onsets, voices_of

RULE_ID = "tie.resolution"
_STARTS = frozenset({Tie.START, Tie.CONTINUE})
_ENDS = frozenset({Tie.STOP, Tie.CONTINUE})
_EXPRESSION = (
    "Si en la partitura une notas distintas, es una ligadura de expresión y este aviso se puede "
    "descartar"
)

Place = tuple[int, int, int]
"""(posición del compás en el pentagrama, voz, índice del evento en la voz)."""


@dataclass(frozen=True, slots=True)
class _Slot:
    place: Place
    event: Event
    onset: Fraction


@dataclass(frozen=True, slots=True)
class _Problem:
    slot: _Slot
    message: str
    fix: str


def _same_pitch(a: Event, b: Event) -> bool:
    return b.kind is EventKind.NOTE and split_pitch(a.pitch) == split_pitch(b.pitch)


def _slots(measures: Sequence[Measure]) -> list[list[_Slot]]:
    """Los eventos de cada compás que cuentan: sin notas de adorno ni silencios invisibles."""
    result: list[list[_Slot]] = []
    for position, measure in enumerate(measures):
        found: list[_Slot] = []
        for voice, events in voices_of(measure).items():
            for index, (event, onset) in enumerate(zip(events, onsets(events), strict=True)):
                if not is_grace(event) and not event.hidden:
                    found.append(_Slot((position, voice, index), event, onset))
        result.append(found)
    return result


def _following(slots: Sequence[Sequence[_Slot]], slot: _Slot) -> tuple[list[_Slot], bool]:
    """Lo que sigue a una nota ligada: lo de su voz que empieza donde acaba o, si es lo último
    de su voz en el compás, lo que empieza con el compás siguiente (lo de su voz primero).
    Vacío si no hay nada, o si la ligadura sale del último compás del pentagrama."""
    position, voice, index = slot.place
    end = slot.onset + (slot.event.duration_beats or Fraction(0))
    same_voice = [other for other in slots[position] if other.place[1] == voice]
    inside = [other for other in same_voice if other.onset == end and other.place[2] > index]
    if inside:
        return inside, False
    if any(other.onset >= end and other.place[2] > index for other in same_voice):
        return [], False
    if position + 1 >= len(slots):
        return [], False
    first = [other for other in slots[position + 1] if other.onset == 0]
    first.sort(key=lambda other: (other.place[1] != voice, other.place[1], other.place[2]))
    return first, True


def _unreached(
    measures: Sequence[Measure],
    keys: Sequence[int],
    slot: _Slot,
    following: Sequence[_Slot],
    crossed: bool,
) -> _Problem:
    measure = measures[slot.place[0]]
    where = position_phrase(slot.onset, measure.time_signature)
    name = note_name(slot.event.pitch, fifths=keys[slot.place[0]])
    nxt = following[0].event
    if nxt.kind is EventKind.REST:
        what = "un silencio"
        fix = (
            "Revisa si en la partitura lo siguiente es una nota; si es un silencio, la ligadura "
            "sobra."
        )
    else:
        other = note_name(nxt.pitch, fifths=keys[following[0].place[0]])
        what = f"un {other}"
        fix = f"{_EXPRESSION}; si no, revisa la altura del {other}."
    if crossed:
        what += f", en el compás {measures[slot.place[0] + 1].number}"
    return _Problem(
        slot,
        f"La ligadura del {name} {de(where)} no llega a otro {name}: lo siguiente es {what}.",
        fix,
    )


class TieResolutionRule(ValidationRule):
    """Cada ligadura de prolongación une dos notas iguales seguidas."""

    @property
    def rule_id(self) -> str:
        return RULE_ID

    def evaluate(self, document: ScoreDocument) -> list[Finding]:
        anchors = anchor_map(document.anchors)
        findings: list[Finding] = []
        for part_index, part in enumerate(document.score.parts):
            for staff_index, staff in enumerate(part.staves):
                measures = staff.measures
                for problem in self._problems(measures, active_keys(staff)):
                    position, voice, index = problem.slot.place
                    anchor = anchors.get(
                        (part_index, staff_index, measures[position].number, voice, index)
                    )
                    if anchor is not None:
                        findings.append(
                            Finding(
                                anchor=anchor,
                                rule_id=RULE_ID,
                                severity=Severity.WARNING,
                                message=problem.message,
                                suggested_fix=problem.fix,
                            )
                        )
        return findings

    @staticmethod
    def _problems(measures: Sequence[Measure], keys: Sequence[int]) -> list[_Problem]:
        slots = _slots(measures)
        matched: set[Place] = set()
        problems: list[_Problem] = []
        for in_measure in slots:
            for slot in in_measure:
                event = slot.event
                if event.kind is EventKind.REST:
                    # El final de una ligadura que ya se señaló en su nota no va aparte.
                    closes = event.tie is Tie.STOP and slot.place in matched
                    if event.tie is not None and not closes:
                        measure = measures[slot.place[0]]
                        where = position_phrase(slot.onset, measure.time_signature)
                        problems.append(
                            _Problem(
                                slot,
                                f"El silencio de {figure_name(event.duration_beats)} {de(where)} "
                                "tiene una ligadura, y los silencios no se ligan.",
                                "Revisa si en la partitura ese silencio es una nota.",
                            )
                        )
                    continue
                if event.kind is not EventKind.NOTE or event.tie not in _STARTS:
                    continue
                following, crossed = _following(slots, slot)
                if not following:
                    continue
                hits = [other for other in following if _same_pitch(event, other.event)]
                if hits:
                    matched.update(other.place for other in hits)
                    continue
                # Un solo aviso por ligadura: la marca de final de lo siguiente no va aparte.
                matched.update(other.place for other in following)
                problems.append(_unreached(measures, keys, slot, following, crossed))

        for in_measure in slots[1:]:  # el primer compás: la ligadura viene de la página anterior
            for slot in in_measure:
                event = slot.event
                if (
                    event.kind is not EventKind.NOTE
                    or event.tie not in _ENDS
                    or slot.place in matched
                ):
                    continue
                measure = measures[slot.place[0]]
                where = position_phrase(slot.onset, measure.time_signature)
                name = note_name(event.pitch, fifths=keys[slot.place[0]])
                problems.append(
                    _Problem(
                        slot,
                        f"El {name} {de(where)} termina una ligadura que no empieza en ninguna "
                        "nota anterior.",
                        f"Revisa si la nota anterior es también un {name} ligado; si no, la "
                        "ligadura sobra.",
                    )
                )
        return problems
