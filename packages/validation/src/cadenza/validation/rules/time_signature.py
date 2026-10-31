"""`time.signature`: indicación de compás (ADR-0040 §5).

Detecta una métrica leída que no casa con lo que suman los compases: el error más visible de
HOMR (#237), que con la métrica leída daría un `measure.balance` por compás, casi todos
falsos. El cálculo (tramos, rachas y su suma S) está en `support.meter_spans`, porque
`measure.balance` comprueba esos compases contra S.

Sin la operación de #236 para cambiar el compás, el hallazgo no trae candidatos.
"""

from __future__ import annotations

from cadenza.domain import Finding, ScoreDocument, Severity

from ..language import (
    capitalize,
    de,
    in_beat_figures,
    measure_phrase,
    measures_phrase,
    meter_name,
    meter_symbol,
)
from .base import ValidationRule
from .support import MeterSpan, anchor_map, first_visible, meter_spans

RULE_ID = "time.signature"


def _texts(span: MeterSpan, start: int) -> tuple[str, str]:
    total = in_beat_figures(span.capacity, span.signature.beat_type)
    read = meter_name(span.signature)
    proposed = span.proposed
    assert proposed is not None  # `meter_spans` solo da sumas que se escriben como métrica
    meter = meter_name(proposed)
    if not span.whole:
        return (
            f"Desde el compás {start}, los compases suman {total} y la indicación sigue siendo "
            f"{read}.",
            f"Revisa si en el compás {start} cambia el compás: puede que sea {meter}.",
        )
    which = capitalize(measures_phrase(span.matching, span.measured))
    symbol = meter_symbol(proposed)
    meter_text = f"{meter} ({symbol})" if symbol else meter
    return (
        f"{which} suman {total} y la indicación de compás es {read}.",
        f"Revisa la indicación de compás {de(measure_phrase(start))}: puede que sea {meter_text}. "
        f"Mientras no cambie, la duración de cada compás se comprueba con {total}.",
    )


class TimeSignatureRule(ValidationRule):
    """La métrica leída casa con lo que suman los compases de su tramo."""

    @property
    def rule_id(self) -> str:
        return RULE_ID

    def evaluate(self, document: ScoreDocument) -> list[Finding]:
        anchors = anchor_map(document.anchors)
        findings: list[Finding] = []
        for part_index, part in enumerate(document.score.parts):
            if not part.staves:
                continue
            staff = part.staves[0]
            by_number = {measure.number: measure for measure in staff.measures}
            for span in meter_spans(part, part_index):
                measure = by_number[span.start]
                anchor = first_visible(anchors, part_index, 0, measure)
                if anchor is None:
                    continue
                message, fix = _texts(span, span.start)
                findings.append(
                    Finding(
                        anchor=anchor,
                        rule_id=RULE_ID,
                        severity=Severity.WARNING,
                        message=message,
                        suggested_fix=fix,
                    )
                )
        return findings
