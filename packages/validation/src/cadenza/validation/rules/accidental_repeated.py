"""`accidental.repeated`: alteración repetida (ADR-0040 §7).

El error de alteración más frecuente de HOMR: cuando una nota repite en el mismo compás la
letra y la octava de otra con alteración, HOMR no ve su becuadro y le pone la alteración de la
anterior. Dispara en una nota que se ve, con sostenido o bemol (también doble) contra la
armadura vigente, cuando la última nota anterior de su voz y compás con su misma letra y
octava lleva esa misma alteración. Cuentan como anteriores las notas de adorno y las de un
acorde, en el orden de la voz, como en el contexto del corpus (`previous_accidental_same_step`).

No dispara (#318, enmienda 11 de ADR-0040) cuando la nota y la anterior de su altura son de
un acorde, ni cuando otra voz u otro pentagrama del mismo compás lleva la misma letra con la
misma alteración, en cualquier octava, sonando cuando empieza la nota o después: en una página
de la práctica común la alteración se escribe una vez y vale hasta la barra.

El candidato es la alteración de la armadura; la capa lo ordena y solo lo muestra si lo
puntúa alto (ADR-0036, enmiendas 6 y 19).
"""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction

from cadenza.domain import (
    EditOp,
    Event,
    EventKind,
    Finding,
    ScoreDocument,
    Severity,
    SuggestedEdit,
)

from ..language import (
    accidental_word,
    de,
    key_accidental,
    letter_name,
    note_name,
    position_phrase,
    split_pitch,
)
from .base import ValidationRule
from .support import active_keys, anchor_map, onsets, voices_of

RULE_ID = "accidental.repeated"
_ALTERED = frozenset({"#", "##", "b", "bb"})

_Owner = tuple[int, int, int]
"""(parte, pentagrama, voz)."""

_Sounding = tuple[_Owner, Fraction, Fraction]
"""(dueño, inicio, final) de una nota en su compás, en negras."""


def _altered_in_measures(
    document: ScoreDocument,
) -> dict[tuple[int, str, str], list[_Sounding]]:
    """Las notas con sostenido o bemol (también doble) de cada compás, por su letra y alteración."""
    found: dict[tuple[int, str, str], list[_Sounding]] = {}
    for part_index, part in enumerate(document.score.parts):
        for staff_index, staff in enumerate(part.staves):
            for measure in staff.measures:
                for voice, events in voices_of(measure).items():
                    for event, start in zip(events, onsets(events), strict=True):
                        letter, accidental, _ = split_pitch(event.pitch)
                        if event.kind is not EventKind.NOTE or accidental not in _ALTERED:
                            continue
                        end = start + max(event.duration_beats or Fraction(0), Fraction(0))
                        owner = (part_index, staff_index, voice)
                        key = (measure.number, letter, accidental)
                        found.setdefault(key, []).append((owner, start, end))
    return found


def _confirmed(sounding: Sequence[_Sounding], owner: _Owner, start: Fraction) -> bool:
    """Otra voz u otro pentagrama lleva la alteración sonando cuando empieza la nota o después."""
    return any(other != owner and (end > start or begin >= start) for other, begin, end in sounding)


def _in_chord(events: Sequence[Event], index: int) -> bool:
    """La nota es de un acorde: lleva `is_chord` o la siguiente de su voz lo lleva."""
    following = events[index + 1] if index + 1 < len(events) else None
    return events[index].is_chord or (following is not None and following.is_chord)


class AccidentalRepeatedRule(ValidationRule):
    """Una alteración contra la armadura que repite la de la nota anterior de su altura."""

    @property
    def rule_id(self) -> str:
        return RULE_ID

    def evaluate(self, document: ScoreDocument) -> list[Finding]:
        anchors = anchor_map(document.anchors)
        altered = _altered_in_measures(document)
        findings: list[Finding] = []
        for part_index, part in enumerate(document.score.parts):
            for staff_index, staff in enumerate(part.staves):
                keys = active_keys(staff)
                for position, measure in enumerate(staff.measures):
                    fifths = keys[position]
                    signature = measure.time_signature
                    for voice, events in voices_of(measure).items():
                        starts = onsets(events)
                        last: dict[tuple[str, int | None], int] = {}
                        for index, event in enumerate(events):
                            if event.kind is not EventKind.NOTE:
                                continue
                            letter, accidental, octave = split_pitch(event.pitch)
                            if not letter:
                                continue
                            previous = last.get((letter, octave))
                            last[(letter, octave)] = index
                            expected = key_accidental(letter, fifths)
                            if (
                                previous is None
                                or event.hidden
                                or accidental not in _ALTERED
                                or accidental == expected
                                or split_pitch(events[previous].pitch)[1] != accidental
                                or (_in_chord(events, index) and _in_chord(events, previous))
                                or _confirmed(
                                    altered.get((measure.number, letter, accidental), ()),
                                    (part_index, staff_index, voice),
                                    starts[index],
                                )
                            ):
                                continue
                            anchor = anchors.get(
                                (part_index, staff_index, measure.number, voice, index)
                            )
                            if anchor is None:
                                continue
                            name = note_name(event.pitch, fifths=fifths)
                            letter_only = letter_name(event.pitch)
                            here = position_phrase(starts[index], signature)
                            there = position_phrase(starts[previous], signature)
                            target = f"{letter}{expected}{octave}"
                            findings.append(
                                Finding(
                                    anchor=anchor,
                                    rule_id=RULE_ID,
                                    severity=Severity.WARNING,
                                    message=(
                                        f"El {name} {de(here)} repite el "
                                        f"{accidental_word(accidental)} del {letter_only} "
                                        f"{de(there)}, y la armadura no lo lleva."
                                    ),
                                    suggested_fix=(
                                        f"Mira si en la partitura este {letter_only} lleva "
                                        f"{accidental_word(expected)}: entonces es "
                                        f"{note_name(target, fifths=fifths)}, no {name}."
                                    ),
                                    candidates=(
                                        SuggestedEdit(
                                            op=EditOp.SET_ACCIDENTAL,
                                            anchor=anchor,
                                            after={"accidental": expected},
                                        ),
                                    ),
                                )
                            )
        return findings
