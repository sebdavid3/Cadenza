"""Núcleo de dominio puro de Cadenza.

Sin dependencias externas ni acoplamiento a I/O. Exporta el `ScoreDocument` y
sus componentes: anclas estables, eventos de edición inmutables y hallazgos de
validación.
"""

from __future__ import annotations

from .anchor import Anchor, AnchorIndex, BBox, EventKind, EventRef
from .clef import Clef
from .edit import (
    CONTENT_EDIT_OPS,
    MARK_EDIT_OPS,
    EditEvent,
    EditOp,
    create_inverse_edit,
    get_last_active_edit,
)
from .edit_payload import (
    InvalidEditPayload,
    has_complete_before,
    is_canonical_pitch,
    normalize_accidental,
    snapshot_before,
    validate_after,
)
from .finding import (
    Finding,
    Severity,
    SuggestedFinding,
    SuggestionResult,
    translate_finding,
)
from .key_signature import KeySignature
from .notation_marks import (
    Articulation,
    Dynamic,
    DynamicMark,
    Slur,
    SlurType,
    Wedge,
    WedgeType,
)
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
from .score_metadata import (
    COMPOSER_MAX_LENGTH,
    MAX_PARTS,
    PART_NAME_MAX_LENGTH,
    SOURCE_FILENAME_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    Instrument,
    PartMetadata,
    ScoreMetadata,
    normalize_source_filename,
)
from .suggestion import CONFIDENCE_LEVELS, SUGGESTION_SOURCES, SuggestedEdit
from .tie import Tie
from .time_signature import TimeSignature
from .timing import EventTiming, TimingMap, compute_timing_map

__all__ = [
    "COMPOSER_MAX_LENGTH",
    "CONFIDENCE_LEVELS",
    "CONTENT_EDIT_OPS",
    "MARK_EDIT_OPS",
    "MAX_PARTS",
    "PART_NAME_MAX_LENGTH",
    "SOURCE_FILENAME_MAX_LENGTH",
    "SUGGESTION_SOURCES",
    "TITLE_MAX_LENGTH",
    "Anchor",
    "AnchorIndex",
    "Articulation",
    "BBox",
    "Clef",
    "Dynamic",
    "DynamicMark",
    "EditEvent",
    "EditOp",
    "Event",
    "EventKind",
    "EventRef",
    "EventTiming",
    "Finding",
    "Instrument",
    "InvalidEditPayload",
    "KeySignature",
    "Measure",
    "Part",
    "PartMetadata",
    "Provenance",
    "ScoreDocument",
    "ScoreIR",
    "ScoreMetadata",
    "Severity",
    "Slur",
    "SlurType",
    "Staff",
    "SuggestedEdit",
    "SuggestedFinding",
    "SuggestionResult",
    "Tie",
    "TimeSignature",
    "TimingMap",
    "UnsupportedEditOpError",
    "Wedge",
    "WedgeType",
    "apply_edit",
    "build_anchor_index",
    "compute_timing_map",
    "create_inverse_edit",
    "get_last_active_edit",
    "has_complete_before",
    "is_canonical_pitch",
    "materialize",
    "normalize_accidental",
    "normalize_source_filename",
    "origin_anchor",
    "snapshot_before",
    "translate_anchor",
    "translate_finding",
    "validate_after",
]
