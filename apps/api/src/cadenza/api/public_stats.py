"""`GET /stats/homr-errors`: las cifras de los errores de HOMR, en vivo (#423, ADR-0073).

La API no calcula nada: lee los grupos que el servicio `stats` (plano offline) dejó en
`public_stats` (y el detalle de cada partitura de un corpus, en `public_stats_scores`) y los
publica solo con los campos de su esquema. Una fila de otro formato o que no
valida se queda fuera y se anota. La respuesta se guarda en memoria `stats_cache_seconds` y lleva
`Cache-Control` y `ETag`, así que las visitas a la portada apenas llegan a la base.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from cadenza.application import (
    MIN_PUBLIC_SESSIONS,
    PUBLIC_STATS_FORMAT_VERSION,
    PublicStatsGroup,
    PublicStatsImage,
    PublicStatsRepository,
    PublicStatsScore,
)
from pydantic import ValidationError

from .schemas import HomrErrorScoreRead, HomrErrorStatsGroupRead, HomrErrorStatsRead

logger = logging.getLogger("cadenza.api.public_stats")

CACHE_CONTROL = "public, max-age=60"
"""Para el navegador y cualquier caché por el camino: las cifras cambian cada 5 minutos."""
IMAGE_CACHE_CONTROL = "public, max-age=86400"
"""La imagen de una partitura de un corpus no cambia: solo con otro archivo del corpus."""
IMAGE_TYPES = frozenset({"image/png", "image/jpeg"})
CORPUS_ONLY = frozenset({"examples", "example_keys", "bars", "history"})
"""Lo que solo llevan los grupos de corpus: los ejemplos con su compás dibujado y el historial."""


def build_stats(groups: Sequence[PublicStatsGroup]) -> HomrErrorStatsRead:
    """La respuesta con los grupos guardados que se pueden publicar."""
    published: list[HomrErrorStatsGroupRead] = []
    live: list[HomrErrorStatsGroupRead] = []
    for group in groups:
        stats = group.stats
        if (
            stats is not None
            and group.source == "cadenza"
            and group.sessions < max(group.min_sessions, MIN_PUBLIC_SESSIONS)
        ):
            # Quien calcula ya lo aplica; si una fila lo incumple, no se publica igual.
            logger.warning("public_stats_group_unpublished id=%s reason=min_sessions", group.id)
            stats = None
        if stats is not None and group.source == "cadenza":
            # Los grupos de Cadenza nunca llevan ejemplos (ADR-0073, enmienda de #424): solo los
            # corpus públicos. Si una fila los trajera, no se publican.
            stats = {k: v for k, v in stats.items() if k not in CORPUS_ONLY}
        if group.format_version != PUBLIC_STATS_FORMAT_VERSION:
            logger.warning(
                "public_stats_group_skipped id=%s reason=format_version=%s",
                group.id,
                group.format_version,
            )
            continue
        try:
            item = HomrErrorStatsGroupRead.model_validate(
                {
                    "id": group.id,
                    "source": group.source,
                    "computed_at": group.computed_at,
                    "min_sessions": group.min_sessions,
                    "published": stats is not None,
                    # Por debajo del mínimo no se dice ni cuántas sesiones tiene.
                    "sessions": group.sessions if stats is not None else None,
                    "stats": stats,
                }
            )
        except ValidationError as exc:
            logger.warning(
                "public_stats_group_skipped id=%s reason=invalid errors=%d",
                group.id,
                exc.error_count(),
            )
            continue
        published.append(item)
        if item.source == "cadenza":
            live.append(item)
    return HomrErrorStatsRead(
        computed_at=max((g.computed_at for g in live), default=None), groups=published
    )


@dataclass(frozen=True, slots=True)
class StatsResponse:
    body: bytes
    etag: str


def _response(body: bytes) -> StatsResponse:
    return StatsResponse(body=body, etag=_etag(body))


def _etag(body: bytes) -> str:
    return f'"{hashlib.sha256(body).hexdigest()[:32]}"'


@dataclass(frozen=True, slots=True)
class ImageResponse:
    body: bytes
    media_type: str
    etag: str


def render_image(
    score: PublicStatsScore | None, image: PublicStatsImage | None
) -> ImageResponse | None:
    """La imagen de una partitura, solo si su detalle se publica y es una imagen de verdad."""
    if render_score(score) is None or image is None:
        return None
    if image.media_type not in IMAGE_TYPES:
        logger.warning("public_stats_image_skipped type=%s", image.media_type)
        return None
    return ImageResponse(body=image.content, media_type=image.media_type, etag=_etag(image.content))


def render(groups: Sequence[PublicStatsGroup]) -> StatsResponse:
    return _response(build_stats(groups).model_dump_json().encode("utf-8"))


def render_score(score: PublicStatsScore | None) -> StatsResponse | None:
    """El detalle de una partitura de un corpus, o None si no se publica: no está, es de un grupo
    de Cadenza, de otro formato o no valida."""
    if score is None:
        return None
    reason = None
    if score.source != "corpus":
        # Quien calcula nunca lo escribe; si una fila lo trajera, no se publica igual.
        reason = f"source={score.source}"
    elif score.format_version != PUBLIC_STATS_FORMAT_VERSION:
        reason = f"format_version={score.format_version}"
    if reason is None:
        try:
            item = HomrErrorScoreRead.model_validate(
                {
                    **score.detail,
                    "group_id": score.group_id,
                    "id": score.score_id,
                    "computed_at": score.computed_at,
                }
            )
        except ValidationError as exc:
            reason = f"invalid errors={exc.error_count()}"
        else:
            return _response(item.model_dump_json().encode("utf-8"))
    logger.warning("public_stats_score_skipped group=%s reason=%s", score.group_id, reason)
    return None


def etag_matches(if_none_match: str | None, etag: str) -> bool:
    """Si `If-None-Match` nombra este ETag (débil o fuerte) o es `*`."""
    if not if_none_match:
        return False
    tags = {tag.strip().removeprefix("W/") for tag in if_none_match.split(",")}
    return "*" in tags or etag in tags


class StatsCache:
    """La última respuesta, hasta `seconds` segundos del reloj monótono."""

    def __init__(self, seconds: int) -> None:
        self._seconds = seconds
        self._lock = threading.Lock()
        self._entry: tuple[float, StatsResponse] | None = None

    def get(
        self,
        repository: Callable[[], PublicStatsRepository],
        monotonic: Callable[[], float],
    ) -> StatsResponse:
        now = monotonic()
        with self._lock:
            entry = self._entry
        if entry is not None and now < entry[0]:
            return entry[1]
        response = render(repository().list())
        if self._seconds > 0:
            with self._lock:
                self._entry = (now + self._seconds, response)
        return response
