"""Adaptador de ScoreExporter basado en music21 (Issue #12, ADR-0010)."""

from __future__ import annotations

from cadenza.application import ScoreExporter
from cadenza.domain import ScoreIR, ScoreMetadata

from .notation import score_ir_to_midi, score_ir_to_musicxml


class Music21ScoreExporter(ScoreExporter):
    """Adaptador de exportación que traduce ScoreIR a MusicXML y MIDI mediante music21."""

    def to_musicxml(self, score: ScoreIR, metadata: ScoreMetadata | None = None) -> str:
        """Serializa ScoreIR a MusicXML 4.0, con el título y los instrumentos si se dan."""
        return score_ir_to_musicxml(score, metadata)

    def to_midi(self, score: ScoreIR, metadata: ScoreMetadata | None = None) -> bytes:
        """Serializa ScoreIR a MIDI 1.0 en bytes, con el programa de cada parte si se da."""
        return score_ir_to_midi(score, metadata)
