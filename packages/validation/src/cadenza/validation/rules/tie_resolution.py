"""Regla de resolución y cierre de ligaduras de prolongación (M2).

Comprueba que todas las ligaduras de prolongación (`Tie.START`, `Tie.CONTINUE`, `Tie.STOP`):
1. Estén correctamente abiertas y cerradas: todo `Tie.START` debe resolverse con un `Tie.STOP`
   (o cadena de `Tie.CONTINUE` -> `Tie.STOP`) en la misma altura y voz.
2. Todo `Tie.STOP` o `Tie.CONTINUE` debe tener un `Tie.START` previo correspondiente
   en la misma voz.
3. No existan ligaduras colgadas o sin cerrar al final de la obra o pentagrama.
4. Los silencios no tengan marcas de ligadura de prolongación.
"""

from __future__ import annotations

from cadenza.domain import Anchor, EventKind, Finding, ScoreDocument, Severity, Tie

from .base import ValidationRule
from .utils import build_event_anchor_map, find_measure_first_anchor

RULE_ID = "tie.resolution"


class TieResolutionRule(ValidationRule):
    """Verifica que las ligaduras de prolongación estén correctamente abiertas y cerradas."""

    @property
    def rule_id(self) -> str:
        return RULE_ID

    def evaluate(self, document: ScoreDocument) -> list[Finding]:
        anchor_map = build_event_anchor_map(document.anchors)
        findings: list[Finding] = []

        for part_idx, part in enumerate(document.score.parts):
            for staff_idx, staff in enumerate(part.staves):
                # Rastrear ligaduras activas por (voice, pitch) -> (Anchor, measure_number)
                active_ties: dict[tuple[int, str], tuple[Anchor, int]] = {}

                for measure in staff.measures:
                    voice_counters: dict[int, int] = {}

                    for event in measure.events:
                        voice_idx = voice_counters.get(event.voice, 0)
                        voice_counters[event.voice] = voice_idx + 1

                        anchor = anchor_map.get(
                            (part_idx, staff_idx, measure.number, event.voice, voice_idx)
                        )
                        if anchor is None:
                            anchor = find_measure_first_anchor(
                                document.anchors, part_idx, staff_idx, measure.number
                            )
                        if anchor is None:
                            continue

                        # 1. Silencios no pueden tener ligadura
                        if event.kind == EventKind.REST and event.tie is not None:
                            findings.append(
                                Finding(
                                    anchor=anchor,
                                    rule_id=RULE_ID,
                                    severity=Severity.WARNING,
                                    message=(
                                        f"Un silencio no puede tener ligadura de prolongación "
                                        f"(voz {event.voice}, compás {measure.number})."
                                    ),
                                    suggested_fix="Eliminar la ligadura del silencio.",
                                )
                            )
                            continue

                        if event.kind != EventKind.NOTE or event.pitch is None:
                            continue

                        key = (event.voice, event.pitch)

                        if event.tie == Tie.START:
                            # Si ya había una ligadura abierta de la misma nota y voz sin cerrar
                            if key in active_ties:
                                prev_anchor, prev_m = active_ties[key]
                                findings.append(
                                    Finding(
                                        anchor=prev_anchor,
                                        rule_id=RULE_ID,
                                        severity=Severity.WARNING,
                                        message=(
                                            f"Ligadura iniciada en la nota {event.pitch} "
                                            f"(compás {prev_m}) no fue cerrada antes de iniciar "
                                            f"una nueva ligadura en el compás {measure.number}."
                                        ),
                                        suggested_fix=(
                                            f"Cerrar la ligadura previa de {event.pitch} con "
                                            "'stop' o retirar el inicio duplicado."
                                        ),
                                    )
                                )
                            active_ties[key] = (anchor, measure.number)

                        elif event.tie == Tie.CONTINUE:
                            if key not in active_ties:
                                findings.append(
                                    Finding(
                                        anchor=anchor,
                                        rule_id=RULE_ID,
                                        severity=Severity.WARNING,
                                        message=(
                                            f"La nota {event.pitch} tiene continuación de ligadura "
                                            "('continue') sin ligadura previa en voz "
                                            f"{event.voice}."
                                        ),
                                        suggested_fix=(
                                            "Añadir un inicio de ligadura ('start') en la nota "
                                            "anterior o cambiar el estado de ligadura."
                                        ),
                                    )
                                )
                            active_ties[key] = (anchor, measure.number)

                        elif event.tie == Tie.STOP:
                            if key in active_ties:
                                del active_ties[key]
                            else:
                                findings.append(
                                    Finding(
                                        anchor=anchor,
                                        rule_id=RULE_ID,
                                        severity=Severity.WARNING,
                                        message=(
                                            f"La nota {event.pitch} tiene cierre de ligadura "
                                            f"('stop') sin ligadura previa en voz {event.voice} "
                                            f"(compás {measure.number})."
                                        ),
                                        suggested_fix=(
                                            "Eliminar el cierre de ligadura o añadir un inicio "
                                            "('start') en la nota precedente."
                                        ),
                                    )
                                )

                        elif event.tie is None:
                            if key in active_ties:
                                prev_anchor, prev_m = active_ties.pop(key)
                                findings.append(
                                    Finding(
                                        anchor=prev_anchor,
                                        rule_id=RULE_ID,
                                        severity=Severity.WARNING,
                                        message=(
                                            f"Ligadura iniciada en la nota {event.pitch} "
                                            f"(compás {prev_m}, voz {event.voice}) quedó "
                                            "interrumpida antes de una nota sin ligadura en "
                                            f"el compás {measure.number}."
                                        ),
                                        suggested_fix=(
                                            f"Cerrar la ligadura en {event.pitch} o retirar "
                                            "el inicio previo."
                                        ),
                                    )
                                )

                # Al terminar el pentagrama, cualquier ligadura que quede activa quedó colgada
                for (voice, pitch), (start_anchor, start_m) in active_ties.items():
                    findings.append(
                        Finding(
                            anchor=start_anchor,
                            rule_id=RULE_ID,
                            severity=Severity.WARNING,
                            message=(
                                f"Ligadura abierta en {pitch} (compás {start_m}, voz {voice}) "
                                "nunca fue cerrada antes del final de la obra."
                            ),
                            suggested_fix=(
                                f"Añadir nota de cierre con 'stop' para {pitch} o retirar 'start'."
                            ),
                        )
                    )

        return findings
