"""Caso de uso: transcribir partitura con OMR y validación inicial (ADR-0009, ADR-0012, #45)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from pathlib import Path

from cadenza.omr import OMREngine
from cadenza.validation import ValidationEngine

from ..ports.session_repository import SessionData, SessionRepository
from ..user import User


@dataclass(frozen=True)
class TranscribeResult:
    """Resultado de la transcripción y validación inicial."""

    session_id: str
    document_id: str
    omr_engine: str
    findings_count: int


def transcribe_score(
    image_path: Path,
    *,
    omr_engine: OMREngine,
    validator: ValidationEngine,
    session_repository: SessionRepository,
    current_user: User,
    session_id: str | None = None,
    image_artifact: str | None = None,
) -> TranscribeResult:
    """Ejecuta el pipeline OMR, evalúa reglas y persiste la sesión asignando el dueño."""

    document = omr_engine.transcribe(image_path)
    findings = validator.validate(document)
    document = replace(
        document,
        provenance=replace(document.provenance, rules_version=validator.rules_version),
    )

    actual_session_id = session_id or str(uuid.uuid4())
    session_data = SessionData(
        id=actual_session_id,
        document_id=document.id,
        omr_engine=document.provenance.omr_engine,
        document=document.to_primitive(),
        image_artifact=image_artifact,
        model_version=document.provenance.model_version,
        status="transcribed",
        owner_id=current_user.id,
    )

    session_repository.add(session_data, findings)

    return TranscribeResult(
        session_id=actual_session_id,
        document_id=document.id,
        omr_engine=document.provenance.omr_engine,
        findings_count=len(findings),
    )
