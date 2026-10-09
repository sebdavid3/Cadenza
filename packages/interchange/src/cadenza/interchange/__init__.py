"""Frontera canónica de notación de Cadenza (MusicXML/MEI/**kern ↔ `ScoreIR`)."""

from __future__ import annotations

from .notation import (
    InterchangeError,
    music21_stream_to_score_ir,
    musicxml_to_score_ir,
    read_score,
    score_ir_to_midi,
    score_ir_to_music21,
    score_ir_to_musicxml,
)
from .score_exporter import Music21ScoreExporter

__all__ = [
    "InterchangeError",
    "Music21ScoreExporter",
    "music21_stream_to_score_ir",
    "musicxml_to_score_ir",
    "read_score",
    "score_ir_to_midi",
    "score_ir_to_music21",
    "score_ir_to_musicxml",
]
