"""Anclas estables de evento.

Un `Anchor` identifica de forma determinista y estable un evento musical como
ruta lógica (parte, pentagrama, compás, voz, índice dentro de la voz), sin
depender de identificadores corruptibles de MusicXML ni de punteros de memoria.
Es el contrato compartido por validación (M2), edición (M3) y aprendizaje
activo (M4).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

BBox = tuple[float, float, float, float]


class EventKind(StrEnum):
    """Naturaleza del evento musical referenciado por un ancla."""

    NOTE = "note"
    REST = "rest"
    CLEF = "clef"
    KEY = "key"
    TIME = "time"


def _freeze_bbox(value: object) -> BBox | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("bbox must have four components")
    x0, y0, x1, y1 = value
    return (float(x0), float(y0), float(x1), float(y1))


@dataclass(frozen=True, slots=True)
class Anchor:
    """Ruta lógica estable que referencia un evento musical."""

    part: int
    staff: int
    measure: int
    voice: int
    event_index: int
    staff_id: str
    bbox: BBox | None = None
    confidence: float | None = None

    def __post_init__(self) -> None:
        for name in ("part", "staff", "voice", "event_index"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0")
        if self.measure < 1:
            raise ValueError("measure must be >= 1")
        if not self.staff_id:
            raise ValueError("staff_id must be non-empty")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")

    def sort_key(self) -> tuple[int, int, int, int, int, str]:
        """Clave de orden determinista para iterar el índice de anclas."""

        return (
            self.part,
            self.staff,
            self.measure,
            self.voice,
            self.event_index,
            self.staff_id,
        )

    def to_primitive(self) -> dict[str, Any]:
        return {
            "part": self.part,
            "staff": self.staff,
            "measure": self.measure,
            "voice": self.voice,
            "event_index": self.event_index,
            "staff_id": self.staff_id,
            "bbox": list(self.bbox) if self.bbox is not None else None,
            "confidence": self.confidence,
        }

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> Anchor:
        return cls(
            part=int(data["part"]),
            staff=int(data["staff"]),
            measure=int(data["measure"]),
            voice=int(data["voice"]),
            event_index=int(data["event_index"]),
            staff_id=str(data["staff_id"]),
            bbox=_freeze_bbox(data.get("bbox")),
            confidence=None if data.get("confidence") is None else float(data["confidence"]),
        )


@dataclass(frozen=True, slots=True)
class EventRef:
    """Referencia mínima al evento del `ScoreIR` asociado a un ancla."""

    kind: EventKind
    ir_handle: str | None = None
    bbox: BBox | None = None
    confidence: float | None = None

    def to_primitive(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "ir_handle": self.ir_handle,
            "bbox": list(self.bbox) if self.bbox is not None else None,
            "confidence": self.confidence,
        }

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> EventRef:
        return cls(
            kind=EventKind(data["kind"]),
            ir_handle=None if data.get("ir_handle") is None else str(data["ir_handle"]),
            bbox=_freeze_bbox(data.get("bbox")),
            confidence=None if data.get("confidence") is None else float(data["confidence"]),
        )


@dataclass(frozen=True, slots=True)
class AnchorIndex:
    """Mapa determinista ``Anchor -> EventRef``.

    La iteración se ordena por la clave lógica del ancla, de modo que dos
    índices construidos a partir del mismo `ScoreIR` son idénticos y su
    serialización es reproducible.
    """

    _entries: Mapping[Anchor, EventRef]
    _by_key: Mapping[tuple[int, int, int, int, int, str], tuple[Anchor, EventRef]]

    @classmethod
    def empty(cls) -> AnchorIndex:
        return cls(MappingProxyType({}), MappingProxyType({}))

    @classmethod
    def from_entries(cls, entries: Mapping[Anchor, EventRef]) -> AnchorIndex:
        data = dict(entries)
        by_key = {anchor.sort_key(): (anchor, ref) for anchor, ref in data.items()}
        return cls(MappingProxyType(data), MappingProxyType(by_key))

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, anchor: object) -> bool:
        if anchor in self._entries:
            return True
        if isinstance(anchor, Anchor):
            return anchor.sort_key() in self._by_key
        return False

    def get(self, anchor: Anchor) -> EventRef | None:
        ref = self._entries.get(anchor)
        if ref is not None:
            return ref
        entry = self._by_key.get(anchor.sort_key())
        return entry[1] if entry is not None else None

    def find_anchor(self, anchor: Anchor) -> Anchor | None:
        """Devuelve el ancla canónica del índice que comparte la misma ruta lógica."""
        entry = self._by_key.get(anchor.sort_key())
        return entry[0] if entry is not None else None

    def __iter__(self) -> Iterator[Anchor]:
        return iter(self.anchors())

    def anchors(self) -> tuple[Anchor, ...]:
        return tuple(sorted(self._entries, key=Anchor.sort_key))

    def items(self) -> tuple[tuple[Anchor, EventRef], ...]:
        return tuple((anchor, self._entries[anchor]) for anchor in self.anchors())

    def to_primitive(self) -> dict[str, Any]:
        return {
            "entries": [
                {"anchor": anchor.to_primitive(), "event": event.to_primitive()}
                for anchor, event in self.items()
            ]
        }

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> AnchorIndex:
        entries: dict[Anchor, EventRef] = {}
        for item in data["entries"]:
            anchor = Anchor.from_primitive(item["anchor"])
            entries[anchor] = EventRef.from_primitive(item["event"])
        return cls.from_entries(entries)
