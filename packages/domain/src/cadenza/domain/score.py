"""Representación intermedia simbólica (`ScoreIR`) y agregado `ScoreDocument`.

En esta fase el `ScoreIR` es un contenedor neutral: no parsea MusicXML ni usa
`music21`. La frontera de parseo se incorporará en la Fase 2. Su única
responsabilidad aquí es dar estructura suficiente para derivar anclas estables.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .anchor import Anchor, AnchorIndex, BBox, EventKind, EventRef
from .provenance import Provenance


@dataclass(frozen=True, slots=True)
class Event:
    """Evento musical neutral del `ScoreIR`."""

    kind: EventKind
    voice: int = 0
    pitch: str | None = None
    duration_beats: Fraction | None = None
    bbox: BBox | None = None
    confidence: float | None = None
    ir_handle: str | None = None

    def to_primitive(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "voice": self.voice,
            "pitch": self.pitch,
            "duration_beats": None if self.duration_beats is None else str(self.duration_beats),
            "bbox": list(self.bbox) if self.bbox is not None else None,
            "confidence": self.confidence,
            "ir_handle": self.ir_handle,
        }

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> Event:
        bbox = data.get("bbox")
        duration = data.get("duration_beats")
        return cls(
            kind=EventKind(data["kind"]),
            voice=int(data["voice"]),
            pitch=None if data.get("pitch") is None else str(data["pitch"]),
            duration_beats=None if duration is None else Fraction(str(duration)),
            bbox=(
                None
                if bbox is None
                else (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
            ),
            confidence=None if data.get("confidence") is None else float(data["confidence"]),
            ir_handle=None if data.get("ir_handle") is None else str(data["ir_handle"]),
        )


@dataclass(frozen=True, slots=True)
class Measure:
    number: int
    events: tuple[Event, ...] = ()

    def to_primitive(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "events": [event.to_primitive() for event in self.events],
        }

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> Measure:
        return cls(
            number=int(data["number"]),
            events=tuple(Event.from_primitive(item) for item in data["events"]),
        )


@dataclass(frozen=True, slots=True)
class Staff:
    id: str
    measures: tuple[Measure, ...] = ()

    def to_primitive(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "measures": [measure.to_primitive() for measure in self.measures],
        }

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> Staff:
        return cls(
            id=str(data["id"]),
            measures=tuple(Measure.from_primitive(item) for item in data["measures"]),
        )


@dataclass(frozen=True, slots=True)
class Part:
    id: str
    staves: tuple[Staff, ...] = ()

    def to_primitive(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "staves": [staff.to_primitive() for staff in self.staves],
        }

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> Part:
        return cls(
            id=str(data["id"]),
            staves=tuple(Staff.from_primitive(item) for item in data["staves"]),
        )


@dataclass(frozen=True, slots=True)
class ScoreIR:
    """Representación intermedia simbólica normalizada (neutral en Fase 0)."""

    parts: tuple[Part, ...] = ()

    def to_primitive(self) -> dict[str, Any]:
        return {"parts": [part.to_primitive() for part in self.parts]}

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> ScoreIR:
        return cls(parts=tuple(Part.from_primitive(item) for item in data["parts"]))


def build_anchor_index(score: ScoreIR) -> AnchorIndex:
    """Deriva el índice de anclas a partir del `ScoreIR` de forma determinista.

    El `event_index` es la posición del evento dentro de su ``(compás, voz)``,
    de modo que la ruta lógica sea estable e independiente del orden global.
    """

    entries: dict[Anchor, EventRef] = {}
    for part_position, part in enumerate(score.parts):
        for staff_position, staff in enumerate(part.staves):
            for measure in staff.measures:
                counters: dict[int, int] = {}
                for event in measure.events:
                    index = counters.get(event.voice, 0)
                    counters[event.voice] = index + 1
                    anchor = Anchor(
                        part=part_position,
                        staff=staff_position,
                        measure=measure.number,
                        voice=event.voice,
                        event_index=index,
                        staff_id=staff.id,
                        bbox=event.bbox,
                        confidence=event.confidence,
                    )
                    entries[anchor] = EventRef(
                        kind=event.kind,
                        ir_handle=event.ir_handle,
                        bbox=event.bbox,
                        confidence=event.confidence,
                    )
    return AnchorIndex.from_entries(entries)


@dataclass(frozen=True, slots=True)
class ScoreDocument:
    """Fuente de verdad del sistema: `ScoreIR` + `AnchorIndex` + `Provenance`."""

    id: str
    score: ScoreIR
    anchors: AnchorIndex
    provenance: Provenance

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must be non-empty")

    def to_primitive(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "score": self.score.to_primitive(),
            "anchors": self.anchors.to_primitive(),
            "provenance": self.provenance.to_primitive(),
        }

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> ScoreDocument:
        return cls(
            id=str(data["id"]),
            score=ScoreIR.from_primitive(data["score"]),
            anchors=AnchorIndex.from_primitive(data["anchors"]),
            provenance=Provenance.from_primitive(data["provenance"]),
        )
