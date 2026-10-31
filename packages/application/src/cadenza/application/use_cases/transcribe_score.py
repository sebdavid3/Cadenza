"""Caso de uso: transcribir partitura con OMR y validación inicial (ADR-0009, ADR-0012, #45)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from cadenza.domain import Finding
from cadenza.omr import OMREngine
from cadenza.validation import ValidationEngine

from ..ports.artifact_store import ArtifactStore, compute_sha256, detect_image_media_type
from ..ports.session_repository import NewSuggestion, SessionData, SessionRepository
from ..ports.suggestion_model import SuggestionModel
from ..suggestions import suggest
from ..user import User


@dataclass(frozen=True)
class TranscribeResult:
    """Resultado de la transcripción y validación inicial."""

    session_id: str
    document_id: str
    omr_engine: str
    findings_count: int
    condition: str = "assisted"
    test_score_id: str | None = None


def normalize_condition(condition: str | None) -> str:
    """Normaliza y valida la condición experimental ('assisted' o 'unassisted') (#33, D38)."""
    if not condition:
        return "assisted"
    val = condition.strip().lower()
    if val in ("assisted", "asistida", "con_validador", "con-validador"):
        return "assisted"
    if val in ("unassisted", "no_asistida", "no-asistida", "sin_validador", "sin-validador"):
        return "unassisted"
    raise ValueError(f"Condición inválida: '{condition}'. Debe ser 'assisted' o 'unassisted'.")


def transcribe_score(
    image_path: Path,
    *,
    omr_engine: OMREngine,
    validator: ValidationEngine,
    session_repository: SessionRepository,
    current_user: User,
    session_id: str | None = None,
    artifact_store: ArtifactStore | None = None,
    image_artifact: str | None = None,
    condition: str = "assisted",
    test_score_id: str | None = None,
    suggestion_model: SuggestionModel | None = None,
) -> TranscribeResult:
    """Ejecuta el pipeline OMR, evalúa reglas (en condición asistida) y persiste la sesión.

    Con `suggestion_model`, la capa de sugerencias corre tras las reglas y la procedencia
    guarda su versión (ADR-0036 §3, §11). En `unassisted` no corre ni una cosa ni otra (D38).
    """

    norm_condition = normalize_condition(condition)

    actual_image_artifact = image_artifact
    if artifact_store is not None and image_path.is_file():
        image_bytes = image_path.read_bytes()
        media_type = detect_image_media_type(image_bytes)
        actual_image_artifact = artifact_store.put(image_bytes, kind="image", media_type=media_type)
    elif actual_image_artifact is None and image_path.is_file():
        actual_image_artifact = compute_sha256(image_path.read_bytes())

    document = omr_engine.transcribe(image_path)
    assisted = norm_condition != "unassisted"
    rule_findings: Sequence[Finding] = validator.validate(document) if assisted else ()
    model = suggestion_model if assisted else None
    suggested = suggest(document, rule_findings, model)
    findings = [finding for finding, _ in suggested]

    document = replace(
        document,
        provenance=replace(
            document.provenance,
            source_image_hash=actual_image_artifact or document.provenance.source_image_hash,
            rules_version=validator.rules_version if norm_condition != "unassisted" else None,
            suggestions_version=None if model is None else model.version,
        ),
    )

    actual_session_id = session_id or str(uuid.uuid4())
    session_data = SessionData(
        id=actual_session_id,
        document_id=document.id,
        omr_engine=document.provenance.omr_engine,
        document=document.to_primitive(),
        image_artifact=actual_image_artifact,
        model_version=document.provenance.model_version,
        status="transcribed",
        owner_id=current_user.id,
        condition=norm_condition,
        test_score_id=test_score_id,
    )

    session_repository.add(
        session_data,
        findings,
        [[NewSuggestion(edit=edit) for edit in edits] for _, edits in suggested],
    )

    return TranscribeResult(
        session_id=actual_session_id,
        document_id=document.id,
        omr_engine=document.provenance.omr_engine,
        findings_count=len(findings),
        condition=norm_condition,
        test_score_id=test_score_id,
    )
