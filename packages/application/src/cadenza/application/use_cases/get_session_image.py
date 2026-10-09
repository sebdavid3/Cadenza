"""Caso de uso: recuperar la imagen original de una sesión (ADR-0004, ADR-0012, #9)."""

from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import ArtifactNotFound, SessionNotFound
from ..ports.artifact_store import ArtifactStore, detect_image_media_type
from ..ports.session_repository import SessionRepository
from ..user import Role, User


@dataclass(frozen=True)
class SessionImageData:
    """Contenido binario y tipo MIME de la imagen de una sesión."""

    content: bytes
    media_type: str


def get_session_image(
    session_id: str,
    *,
    session_repository: SessionRepository,
    artifact_store: ArtifactStore,
    current_user: User,
) -> SessionImageData:
    """Recupera la imagen de la sesión verificando permisos y presencia en el almacén.

    Aplica la regla de acceso (ADR-0012): un transcriptor solo accede a sus propias
    sesiones (las ajenas responden como inexistentes); un investigador puede leer todas.
    """
    session_data = session_repository.get(session_id)
    if session_data is None:
        raise SessionNotFound(session_id)

    if current_user.role != Role.INVESTIGADOR and session_data.owner_id != current_user.id:
        raise SessionNotFound(session_id)

    if not session_data.image_artifact:
        raise SessionNotFound(session_id)

    try:
        content = artifact_store.get(session_data.image_artifact)
    except ArtifactNotFound:
        raise SessionNotFound(session_id) from None

    media_type = artifact_store.get_media_type(session_data.image_artifact)
    if not media_type:
        media_type = detect_image_media_type(content)

    return SessionImageData(content=content, media_type=media_type)
