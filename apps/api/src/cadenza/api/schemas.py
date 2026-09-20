"""Esquemas Pydantic v2 de la API de Cadenza."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from cadenza.domain import Anchor, EditOp
from cadenza.persistence import EditEventRecord, FindingRecord
from pydantic import BaseModel, ConfigDict, Field


class AnchorPayload(BaseModel):
    """Ancla de evento en formato primitivo (contrato compartido del dominio)."""

    model_config = ConfigDict(extra="forbid")

    part: int = Field(ge=0)
    staff: int = Field(ge=0)
    measure: int = Field(ge=1)
    voice: int = Field(ge=0)
    event_index: int = Field(ge=0)
    staff_id: str = Field(min_length=1)
    bbox: list[float] | None = None
    confidence: float | None = None

    def to_anchor(self) -> Anchor:
        return Anchor.from_primitive(self.model_dump())


class EditEventCreate(BaseModel):
    """Payload de una corrección humana (el servidor asigna id, seq y fecha)."""

    model_config = ConfigDict(extra="forbid")

    op: EditOp
    anchor: AnchorPayload
    author: str = Field(min_length=1)
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class TranscribeResponse(BaseModel):
    session_id: str
    document_id: str
    omr_engine: str
    findings_count: int


class FindingRead(BaseModel):
    id: int
    rule_id: str
    severity: str
    message: str
    suggested_fix: str | None
    anchor: dict[str, Any]

    @classmethod
    def from_record(cls, record: FindingRecord) -> FindingRead:
        return cls(
            id=record.id,
            rule_id=record.rule_id,
            severity=record.severity,
            message=record.message,
            suggested_fix=record.suggested_fix,
            anchor=record.anchor,
        )


class EditEventRead(BaseModel):
    id: str
    session_id: str
    seq: int
    op: str
    author: str
    anchor: dict[str, Any]
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime

    @classmethod
    def from_record(cls, record: EditEventRecord) -> EditEventRead:
        return cls(
            id=record.id,
            session_id=record.session_id,
            seq=record.seq,
            op=record.op,
            author=record.author,
            anchor=record.anchor,
            before=record.before,
            after=record.after,
            created_at=record.created_at,
        )
