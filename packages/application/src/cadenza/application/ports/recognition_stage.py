"""Puerto de una etapa de reconocimiento que corre tras el motor OMR (ADR-0059 §1).

`RecognitionStage` es un `typing.Protocol`: la etapa del compás de `cadenza.omr` (`MeterStage`)
lo cumple por estructura, y el caso de uso de transcribir no depende de su clase.
"""

from __future__ import annotations

from typing import Protocol

from cadenza.domain import ScoreDocument


class RecognitionStage(Protocol):
    """Recibe la transcripción del motor y devuelve la que se valida y se guarda."""

    def apply(self, document: ScoreDocument) -> ScoreDocument:
        """El documento con lo que la etapa reconoce, y la etapa anotada en su procedencia."""
        ...
