"""Puerto `OMREngine`: contrato de transcripción OMR de Cadenza.

Toda la capacidad de OMR del sistema se declara aquí. Los adaptadores
(`FakeOMREngine`, `HOMREngine`, y en el futuro `OemerEngine`) dependen del
dominio, nunca al contrario (ADR-0001, ADR-0005).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from cadenza.domain import ScoreDocument


class OMREngine(ABC):
    """Puerto que convierte una imagen de partitura en un `ScoreDocument`.

    El resultado es la transcripción **cruda**: `ScoreIR` + `AnchorIndex` +
    `Provenance`. El puerto no filtra detalles del motor (modelo, dispositivo,
    formatos intermedios) para que los adaptadores sean intercambiables.
    """

    @property
    @abstractmethod
    def engine_id(self) -> str:
        """Identificador estable del motor, usado en `Provenance.omr_engine`."""

    @abstractmethod
    def transcribe(self, image_path: Path) -> ScoreDocument:
        """Transcribe la imagen y devuelve el `ScoreDocument` resultante."""
