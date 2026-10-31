"""`key.consistency`: armaduras distintas (ADR-0040 §8).

Solo comprueba que los pentagramas de una misma parte (un piano) lleven la misma armadura en
cada compás. Dispara desde el compás en que empiezan a discrepar, una vez por tramo de
discrepancia, y nunca entre partes distintas: un instrumento transpositor lleva otra armadura.

Se retiraron las comprobaciones de las alteraciones frente a la armadura (un bemol con
armadura de sostenidos y al revés) y de sostenido y bemol sobre la misma letra: la primera
señalaba alteraciones escritas y correctas, como la sensible de las tonalidades menores, y lo
que sí eran errores lo cubre `accidental.repeated`; la segunda no aparece en el corpus.
"""

from __future__ import annotations

from cadenza.domain import EditOp, Finding, ScoreDocument, Severity, SuggestedEdit

from ..language import Phrase, de, key_name, measure_phrase
from .base import ValidationRule
from .support import active_keys, anchor_map, first_visible

RULE_ID = "key.consistency"


def _staff_phrase(staff_index: int, staves: int) -> Phrase:
    """«el pentagrama de abajo» en un piano; con más, por su número desde arriba."""
    return Phrase("el", "pentagrama de abajo" if staves == 2 else f"pentagrama {staff_index + 1}")


class KeyConsistencyRule(ValidationRule):
    """Los pentagramas de una misma parte llevan la misma armadura."""

    @property
    def rule_id(self) -> str:
        return RULE_ID

    def evaluate(self, document: ScoreDocument) -> list[Finding]:
        anchors = anchor_map(document.anchors)
        findings: list[Finding] = []
        for part_index, part in enumerate(document.score.parts):
            if len(part.staves) < 2:
                continue
            top = part.staves[0]
            top_keys = dict(
                zip((measure.number for measure in top.measures), active_keys(top), strict=True)
            )
            for staff_index, staff in enumerate(part.staves[1:], start=1):
                # Si el tramo de discrepancia en curso ya se señaló: una vez por tramo, aunque
                # las armaduras cambien sin llegar a coincidir.
                flagged = False
                for measure, fifths in zip(staff.measures, active_keys(staff), strict=True):
                    upper = top_keys.get(measure.number)
                    if upper is None or upper == fifths:
                        flagged = False
                        continue
                    if flagged:
                        continue
                    anchor = first_visible(anchors, part_index, staff_index, measure)
                    if anchor is None:
                        # Sin nada que elegir en este compás, se señala en el siguiente.
                        continue
                    flagged = True
                    staff_phrase = _staff_phrase(staff_index, len(part.staves))
                    findings.append(
                        Finding(
                            anchor=anchor,
                            rule_id=RULE_ID,
                            severity=Severity.WARNING,
                            message=(
                                f"En {measure_phrase(measure.number)}, la armadura "
                                f"{de(staff_phrase)} ({key_name(fifths)}) no coincide con la de "
                                f"arriba ({key_name(upper)})."
                            ),
                            suggested_fix=(
                                "Revisa las dos armaduras: en los pentagramas de un mismo piano "
                                "suelen ser iguales."
                            ),
                            candidates=(
                                SuggestedEdit(
                                    op=EditOp.SET_KEY,
                                    anchor=anchor,
                                    after={"fifths": upper},
                                ),
                            ),
                        )
                    )
        return findings
