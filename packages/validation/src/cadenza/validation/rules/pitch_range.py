"""`pitch.range`: altura fuera de registro (ADR-0040 §9).

Una nota fuera del registro de su clave vigente suele ser una octava o una clave mal leídas.
Una clave sin tabla usa el registro del piano, de La0 a Do8. Las notas de adorno no cuentan.
El candidato es la misma nota, desplazada por octavas hasta la más cercana dentro del registro.
"""

from __future__ import annotations

import re

from cadenza.domain import (
    Clef,
    EditOp,
    EventKind,
    Finding,
    ScoreDocument,
    Severity,
    SuggestedEdit,
)

from ..language import clef_name, de, midi_of, note_name, position_phrase
from ..pitch import midi_to_pitch
from .base import ValidationRule
from .support import active_clefs, active_keys, anchor_map, is_grace, onsets, voices_of

RULE_ID = "pitch.range"

# Rangos MIDI (mín., máx.) de las claves usuales, sin octavar.
_CLEF_MIDI_RANGES: dict[tuple[str, int], tuple[int, int]] = {
    ("G", 2): (43, 96),  # clave de sol: Sol2 a Do7
    ("F", 4): (24, 72),  # clave de fa: Do1 a Do5
    ("C", 3): (36, 84),  # clave de do en tercera: Do2 a Do6
    ("C", 4): (31, 79),  # clave de do en cuarta: Sol1 a Sol5
}

# El registro del piano (La0 a Do8), para una clave sin tabla.
_DEFAULT_RANGE = (21, 108)
_OCTAVE_RE = re.compile(r"-?\d+$")


def _shift_octaves(pitch: str, octaves: int) -> str | None:
    match = _OCTAVE_RE.search(pitch)
    if match is None:
        return None
    return f"{pitch[: match.start()]}{int(match.group()) + octaves}"


class PitchRangeRule(ValidationRule):
    """Las notas caen dentro del registro razonable de su clave."""

    def __init__(
        self,
        *,
        custom_ranges: dict[tuple[str, int], tuple[int, int]] | None = None,
    ) -> None:
        self._ranges = dict(_CLEF_MIDI_RANGES)
        if custom_ranges:
            self._ranges.update(custom_ranges)

    @property
    def rule_id(self) -> str:
        return RULE_ID

    def _range(self, clef: Clef) -> tuple[int, int]:
        low, high = self._ranges.get((clef.sign.upper(), clef.line), _DEFAULT_RANGE)
        shift = clef.octave_change * 12
        return low + shift, high + shift

    def evaluate(self, document: ScoreDocument) -> list[Finding]:
        anchors = anchor_map(document.anchors)
        findings: list[Finding] = []
        for part_index, part in enumerate(document.score.parts):
            for staff_index, staff in enumerate(part.staves):
                # Sin clave leída: sol en el primer pentagrama y fa en los demás.
                default = Clef.treble() if staff_index == 0 else Clef.bass()
                clefs = active_clefs(staff, default)
                keys = active_keys(staff)
                for position, measure in enumerate(staff.measures):
                    low, high = self._range(clefs[position])
                    for voice, events in voices_of(measure).items():
                        starts = onsets(events)
                        for index, event in enumerate(events):
                            if event.kind is not EventKind.NOTE or is_grace(event):
                                continue
                            midi = midi_of(event.pitch)
                            if midi is None or low <= midi <= high or event.pitch is None:
                                continue
                            anchor = anchors.get(
                                (part_index, staff_index, measure.number, voice, index)
                            )
                            if anchor is None:
                                continue
                            octaves = (
                                (low - midi + 11) // 12
                                if midi < low
                                else -((midi - high + 11) // 12)
                            )
                            target = _shift_octaves(event.pitch, octaves)
                            target_midi = midi_of(target)
                            fits = target_midi is not None and low <= target_midi <= high
                            where = position_phrase(starts[index], measure.time_signature)
                            name = note_name(event.pitch, fifths=keys[position], octave=True)
                            side = "debajo" if midi < low else "encima"
                            bounds = (
                                f"de {note_name(midi_to_pitch(low), octave=True)} a "
                                f"{note_name(midi_to_pitch(high), octave=True)}"
                            )
                            fix = "Revisa la octava de la nota o la clave del pentagrama"
                            if fits and target is not None:
                                fix += (
                                    ": puede que sea "
                                    f"{note_name(target, fifths=keys[position], octave=True)}."
                                )
                            else:
                                fix += "."
                            findings.append(
                                Finding(
                                    anchor=anchor,
                                    rule_id=RULE_ID,
                                    severity=Severity.WARNING,
                                    message=(
                                        f"El {name} {de(where)} está muy por {side} de lo que se "
                                        f"escribe en {clef_name(clefs[position])} ({bounds})."
                                    ),
                                    suggested_fix=fix,
                                    candidates=(
                                        (
                                            SuggestedEdit(
                                                op=EditOp.SET_PITCH,
                                                anchor=anchor,
                                                after={"pitch": target},
                                            ),
                                        )
                                        if fits and target is not None
                                        else ()
                                    ),
                                )
                            )
        return findings
