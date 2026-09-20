"""Frontera canónica de notación de Cadenza (MusicXML/MEI/**kern ↔ `ScoreIR`)."""

from __future__ import annotations

from .notation import (
    InterchangeError,
    music21_stream_to_score_ir,
    musicxml_to_score_ir,
    read_score,
    score_ir_to_musicxml,
)

__all__ = [
    "InterchangeError",
    "music21_stream_to_score_ir",
    "musicxml_to_score_ir",
    "read_score",
    "score_ir_to_musicxml",
]
