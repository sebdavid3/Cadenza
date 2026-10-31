"""`tuplet.incomplete`: tresillo incompleto (ADR-0040 §6).

En el `ScoreIR` un tresillo es una duración con 3 en el denominador (ADR-0017), sin un grupo
explícito: un grupo son los eventos seguidos de una voz con ese factor, y está completo si su
suma es una figura sin tresillo. Los cinquillos y septillos quedan fuera: los señala
`measure.balance` si no cuadran. Sin candidatos: no se sabe la altura de la nota que falta.
"""

from __future__ import annotations

from cadenza.domain import Finding, ScoreDocument, Severity

from ..language import de, figure_of, measure_phrase, number_word, position_phrase
from .base import ValidationRule
from .support import anchor_map, incomplete_tuplets, voices_of

RULE_ID = "tuplet.incomplete"


class TupletIncompleteRule(ValidationRule):
    """A ningún tresillo le falta ni le sobra una parte."""

    @property
    def rule_id(self) -> str:
        return RULE_ID

    def evaluate(self, document: ScoreDocument) -> list[Finding]:
        anchors = anchor_map(document.anchors)
        findings: list[Finding] = []
        for part_index, part in enumerate(document.score.parts):
            for staff_index, staff in enumerate(part.staves):
                for measure in staff.measures:
                    for voice, events in voices_of(measure).items():
                        for group in incomplete_tuplets(events):
                            missing = group.missing_units
                            unit = figure_of(group.unit)
                            anchor = anchors.get(
                                (part_index, staff_index, measure.number, voice, group.indices[0])
                            )
                            if missing is None or unit is None or anchor is None:
                                continue
                            written = unit.written
                            where = position_phrase(group.onset, measure.time_signature)
                            head = (
                                f"En {measure_phrase(measure.number)}, al tresillo de "
                                f"{written.name(plural=True)} {de(where)}"
                            )
                            if missing == 1:
                                message = f"{head} le falta una {written.name()}."
                                fix = (
                                    "Revisa el tresillo: puede que falte una nota o que una de "
                                    f"sus {written.name(plural=True)} sea más larga."
                                )
                            else:
                                message = (
                                    f"{head} le faltan {number_word(missing)} "
                                    f"{written.name(plural=True)}."
                                )
                                fix = (
                                    "Revisa el tresillo: puede que falten dos notas o que "
                                    "sobre una."
                                )
                            findings.append(
                                Finding(
                                    anchor=anchor,
                                    rule_id=RULE_ID,
                                    severity=Severity.ERROR,
                                    message=message,
                                    suggested_fix=fix,
                                )
                            )
        return findings
