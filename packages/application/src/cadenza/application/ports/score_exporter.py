"""Puerto para la serialización y exportación de partituras (Issue #12, ADR-0010)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from cadenza.domain import ScoreIR


class ScoreExporter(ABC):
    """Puerto para la exportación de un ScoreIR a formatos estándar (MusicXML, MIDI)."""

    @abstractmethod
    def to_musicxml(self, score: ScoreIR) -> str:
        """Serializa un ScoreIR a una cadena de texto en formato MusicXML 4.0."""

    @abstractmethod
    def to_midi(self, score: ScoreIR) -> bytes:
        """Serializa un ScoreIR a una secuencia de bytes en formato MIDI 1.0."""


class InMemoryScoreExporter(ScoreExporter):
    """Doble de prueba en memoria sin dependencias de notación externa."""

    def __init__(
        self,
        musicxml_template: str | None = None,
        midi_bytes: bytes | None = None,
    ) -> None:
        self.musicxml_template = (
            musicxml_template
            or '<?xml version="1.0" encoding="UTF-8"?>\n<score-partwise version="4.0"/>'
        )
        self.midi_bytes = (
            midi_bytes
            or b"MThd\x00\x00\x00\x06\x00\x01\x00\x01\x01\xe0MTrk\x00\x00\x00\x04\x00\xff/\x00"
        )
        self.exported_scores: list[tuple[str, ScoreIR]] = []

    def to_musicxml(self, score: ScoreIR) -> str:
        self.exported_scores.append(("musicxml", score))
        return self.musicxml_template

    def to_midi(self, score: ScoreIR) -> bytes:
        self.exported_scores.append(("midi", score))
        return self.midi_bytes
