"""Núcleo de dominio puro de Cadenza.

Sin dependencias externas ni acoplamiento a I/O. Exporta el `ScoreDocument` y
sus componentes: anclas estables, eventos de edición inmutables y hallazgos de
validación.
"""

from __future__ import annotations

from .anchor import Anchor, AnchorIndex, BBox, EventKind, EventRef
from .clef import Clef
from .edit import EditEvent, EditOp, create_inverse_edit, get_last_active_edit
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
from .timing import EventTiming, TimingMap, compute_timing_map

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
    "EventTiming",
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
    "TimingMap",
    "UnsupportedEditOpError",
    "apply_edit",
    "build_anchor_index",
    "compute_timing_map",
    "create_inverse_edit",
    "get_last_active_edit",
    "materialize",
    "origin_anchor",
    "translate_anchor",
    "translate_finding",
]
