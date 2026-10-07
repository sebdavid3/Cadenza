"""Núcleo de dominio puro de Cadenza.

Sin dependencias externas ni acoplamiento a I/O. Exporta el `ScoreDocument` y
sus componentes: anclas estables, eventos de edición inmutables y hallazgos de
validación.
"""

from __future__ import annotations

from .anchor import Anchor, AnchorIndex, BBox, EventKind, EventRef
from .clef import Clef
from .edit import EditEvent, EditOp
from .finding import Finding, Severity, translate_finding
from .key_signature import KeySignature
from .projection import (
    UnsupportedEditOpError,
    apply_edit,
    materialize,
    origin_anchor,
    translate_anchor,
)
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
from .tie import Tie
from .time_signature import TimeSignature

__all__ = [
    "Anchor",
    "AnchorIndex",
    "BBox",
    "Clef",
    "EditEvent",
    "EditOp",
    "Event",
    "EventKind",
    "EventRef",
    "Finding",
    "KeySignature",
    "Measure",
    "Part",
    "Provenance",
    "ScoreDocument",
    "ScoreIR",
    "Severity",
    "Staff",
    "Tie",
    "TimeSignature",
    "UnsupportedEditOpError",
    "apply_edit",
    "build_anchor_index",
    "materialize",
    "origin_anchor",
    "translate_anchor",
    "translate_finding",
]
