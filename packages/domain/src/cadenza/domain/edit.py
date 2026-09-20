"""Eventos de edición inmutables del ciclo Human-in-the-Loop (ADR-0007)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from .anchor import Anchor


class EditOp(StrEnum):
    """Operaciones de corrección admitidas sobre un evento anclado."""

    SET_PITCH = "SetPitch"
    SET_DURATION = "SetDuration"
    SET_ACCIDENTAL = "SetAccidental"
    INSERT_EVENT = "InsertEvent"
    DELETE_EVENT = "DeleteEvent"
    SET_CLEF = "SetClef"
    SET_KEY = "SetKey"


@dataclass(frozen=True, slots=True)
class EditEvent:
    """Corrección humana inmutable anclada a un evento musical.

    El estado actual de un `ScoreDocument` se obtiene aplicando la secuencia de
    `EditEvent` sobre el `ScoreIR` crudo. La inmutabilidad es estructural: los
    atributos son de solo lectura y los diccionarios ``before``/``after`` se
    congelan.
    """

    id: str
    document_id: str
    seq: int
    anchor: Anchor
    op: EditOp
    author: str
    created_at: datetime
    before: Mapping[str, Any] | None = None
    after: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must be non-empty")
        if not self.document_id:
            raise ValueError("document_id must be non-empty")
        if not self.author:
            raise ValueError("author must be non-empty")
        if self.seq < 0:
            raise ValueError("seq must be >= 0")
        if self.before is not None:
            object.__setattr__(self, "before", MappingProxyType(dict(self.before)))
        if self.after is not None:
            object.__setattr__(self, "after", MappingProxyType(dict(self.after)))

    def __hash__(self) -> int:
        # Excluye los mappings (no hashables) pero mantiene la identidad del
        # evento; la igualdad generada sí los considera.
        return hash(
            (
                self.id,
                self.document_id,
                self.seq,
                self.anchor,
                self.op,
                self.author,
                self.created_at,
            )
        )

    def to_primitive(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "seq": self.seq,
            "anchor": self.anchor.to_primitive(),
            "op": self.op.value,
            "author": self.author,
            "created_at": self.created_at.isoformat(),
            "before": None if self.before is None else dict(self.before),
            "after": None if self.after is None else dict(self.after),
        }

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> EditEvent:
        before = data.get("before")
        after = data.get("after")
        return cls(
            id=str(data["id"]),
            document_id=str(data["document_id"]),
            seq=int(data["seq"]),
            anchor=Anchor.from_primitive(data["anchor"]),
            op=EditOp(data["op"]),
            author=str(data["author"]),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            before=None if before is None else dict(before),
            after=None if after is None else dict(after),
        )
