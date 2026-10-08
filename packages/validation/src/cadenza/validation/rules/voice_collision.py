"""Regla de colisión de voces (M2).

Comprueba que no existan solapamientos temporales anómalos o incongruencias
polifónicas dentro de una misma voz de un compás:
1. En acordes (`is_chord=True`), todas las notas deben compartir la misma duración
   con la nota base. Duraciones distintas dentro del mismo acorde provocan desincronización
   o solapamiento temporal no válido dentro de la misma voz (deben pertenecer a voces separadas).
2. Un evento marcado como acorde (`is_chord=True`) no puede ser el primer evento de la voz
   ni ocurrir después de un silencio.
3. No pueden coexistir notas con la misma altura (unísonos duplicados) dentro del mismo acorde.
4. Los silencios no pueden estar marcados como acordes.
5. Las duraciones de notas y silencios deben ser estrictamente positivas.
"""

from __future__ import annotations

from fractions import Fraction

from cadenza.domain import Event, EventKind, Finding, ScoreDocument, Severity

from .base import ValidationRule
from .utils import build_event_anchor_map, find_measure_first_anchor

RULE_ID = "voice.collision"


class VoiceCollisionRule(ValidationRule):
    """Verifica que no existan solapamientos temporales ni incongruencias dentro de una voz."""

    @property
    def rule_id(self) -> str:
        return RULE_ID

    def evaluate(self, document: ScoreDocument) -> list[Finding]:
        anchor_map = build_event_anchor_map(document.anchors)
        findings: list[Finding] = []

        for part_idx, part in enumerate(document.score.parts):
            for staff_idx, staff in enumerate(part.staves):
                for measure in staff.measures:
                    # Agrupar eventos por voz
                    voice_events: dict[int, list[tuple[int, Event]]] = {}
                    voice_counters: dict[int, int] = {}

                    for event in measure.events:
                        voice_idx = voice_counters.get(event.voice, 0)
                        voice_counters[event.voice] = voice_idx + 1
                        voice_events.setdefault(event.voice, []).append((voice_idx, event))

                    for voice, events_with_idx in voice_events.items():
                        current_chord_base: tuple[int, Event] | None = None
                        seen_chord_pitches: set[str] = set()

                        for voice_idx, event in events_with_idx:
                            anchor = anchor_map.get(
                                (part_idx, staff_idx, measure.number, voice, voice_idx)
                            )
                            if anchor is None:
                                anchor = find_measure_first_anchor(
                                    document.anchors, part_idx, staff_idx, measure.number
                                )
                            if anchor is None:
                                continue

                            # 1. Duración estrictamente positiva
                            if (
                                event.duration_beats is not None
                                and event.duration_beats <= Fraction(0)
                            ):
                                findings.append(
                                    Finding(
                                        anchor=anchor,
                                        rule_id=RULE_ID,
                                        severity=Severity.ERROR,
                                        message=(
                                            f"Duración no positiva ({event.duration_beats}) "
                                            f"en la voz {voice} del compás {measure.number}."
                                        ),
                                        suggested_fix=(
                                            "Asignar una duración estrictamente mayor que cero."
                                        ),
                                    )
                                )

                            # 2. Silencios no pueden ser parte de un acorde
                            if event.kind == EventKind.REST and event.is_chord:
                                findings.append(
                                    Finding(
                                        anchor=anchor,
                                        rule_id=RULE_ID,
                                        severity=Severity.ERROR,
                                        message=(
                                            f"Un silencio no puede formar parte de un acorde "
                                            f"(voz {voice}, compás {measure.number})."
                                        ),
                                        suggested_fix=(
                                            "Desmarcar el silencio como acorde o "
                                            "moverlo a otra voz."
                                        ),
                                    )
                                )
                                current_chord_base = None
                                seen_chord_pitches.clear()
                                continue

                            # 3. Comprobaciones de acorde vs nota base
                            if event.is_chord:
                                if current_chord_base is None:
                                    findings.append(
                                        Finding(
                                            anchor=anchor,
                                            rule_id=RULE_ID,
                                            severity=Severity.ERROR,
                                            message=(
                                                "Nota marcada como acorde sin una nota base previa "
                                                f"en la voz {voice} (compás {measure.number})."
                                            ),
                                            suggested_fix=(
                                                "Desmarcar el evento como acorde o "
                                                "anteponer una nota base."
                                            ),
                                        )
                                    )
                                else:
                                    _base_idx, base_event = current_chord_base

                                    # Coincidencia de duración dentro del mismo acorde
                                    if (
                                        event.duration_beats is not None
                                        and base_event.duration_beats is not None
                                        and event.duration_beats != base_event.duration_beats
                                    ):
                                        findings.append(
                                            Finding(
                                                anchor=anchor,
                                                rule_id=RULE_ID,
                                                severity=Severity.ERROR,
                                                message=(
                                                    "Desincronización temporal en acorde de la "
                                                    f"voz {voice}: la nota dura "
                                                    f"{event.duration_beats} y la nota base dura "
                                                    f"{base_event.duration_beats}."
                                                ),
                                                suggested_fix=(
                                                    f"Igualar la duración a "
                                                    f"{base_event.duration_beats} o separar "
                                                    "la nota en una voz distinta."
                                                ),
                                            )
                                        )

                                    # Unísono duplicado dentro del mismo acorde
                                    if event.pitch and event.pitch in seen_chord_pitches:
                                        findings.append(
                                            Finding(
                                                anchor=anchor,
                                                rule_id=RULE_ID,
                                                severity=Severity.ERROR,
                                                message=(
                                                    f"Altura duplicada {event.pitch} dentro del "
                                                    f"mismo acorde en la voz {voice} "
                                                    f"(compás {measure.number})."
                                                ),
                                                suggested_fix=(
                                                    f"Eliminar la nota duplicada {event.pitch} "
                                                    "del acorde."
                                                ),
                                            )
                                        )
                                    elif event.pitch:
                                        seen_chord_pitches.add(event.pitch)

                            else:
                                # Nueva nota base o silencio independiente
                                if event.kind == EventKind.NOTE:
                                    current_chord_base = (voice_idx, event)
                                    seen_chord_pitches = {event.pitch} if event.pitch else set()
                                else:
                                    current_chord_base = None
                                    seen_chord_pitches.clear()

        return findings
