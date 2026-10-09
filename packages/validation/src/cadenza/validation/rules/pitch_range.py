"""Regla de rango tonal por clave (M2).

Comprueba que las alturas de las notas se encuentren dentro de un rango razonable
para la clave activa del pentagrama. Las notas excesivamente agudas o graves respecto
a la clave suelen corresponder a errores de lectura del OMR (octavas desplazadas o
símbolos mal reconocidos).
"""

from __future__ import annotations

from cadenza.domain import Clef, EventKind, Finding, ScoreDocument, Severity

from ..pitch import midi_to_pitch, pitch_to_midi
from .base import ValidationRule
from .utils import build_event_anchor_map, clef_display_name, find_measure_first_anchor

RULE_ID = "pitch.range"

# Rangos MIDI base (min, max) para claves estándar sin cambio de octava
_CLEF_MIDI_RANGES: dict[tuple[str, int], tuple[int, int]] = {
    ("G", 2): (43, 96),  # Sol en 2ª: G2 a C7
    ("F", 4): (24, 72),  # Fa en 4ª: C1 a C5
    ("C", 3): (36, 84),  # Do en 3ª (alto): C2 a C6
    ("C", 4): (31, 79),  # Do en 4ª (tenor): G1 a G5
}

# Rango general amplio de fallback (piano de 88 teclas: A0 a C8)
_DEFAULT_RANGE = (21, 108)


def _get_clef_range(clef: Clef) -> tuple[int, int]:
    base = _CLEF_MIDI_RANGES.get((clef.sign.upper(), clef.line), _DEFAULT_RANGE)
    shift = clef.octave_change * 12
    return (base[0] + shift, base[1] + shift)


class PitchRangeRule(ValidationRule):
    """Verifica que las alturas de notas estén dentro del rango razonable para la clave."""

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

    def evaluate(self, document: ScoreDocument) -> list[Finding]:
        anchor_map = build_event_anchor_map(document.anchors)
        findings: list[Finding] = []

        for part_idx, part in enumerate(document.score.parts):
            for staff_idx, staff in enumerate(part.staves):
                # Clave activa del pentagrama: por defecto Sol en pentagrama 0, Fa en pentagrama 1
                active_clef: Clef = Clef.treble() if staff_idx == 0 else Clef.bass()

                for measure in staff.measures:
                    if measure.clef is not None:
                        active_clef = measure.clef

                    min_midi, max_midi = _get_clef_range(active_clef)
                    min_pitch_str = midi_to_pitch(min_midi)
                    max_pitch_str = midi_to_pitch(max_midi)
                    clef_desc = clef_display_name(active_clef)

                    # Rastrear índice dentro de cada voz para encontrar el ancla
                    voice_counters: dict[int, int] = {}

                    for event in measure.events:
                        voice_idx = voice_counters.get(event.voice, 0)
                        voice_counters[event.voice] = voice_idx + 1

                        if event.kind != EventKind.NOTE or event.pitch is None:
                            continue

                        midi = pitch_to_midi(event.pitch)
                        if midi is None:
                            continue

                        if midi < min_midi or midi > max_midi:
                            anchor = anchor_map.get(
                                (part_idx, staff_idx, measure.number, event.voice, voice_idx)
                            )
                            if anchor is None:
                                anchor = find_measure_first_anchor(
                                    document.anchors, part_idx, staff_idx, measure.number
                                )
                            if anchor is None:
                                continue

                            findings.append(
                                Finding(
                                    anchor=anchor,
                                    rule_id=RULE_ID,
                                    severity=Severity.WARNING,
                                    message=(
                                        f"La nota {event.pitch} está fuera del rango razonable "
                                        f"({min_pitch_str}-{max_pitch_str}) "
                                        f"para la clave {clef_desc}."
                                    ),
                                    suggested_fix=(
                                        "Verificar la altura o la octava de la nota "
                                        f"(actual: {event.pitch})."
                                    ),
                                )
                            )

        return findings
