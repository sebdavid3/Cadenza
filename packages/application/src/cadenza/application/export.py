"""Tipos y modelos para la exportación de partituras (Issue #12, ADR-0010)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExportFormat(StrEnum):
    """Formatos de exportación admitidos por el sistema."""

    MUSICXML = "musicxml"
    MIDI = "midi"


@dataclass(frozen=True)
class ExportedScore:
    """Resultado binario o textual de la exportación de una partitura."""

    content: bytes | str
    media_type: str
    filename: str
