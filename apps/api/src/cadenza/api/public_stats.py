"""`GET /stats/homr-errors`: las cifras de los errores de HOMR, en vivo (#423, ADR-0073).

La API no calcula nada: lee los grupos que el servicio `stats` (plano offline) dejó en
`public_stats` y los publica solo con los campos de su esquema. Una fila de otro formato o que no
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
    PublicStatsRepository,
)
from pydantic import ValidationError

from .schemas import HomrErrorStatsGroupRead, HomrErrorStatsRead

logger = logging.getLogger("cadenza.api.public_stats")

CACHE_CONTROL = "public, max-age=60"
CORPUS_ONLY = frozenset({"examples", "example_keys", "bars"})
"""Lo que solo llevan los grupos de corpus: los ejemplos con su compás dibujado."""
"""Para el navegador y cualquier caché por el camino: las cifras cambian cada 5 minutos."""


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


def render(groups: Sequence[PublicStatsGroup]) -> StatsResponse:
    body = build_stats(groups).model_dump_json().encode("utf-8")
    return StatsResponse(body=body, etag=f'"{hashlib.sha256(body).hexdigest()[:32]}"')


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
