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


class EventRefPayload(BaseModel):
    """Referencia mínima al evento del ScoreIR asociado a un ancla."""

    kind: str = Field(description="Tipo de evento musical ('note', 'rest', 'clef', 'key', 'time')")
    ir_handle: str | None = Field(
        default=None, description="Identificador interno del manejador IR"
    )
    bbox: list[float] | None = Field(
        default=None, description="Coordenadas normalizadas de bounding box"
    )
    confidence: float | None = Field(default=None, description="Confianza asignada al evento")


class AnchorEntryPayload(BaseModel):
    """Entrada individual en el mapa de anclas del ScoreDocument."""

    anchor: AnchorPayload
    event: EventRefPayload


class AnchorIndexPayload(BaseModel):
    """Índice determinista de anclas del documento o estado materializado."""

    entries: list[AnchorEntryPayload] = Field(
        default_factory=list, description="Lista ordenada de asociaciones ancla-evento"
    )


class TimeSignaturePayload(BaseModel):
    """Signatura de compás (métrica) de un compás."""

    beats: int = Field(gt=0, description="Número de pulsos por compás")
    beat_type: int = Field(gt=0, description="Figura musical que representa un pulso")


class ClefPayload(BaseModel):
    """Clave musical (p. ej. Sol, Fa, Do)."""

    sign: str = Field(description="Símbolo de clave ('G', 'F', 'C')")
    line: int = Field(
        default=2, gt=0, description="Línea del pentagrama en la que se ubica la clave"
    )
    octave_change: int = Field(default=0, description="Desplazamiento de octava (+1, -1, 0)")


class KeySignaturePayload(BaseModel):
    """Armadura de clave expresada en número de quintas respecto a Do mayor."""

    fifths: int = Field(
        ge=-7, le=7, description="Número de alteraciones en quintas (-7 bemoles a +7 sostenidos)"
    )
    mode: str | None = Field(default=None, description="Modo armónico opcional ('major', 'minor')")


class ScoreEventPayload(BaseModel):
    """Evento musical individual en un compás (nota, silencio, etc.)."""

    kind: str = Field(description="Tipo de evento ('note', 'rest', etc.)")
    voice: int = Field(default=0, ge=0, description="Índice de voz dentro del pentagrama")
    pitch: str | None = Field(
        default=None, description="Altura en notación científica (p. ej. 'C4', 'F#5')"
    )
    duration_beats: str | None = Field(
        default=None, description="Duración exacta en pulsos como fracción ('1/4', '1', '3/8')"
    )
    tie: str | None = Field(
        default=None, description="Estado de ligadura ('start', 'continue', 'stop')"
    )
    is_chord: bool = Field(
        default=False, description="Indica si la nota pertenece a un acorde simultáneo"
    )
    bbox: list[float] | None = Field(default=None, description="Bounding box normalizado")
    confidence: float | None = Field(
        default=None, description="Puntuación de confianza del reconocimiento"
    )
    ir_handle: str | None = Field(default=None, description="Manejador de referencia interna")


class MeasurePayload(BaseModel):
    """Compás que agrupa eventos musicales y metadatos estructurales."""

    number: int = Field(ge=1, description="Número de compás (1-indexed)")
    events: list[ScoreEventPayload] = Field(description="Secuencia de eventos musicales")
    time_signature: TimeSignaturePayload | None = Field(
        default=None, description="Signatura de compás"
    )
    clef: ClefPayload | None = Field(default=None, description="Clave musical activa en el compás")
    key_signature: KeySignaturePayload | None = Field(
        default=None, description="Armadura de clave activa"
    )


class StaffPayload(BaseModel):
    """Pentagrama que agrupa compases en una parte."""

    id: str = Field(description="Identificador único del pentagrama (p. ej. 'part-0-staff-0')")
    measures: list[MeasurePayload] = Field(description="Lista de compases del pentagrama")


class PartPayload(BaseModel):
    """Parte instrumental o vocal que agrupa uno o varios pentagramas."""

    id: str = Field(description="Identificador de la parte (p. ej. 'part-0')")
    staves: list[StaffPayload] = Field(description="Lista de pentagramas de la parte")


class ScoreIRPayload(BaseModel):
    """Representación intermedia simbólica normalizada de la partitura (ScoreIR)."""

    parts: list[PartPayload] = Field(description="Partes que componen la partitura")


class ProvenancePayload(BaseModel):
    """Trazabilidad y procedencia de la inferencia OMR y validación."""

    omr_engine: str = Field(description="Nombre del motor OMR utilizado ('fake', 'homr')")
    model_version: str | None = Field(default=None, description="Versión del modelo OMR")
    rules_version: str | None = Field(default=None, description="Versión del catálogo de reglas")
    source_image_hash: str | None = Field(
        default=None, description="Hash SHA-256 de la imagen de origen"
    )
    created_at: str | None = Field(default=None, description="Marca de tiempo ISO-8601 de creación")
    device: str | None = Field(
        default=None, description="Dispositivo de cómputo efectivo ('cpu', 'cuda')"
    )


class ScoreDocumentPayload(BaseModel):
    """Documento musical integral: ScoreIR + Índice de anclas + Provenance."""

    id: str = Field(description="Identificador único del documento")
    score: ScoreIRPayload = Field(description="Árbol simbólico ScoreIR")
    anchors: AnchorIndexPayload = Field(description="Índice de anclas de la partitura")
    provenance: ProvenancePayload = Field(description="Metadatos de procedencia del documento")


class ErrorDetail(BaseModel):
    """Estructura uniforme de mensaje de error HTTP de la API."""

    detail: Any = Field(description="Descripción del error o detalle de validación")


class VersionResponse(BaseModel):
    """Versión de la API y del servicio."""

    api_version: str = Field(default="1.0.0", description="Versión del contrato API v1")
    app_version: str = Field(default="1.0.0", description="Versión de la aplicación Cadenza")


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
    anchor: AnchorPayload
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
            anchor=AnchorPayload.model_validate(record.anchor),
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
            anchor=AnchorPayload.model_validate(finding.anchor),
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
    anchor: AnchorPayload
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
            anchor=AnchorPayload.model_validate(record.anchor),
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
            anchor=AnchorPayload.model_validate(edit.anchor.to_primitive()),
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
    document: ScoreDocumentPayload
    findings: list[FindingRead]
    edits: list[EditEventRead]
    current_score: ScoreIRPayload | None = None
    current_seq: int = 0
    anchor_index: AnchorIndexPayload | None = None
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
    current_score: ScoreIRPayload
    anchor_index: AnchorIndexPayload | None = None
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
