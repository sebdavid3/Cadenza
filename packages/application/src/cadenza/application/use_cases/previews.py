"""Casos de uso: transcribir sin cuenta y reclamar la transcripción al entrar (#278, ADR-0054).

Una transcripción sin cuenta guarda lo que leyó HOMR, la imagen y los datos de la partitura en
su propia tabla, sin dueño ni sesión, hasta que caduca. Quien la transcribió recibe un token;
al entrar, lo presenta una sola vez y la transcripción pasa a ser una sesión suya, con el mismo
documento y la misma imagen, sin volver a ejecutar el OMR. El autor lo fija el servidor con la
cuenta que reclama (ADR-0012).
"""

from __future__ import annotations

import hashlib
import hmac
import math
import secrets
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

from cadenza.domain import ScoreDocument, ScoreMetadata, normalize_source_filename
from cadenza.omr import OMREngine
from cadenza.validation import ValidationEngine

from ..exceptions import PreviewCapacityExceeded, PreviewNotFound
from ..ports.artifact_store import ArtifactStore, compute_sha256, detect_image_media_type
from ..ports.preview_repository import PreviewData, PreviewRepository
from ..ports.recognition_stage import RecognitionStage
from ..ports.session_repository import SessionRepository
from ..ports.suggestion_model import SuggestionModel
from ..user import User
from .transcribe_score import TranscribeResult, create_session_from_document

# 32 bytes aleatorios: imposible de adivinar, y aun así solo vale con una cuenta iniciada.
_TOKEN_BYTES = 32
# La sesión que nace al reclamar una transcripción tiene un id que sale del de esta: si se pierde
# la respuesta, el reintento de la misma cuenta encuentra su sesión en vez de un 404 (#278).
_CLAIM_NAMESPACE = uuid.UUID("6f1d6c2e-7a0b-4c55-9f1e-2b8a3c4d5e6f")


def claimed_session_id(preview_id: str) -> str:
    """El id de la sesión que nace al reclamar la transcripción `preview_id`."""
    return str(uuid.uuid5(_CLAIM_NAMESPACE, preview_id))


def hash_claim_token(token: str) -> str:
    """El resumen con el que se guarda el token (el token en claro no se guarda)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PreviewResult:
    """Lo que devuelve una transcripción sin cuenta: lo leído y cómo reclamarlo."""

    preview_id: str
    claim_token: str
    expires_at: datetime
    document: ScoreDocument
    findings_count: int
    metadata: ScoreMetadata
    source_filename: str | None


def ensure_preview_capacity(
    preview_repository: PreviewRepository, *, now: datetime, max_active: int
) -> None:
    """Borra las caducadas y comprueba que cabe otra; si no, `PreviewCapacityExceeded`.

    Limita lo que puede ocupar en la base lo transcrito sin cuenta, venga de las IP que venga.
    """
    preview_repository.purge_expired(now)
    if preview_repository.count_active(now) >= max_active:
        oldest = preview_repository.next_expiry(now)
        wait = 60 if oldest is None else max(1, math.ceil((oldest - now).total_seconds()))
        raise PreviewCapacityExceeded(max_active, retry_after_seconds=wait)


def create_preview(
    image_path: Path,
    *,
    omr_engine: OMREngine,
    validator: ValidationEngine,
    preview_repository: PreviewRepository,
    now: datetime,
    ttl: timedelta,
    metadata: ScoreMetadata | None = None,
    source_filename: str | None = None,
    meter_stage: RecognitionStage | None = None,
) -> PreviewResult:
    """Transcribe la imagen sin cuenta, cuenta los posibles errores y la guarda hasta `ttl`.

    Las reglas corren como en una sesión asistida para decir cuántos posibles errores hay, pero
    no se guardan: al reclamarla se vuelven a evaluar sobre el mismo documento, con la capa de
    sugerencias si está encendida, como en `POST /transcribe`.

    Con `meter_stage`, la etapa del compás corre tras el motor, como en `transcribe_score`
    (ADR-0059): la sesión que se reclama tiene el mismo documento que tendría transcrita con
    cuenta, con la etapa en su procedencia.
    """
    image = image_path.read_bytes()
    document = omr_engine.transcribe(image_path)
    if meter_stage is not None:
        document = meter_stage.apply(document)
    findings = validator.validate(document)
    document = replace(
        document,
        provenance=replace(
            document.provenance,
            source_image_hash=compute_sha256(image),
            rules_version=validator.rules_version,
        ),
    )
    fitted = (metadata or ScoreMetadata()).fitted(len(document.score.parts))
    filename = normalize_source_filename(source_filename)
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    preview = PreviewData(
        id=str(uuid.uuid4()),
        token_hash=hash_claim_token(token),
        document=document.to_primitive(),
        image=image,
        image_media_type=detect_image_media_type(image),
        created_at=now,
        expires_at=now + ttl,
        metadata=fitted,
        source_filename=filename,
    )
    preview_repository.add(preview)
    return PreviewResult(
        preview_id=preview.id,
        claim_token=token,
        expires_at=preview.expires_at,
        document=document,
        findings_count=len(findings),
        metadata=fitted,
        source_filename=filename,
    )


def claim_preview(
    preview_id: str,
    token: str,
    *,
    preview_repository: PreviewRepository,
    session_repository: SessionRepository,
    artifact_store: ArtifactStore,
    validator: ValidationEngine,
    current_user: User,
    now: datetime,
    suggestion_model: SuggestionModel | None = None,
) -> TranscribeResult:
    """Convierte la transcripción sin cuenta en una sesión de `current_user`, una sola vez.

    Una que no existe, que caducó o con otro token responde igual (`PreviewNotFound`): no se
    puede averiguar cuáles existen. La transcripción se borra en la misma transacción en que
    nace la sesión; si dos peticiones la reclaman a la vez, solo una la borra y la otra recibe
    `PreviewNotFound`. Si ya la reclamó esta misma cuenta (se perdió la respuesta), devuelve
    su sesión en vez de un 404: otra cuenta no puede llegar a ella.
    """
    # De paso se borran las caducadas, con su imagen (ADR-0054 §3).
    preview_repository.purge_expired(now)
    preview = preview_repository.get(preview_id)
    if preview is None:
        claimed = session_repository.get(claimed_session_id(preview_id))
        if claimed is not None and claimed.owner_id == current_user.id:
            return TranscribeResult(
                session_id=claimed.id,
                document_id=claimed.document_id,
                omr_engine=claimed.omr_engine,
                findings_count=len(session_repository.list_findings(claimed.id)),
                condition=claimed.condition,
                test_score_id=claimed.test_score_id,
            )
    if (
        preview is None
        or preview.expires_at <= now
        or not hmac.compare_digest(preview.token_hash, hash_claim_token(token))
    ):
        raise PreviewNotFound(preview_id)
    if not preview_repository.delete(preview_id):
        raise PreviewNotFound(preview_id)

    image_artifact = artifact_store.put(
        preview.image, kind="image", media_type=preview.image_media_type
    )
    return create_session_from_document(
        ScoreDocument.from_primitive(preview.document),
        validator=validator,
        session_repository=session_repository,
        current_user=current_user,
        image_artifact=image_artifact,
        session_id=claimed_session_id(preview_id),
        condition="assisted",
        suggestion_model=suggestion_model,
        metadata=preview.metadata,
        source_filename=preview.source_filename,
    )
