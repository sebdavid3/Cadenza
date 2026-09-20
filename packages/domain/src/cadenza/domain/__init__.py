"""Núcleo de dominio puro de Cadenza.

Sin dependencias externas ni acoplamiento a I/O. Exporta el `ScoreDocument` y
sus componentes: anclas estables, eventos de edición inmutables y hallazgos de
validación.
"""

from __future__ import annotations

from .anchor import Anchor, AnchorIndex, BBox, EventKind, EventRef
from .edit import EditEvent, EditOp
from .finding import Finding, Severity
from .provenance import Provenance
from .score import (
    Event,
    Measure,
    Part,
    ScoreDocument,
    ScoreIR,
    Staff,
    build_anchor_index,
)

__all__ = [
    "Anchor",
    "AnchorIndex",
    "BBox",
    "EditEvent",
    "EditOp",
    "Event",
    "EventKind",
    "EventRef",
    "Finding",
    "Measure",
    "Part",
    "Provenance",
    "ScoreDocument",
    "ScoreIR",
    "Severity",
    "Staff",
    "build_anchor_index",
]
