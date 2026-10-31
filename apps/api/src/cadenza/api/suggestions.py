"""Carga de la capa de sugerencias al arrancar la API (ADR-0036 §8, §12).

La API carga la versión promovida del registro de la capa, comprueba el `sha256` de su
artefacto y su `feature_version` frente a la del código, y la inyecta en los casos de uso.
No importa código de entrenamiento: el artefacto se lee con `cadenza.validation.learned`.
Si algo no cuadra, valida sin capa y lo registra en el log.
"""

from __future__ import annotations

import logging

from cadenza.application import ArtifactNotFound, ArtifactStore, SuggestionModel
from cadenza.persistence import (
    FilesystemArtifactStore,
    SessionFactory,
    SqlAlchemySuggestionModelRegistry,
)
from cadenza.validation.learned import (
    FEATURE_VERSION,
    MODEL_TYPE,
    FrequencyBackoffModel,
    InvalidSuggestionArtifact,
)
from sqlalchemy.exc import SQLAlchemyError

from .settings import Settings

logger = logging.getLogger("cadenza.api.suggestions")


def load_suggestion_model(
    session_factory: SessionFactory,
    settings: Settings,
    artifact_store: ArtifactStore | None = None,
) -> SuggestionModel | None:
    """La capa promovida, o None si el interruptor está apagado o no se puede usar."""
    if not settings.suggestions_enabled:
        logger.info("suggestion_layer enabled=False")
        return None
    with session_factory() as db:
        try:
            active = SqlAlchemySuggestionModelRegistry(db).active()
        except SQLAlchemyError as exc:
            logger.warning("suggestion_layer unavailable reason=registry_error error=%s", exc)
            return None
        if active is None:
            logger.warning("suggestion_layer unavailable reason=no_promoted_version")
            return None
        if active.model_type != MODEL_TYPE:
            logger.warning(
                "suggestion_layer unavailable reason=model_type version=%s model_type=%s",
                active.version,
                active.model_type,
            )
            return None
        if active.feature_version != FEATURE_VERSION:
            logger.warning(
                "suggestion_layer unavailable reason=feature_version version=%s "
                "registered=%s code=%s",
                active.version,
                active.feature_version,
                FEATURE_VERSION,
            )
            return None
        store = artifact_store or FilesystemArtifactStore(settings.artifacts_dir, session=db)
        try:
            content = store.get(active.artifact_hash)
        except (ArtifactNotFound, OSError) as exc:
            logger.warning(
                "suggestion_layer unavailable reason=artifact_missing version=%s error=%s",
                active.version,
                exc,
            )
            return None
    try:
        model = FrequencyBackoffModel.from_bytes(
            content, version=active.version, expected_sha256=active.artifact_hash
        )
    except InvalidSuggestionArtifact as exc:
        logger.warning(
            "suggestion_layer unavailable reason=invalid_artifact version=%s error=%s",
            active.version,
            exc,
        )
        return None
    logger.info(
        "suggestion_layer loaded version=%s feature_version=%s families=%s",
        active.version,
        FEATURE_VERSION,
        ",".join(model.active_families()) or "-",
    )
    return model
