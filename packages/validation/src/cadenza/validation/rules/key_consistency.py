"""Regla de consistencia de armadura y alteraciones (M2).

Comprueba que:
1. En sistemas con múltiples pentagramas (p. ej. piano), las armaduras de clave sean
   consistentes entre pentagramas dentro del mismo compás.
2. Las alteraciones accidentales de las notas sean coherentes con la tonalidad establecida
   por la armadura activa (p. ej., evitar bemoles contradictorios en armaduras con sostenidos
   o sostenidos en armaduras con bemoles, que suelen ser errores de reconocimiento enarmónico).
3. No existan alteraciones contradictorias simultáneas (p. ej., sostenido y bemol sobre la misma
   letra de nota) en el mismo compás y voz.
"""

from __future__ import annotations

from cadenza.domain import EventKind, Finding, KeySignature, ScoreDocument, Severity

from ..pitch import parse_pitch
from .base import ValidationRule
from .utils import build_event_anchor_map, find_measure_first_anchor

RULE_ID = "key.consistency"


def _key_name(fifths: int) -> str:
    if fifths == 0:
        return "sin alteraciones (Do mayor / La menor)"
    if fifths > 0:
        return f"{fifths} sostenido{'s' if fifths > 1 else ''}"
    abs_f = abs(fifths)
    return f"{abs_f} bemol{'es' if abs_f > 1 else ''}"


class KeyConsistencyRule(ValidationRule):
    """Verifica la consistencia de armaduras entre pentagramas y coherencia de alteraciones."""

    @property
    def rule_id(self) -> str:
        return RULE_ID

    def evaluate(self, document: ScoreDocument) -> list[Finding]:
        anchor_map = build_event_anchor_map(document.anchors)
        findings: list[Finding] = []

        for part_idx, part in enumerate(document.score.parts):
            # 1. Rastrear armadura activa por pentagrama
            staff_keys: dict[int, KeySignature] = {}

            # Agrupar compases por número de compás a través de los pentagramas
            measures_by_number: dict[int, dict[int, int]] = {}
            for staff_idx, staff in enumerate(part.staves):
                for m_idx, measure in enumerate(staff.measures):
                    measures_by_number.setdefault(measure.number, {})[staff_idx] = m_idx

            for measure_num in sorted(measures_by_number.keys()):
                staff_entries = measures_by_number[measure_num]

                # Actualizar armaduras activas si este compás define key_signature
                for staff_idx, m_idx in staff_entries.items():
                    m = part.staves[staff_idx].measures[m_idx]
                    if m.key_signature is not None:
                        staff_keys[staff_idx] = m.key_signature
                    elif staff_idx not in staff_keys:
                        # Por defecto sin alteraciones
                        staff_keys[staff_idx] = KeySignature(fifths=0)

                # Comprobar consistencia entre pentagramas si hay más de 1 pentagrama
                if len(part.staves) > 1 and 0 in staff_keys:
                    primary_key = staff_keys[0]
                    for staff_idx in sorted(staff_entries.keys()):
                        if staff_idx == 0:
                            continue
                        secondary_key = staff_keys[staff_idx]
                        if secondary_key.fifths != primary_key.fifths:
                            anchor = find_measure_first_anchor(
                                document.anchors, part_idx, staff_idx, measure_num
                            )
                            if anchor is not None:
                                findings.append(
                                    Finding(
                                        anchor=anchor,
                                        rule_id=RULE_ID,
                                        severity=Severity.WARNING,
                                        message=(
                                            f"Discrepancia de armadura en compás {measure_num}: "
                                            f"pentagrama {staff_idx} "
                                            f"({_key_name(secondary_key.fifths)}) no coincide "
                                            "con el pentagrama principal "
                                            f"({_key_name(primary_key.fifths)})."
                                        ),
                                        suggested_fix=(
                                            f"Alinear la armadura del pentagrama {staff_idx} en "
                                            f"compás {measure_num} con la del pentagrama principal "
                                            f"({_key_name(primary_key.fifths)})."
                                        ),
                                    )
                                )

                # 2. Comprobar alteraciones de notas en cada pentagrama y voz
                for staff_idx, m_idx in staff_entries.items():
                    current_key = staff_keys[staff_idx]
                    measure = part.staves[staff_idx].measures[m_idx]

                    voice_counters: dict[int, int] = {}
                    seen_alters: dict[tuple[int, str], list[tuple[int, int]]] = {}

                    for event in measure.events:
                        voice_idx = voice_counters.get(event.voice, 0)
                        voice_counters[event.voice] = voice_idx + 1

                        if event.kind != EventKind.NOTE or event.pitch is None:
                            continue

                        parsed = parse_pitch(event.pitch)
                        if parsed is None:
                            continue

                        step, alter, _octave = parsed
                        anchor = anchor_map.get(
                            (part_idx, staff_idx, measure.number, event.voice, voice_idx)
                        )
                        if anchor is None:
                            anchor = find_measure_first_anchor(
                                document.anchors, part_idx, staff_idx, measure.number
                            )
                        if anchor is None:
                            continue

                        # A. Coherencia con la armadura:
                        if current_key.fifths > 0 and alter < 0:
                            findings.append(
                                Finding(
                                    anchor=anchor,
                                    rule_id=RULE_ID,
                                    severity=Severity.WARNING,
                                    message=(
                                        f"La nota {event.pitch} contiene un bemol inconsistente "
                                        f"con la armadura de {_key_name(current_key.fifths)}."
                                    ),
                                    suggested_fix=(
                                        f"Revisar la alteración de {event.pitch} o sustituirla "
                                        "por su enarmónico con sostenido."
                                    ),
                                )
                            )
                        elif current_key.fifths < 0 and alter > 0:
                            findings.append(
                                Finding(
                                    anchor=anchor,
                                    rule_id=RULE_ID,
                                    severity=Severity.WARNING,
                                    message=(
                                        f"La nota {event.pitch} contiene un sostenido "
                                        "inconsistente con la armadura de "
                                        f"{_key_name(current_key.fifths)}."
                                    ),
                                    suggested_fix=(
                                        f"Revisar la alteración de {event.pitch} o sustituirla "
                                        "por su enarmónico con bemol."
                                    ),
                                )
                            )

                        # B. Coherencia interna dentro del mismo compás y voz:
                        key_step = (event.voice, step)
                        prev_alters = seen_alters.get(key_step, [])
                        for prev_alt, _prev_voice_idx in prev_alters:
                            if (prev_alt > 0 and alter < 0) or (prev_alt < 0 and alter > 0):
                                findings.append(
                                    Finding(
                                        anchor=anchor,
                                        rule_id=RULE_ID,
                                        severity=Severity.WARNING,
                                        message=(
                                            f"Alteraciones opuestas contradictorias sobre la nota "
                                            f"{step} en la voz {event.voice} del compás "
                                            f"{measure.number}."
                                        ),
                                        suggested_fix=(
                                            f"Unificar la notación enarmónica de las alteraciones "
                                            f"de {step} en el compás {measure.number}."
                                        ),
                                    )
                                )
                                break
                        seen_alters.setdefault(key_step, []).append((alter, voice_idx))

        return findings
