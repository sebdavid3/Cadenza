"""Esquemas Pydantic v2 de la API de Cadenza."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from cadenza.application import EffortMetricsData, PersistedFinding
from cadenza.domain import Anchor, EditEvent, EditOp
from cadenza.persistence import EditEventRecord, FindingRecord
from pydantic import BaseModel, ConfigDict, Field


class AnchorPayload(BaseModel):
    """Ancla de evento en formato primitivo (contrato compartido del dominio).

    El ancla es posicional y se interpreta respecto al estado `at_seq`
    correspondiente: estado 0 para el documento crudo, estado `seq - 1`
    (`base_seq`) para una edición, estado `at_seq` para un hallazgo (ADR-0011).
    """

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
    """Payload de una corrección humana (el servidor asigna id, seq y fecha).

    Exige `base_seq`, que identifica el estado sobre el cual se construyó la
    edición (ADR-0011). Si `base_seq` no coincide con el último `seq` de la sesión,
    el servidor responde HTTP 409 Conflict y no persiste nada. El servidor nunca
    reintenta con otro `seq` para no alterar el evento al que apunta el ancla.

    El ancla `anchor` es posicional y se interpreta estrictamente respecto al
    estado base declarado (`base_seq`, ADR-0011).
    """

    model_config = ConfigDict(extra="forbid")

    base_seq: int = Field(
        ge=0,
        description="Número de secuencia del estado sobre el que se preparó la edición (ADR-0011)",
    )
    op: EditOp
    anchor: AnchorPayload
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
    at_seq: int = 0
    status: str = "active"
    dismissed_at: datetime | None = None
    dismissed_by: str | None = None
    dismissal_reason: str | None = None

    @classmethod
    def from_record(cls, record: FindingRecord) -> FindingRead:
        return cls(
            id=record.id,
            rule_id=record.rule_id,
            severity=record.severity,
            message=record.message,
            suggested_fix=record.suggested_fix,
            anchor=record.anchor,
            at_seq=record.at_seq,
            status=record.status,
            dismissed_at=record.dismissed_at,
            dismissed_by=record.dismissed_by,
            dismissal_reason=record.dismissal_reason,
        )

    @classmethod
    def from_persisted(cls, finding: PersistedFinding) -> FindingRead:
        return cls(
            id=finding.id,
            rule_id=finding.rule_id,
            severity=finding.severity,
            message=finding.message,
            suggested_fix=finding.suggested_fix,
            anchor=finding.anchor,
            at_seq=finding.at_seq,
            status=finding.status,
            dismissed_at=finding.dismissed_at,
            dismissed_by=finding.dismissed_by,
            dismissal_reason=finding.dismissal_reason,
        )


class DismissFindingRequest(BaseModel):
    """Payload opcional para descartar un hallazgo como falso positivo (#36)."""

    reason: str | None = None


class EditEventRead(BaseModel):
    id: str
    session_id: str
    seq: int
    op: str
    author: str
    anchor: dict[str, Any]
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reverts_edit_id: str | None = None
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
            reverts_edit_id=record.reverts_edit_id,
            created_at=record.created_at,
        )

    @classmethod
    def from_edit(cls, edit: EditEvent, session_id: str) -> EditEventRead:
        return cls(
            id=edit.id,
            session_id=session_id,
            seq=edit.seq,
            op=edit.op.value,
            author=edit.author,
            anchor=edit.anchor.to_primitive(),
            before=None if edit.before is None else dict(edit.before),
            after=None if edit.after is None else dict(edit.after),
            reverts_edit_id=edit.reverts_edit_id,
            created_at=edit.created_at,
        )


class SessionDetailRead(BaseModel):
    """Documento persistido + findings + correcciones de una sesión (HITL).

    `current_seq` indica el estado de secuencia de la partitura actual (`0` para crudo,
    `n` para `n` ediciones). `current_score` es el ScoreIR materializado y
    `anchor_index` contiene el índice de anclas correspondiente al estado actual,
    con `bbox` y `confidence` heredadas del documento original (ADR-0011).
    """

    session_id: str
    document_id: str
    omr_engine: str
    document: dict[str, Any]
    findings: list[FindingRead]
    edits: list[EditEventRead]
    current_score: dict[str, Any]
    current_seq: int = 0
    anchor_index: dict[str, Any] | None = None
    image_artifact: str | None = None
    model_version: str | None = None
    status: str = "transcribed"


class SessionSummaryRead(BaseModel):
    """Resumen ligero de una sesión para listados (sin el documento JSONB) (#27)."""

    session_id: str
    document_id: str
    omr_engine: str
    model_version: str | None = None
    status: str
    created_at: datetime
    findings_count: int = 0
    edits_count: int = 0


class RevalidateResponse(BaseModel):
    """Respuesta tras revalidación de la partitura (ADR-0011, ADR-0013, #11, #48).

    Devuelve el `current_seq` de la sesión y la lista de hallazgos evaluados,
    cada uno con su `at_seq` correspondiente.
    """

    session_id: str
    current_seq: int
    findings: list[FindingRead]


class FinalizeResponse(BaseModel):
    """Respuesta tras finalizar una sesión de transcripción (ADR-0014, #34)."""

    session_id: str
    status: str
    final_seq: int
    findings: list[FindingRead]


class ReopenResponse(BaseModel):
    """Respuesta tras reabrir una sesión finalizada (ADR-0014, #34)."""

    session_id: str
    status: str
    current_seq: int


class UndoRequest(BaseModel):
    """Payload opcional para deshacer una edición con validación de concurrencia (#35, #48)."""

    base_seq: int | None = Field(
        default=None,
        description=(
            "Número de secuencia base esperado. Si se especifica y no coincide "
            "con el estado actual, responde 409."
        ),
    )


class UndoResponse(BaseModel):
    """Respuesta tras deshacer una edición en el servidor (ADR-0007, ADR-0011, #35, #48)."""

    session_id: str
    current_seq: int
    undone_edit_id: str
    current_score: dict[str, Any]
    anchor_index: dict[str, Any] | None = None
    compensatory_edit_id: str | None = None
    compensatory_edit: EditEventRead | None = None


class TokenResponse(BaseModel):
    """Respuesta de autenticación con token de acceso Bearer (OAuth2)."""

    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    """Perfil público de un usuario autenticado (ADR-0012)."""

    id: str
    username: str
    role: str
    active: bool
    created_at: datetime | None = None


class UserCreate(BaseModel):
    """Payload para dar de alta una cuenta (ADR-0012, #46)."""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8)
    role: str = Field(pattern="^(transcriptor|investigador)$")


class UserUpdate(BaseModel):
    """Payload para modificar rol, estado o restablecer contraseña (ADR-0012, #46)."""

    role: str | None = Field(default=None, pattern="^(transcriptor|investigador)$")
    active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class ChangePasswordRequest(BaseModel):
    """Payload para cambio de contraseña por el propio usuario (ADR-0012, #46)."""

    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


class StatusResponse(BaseModel):
    """Respuesta con mensaje de estado de la operación."""

    status: str
    message: str | None = None


class EffortMetricsCreate(BaseModel):
    """Payload para registrar métricas de esfuerzo de corrección (#13)."""

    model_config = ConfigDict(extra="forbid")

    duration_ms: int = Field(ge=0, description="Duración total de corrección en ms")
    time_to_first_edit_ms: int | None = Field(
        default=None, ge=0, description="Tiempo hasta la primera edición en ms"
    )
    interventions: dict[str, int] = Field(
        default_factory=dict, description="Intervenciones por número de compás"
    )


class EffortMetricsRead(BaseModel):
    """Métricas de esfuerzo persistidas para una sesión (#13)."""

    id: str
    session_id: str
    duration_ms: int
    time_to_first_edit_ms: int | None
    interventions: dict[str, int]
    created_at: datetime

    @classmethod
    def from_data(cls, data: EffortMetricsData) -> EffortMetricsRead:
        return cls(
            id=data.id,
            session_id=data.session_id,
            duration_ms=data.duration_ms,
            time_to_first_edit_ms=data.time_to_first_edit_ms,
            interventions=data.interventions,
            created_at=data.created_at,
        )
