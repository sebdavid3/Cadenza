"""`voice.collision`: acorde mal formado (ADR-0040 §11).

Detecta acordes que no se pueden escribir y un silencio sin duración:

- notas del acorde con figuras distintas;
- un silencio dentro de un acorde;
- una nota de acorde sin una nota antes con la que sonar;
- la misma altura dos veces en un acorde;
- un silencio sin duración.

Una nota de duración 0 o nula no es un error: es una nota de adorno (ADR-0028).
"""

from __future__ import annotations

from cadenza.domain import Event, EventKind, Finding, ScoreDocument, Severity

from ..language import count_figures, de, note_name, position_phrase, split_pitch
from .base import ValidationRule
from .support import active_keys, anchor_map, is_grace, onsets, voices_of

RULE_ID = "voice.collision"


class VoiceCollisionRule(ValidationRule):
    """Los acordes de cada voz se pueden escribir, y ningún silencio dura nada."""

    @property
    def rule_id(self) -> str:
        return RULE_ID

    def evaluate(self, document: ScoreDocument) -> list[Finding]:
        anchors = anchor_map(document.anchors)
        findings: list[Finding] = []

        def add(key: tuple[int, int, int, int, int], message: str, fix: str) -> None:
            anchor = anchors.get(key)
            if anchor is not None:
                findings.append(
                    Finding(
                        anchor=anchor,
                        rule_id=RULE_ID,
                        severity=Severity.ERROR,
                        message=message,
                        suggested_fix=fix,
                    )
                )

        for part_index, part in enumerate(document.score.parts):
            for staff_index, staff in enumerate(part.staves):
                for measure, fifths in zip(staff.measures, active_keys(staff), strict=True):
                    for voice, events in voices_of(measure).items():
                        starts = onsets(events)
                        base: Event | None = None
                        seen: set[tuple[str, str, int | None]] = set()
                        for index, event in enumerate(events):
                            key = (part_index, staff_index, measure.number, voice, index)
                            where = de(position_phrase(starts[index], measure.time_signature))
                            if event.kind is EventKind.REST:
                                duration = event.duration_beats
                                if event.is_chord:
                                    add(
                                        key,
                                        f"El silencio {where} está dentro de un acorde.",
                                        "Revisa si es una nota del acorde o un silencio de otra "
                                        "voz.",
                                    )
                                elif duration is None or duration <= 0:
                                    add(
                                        key,
                                        f"El silencio {where} no dura nada.",
                                        "Revisa su figura en la partitura.",
                                    )
                                if not event.is_chord:
                                    base = None
                                    seen = set()
                                continue
                            if event.kind is not EventKind.NOTE:
                                continue
                            pitch = split_pitch(event.pitch)
                            if not event.is_chord:
                                base = event
                                seen = {pitch}
                                continue
                            name = note_name(event.pitch, fifths=fifths)
                            if base is None:
                                add(
                                    key,
                                    f"El {name} {where} está marcado como nota de un acorde, "
                                    "pero no tiene antes otra nota con la que sonar.",
                                    "Revisa si es una nota suelta.",
                                )
                                continue
                            # Una nota de adorno no tiene figura que comparar (ADR-0028).
                            if (
                                not is_grace(event)
                                and not is_grace(base)
                                and event.duration_beats != base.duration_beats
                            ):
                                first = note_name(base.pitch, fifths=fifths)
                                mine = count_figures(1, event.duration_beats)
                                theirs = count_figures(1, base.duration_beats)
                                add(
                                    key,
                                    f"En el acorde {where}, el {name} es {mine} y el {first} es "
                                    f"{theirs}.",
                                    "Si en la partitura suenan juntas, iguala la figura; si el "
                                    f"{name} va aparte, es de otra voz.",
                                )
                            if pitch in seen:
                                add(
                                    key,
                                    f"El acorde {where} tiene dos veces el mismo {name}.",
                                    "Borra uno de los dos.",
                                )
                            seen.add(pitch)
        return findings
