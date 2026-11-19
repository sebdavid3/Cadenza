"""Las cifras públicas de los errores de HOMR (#423, ADR-0073).

Las calcula el plano offline (el servicio `stats`, `ml/public_stats.py`) y las guarda por grupo;
la API solo las lee. Los dos planos se comunican por estos datos persistidos (CLAUDE.md §10.7).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

PUBLIC_STATS_FORMAT_VERSION: Final = 1
"""La versión de lo que lleva `PublicStatsGroup.stats`. La API no publica otra."""


@dataclass(frozen=True, slots=True)
class PublicStatsGroup:
    """Las cifras de conjunto de un grupo de sesiones (`cadenza`, `pruebas`) o de un corpus.

    `source` es `cadenza` (en vivo) o `corpus` (precalculado, con el sha256 de su archivo en
    `source_sha256`). `stats` es None si el grupo no llega a `min_sessions` sesiones: entonces
    no se publica, ni siquiera cuántas tiene.
    """

    id: str
    source: str
    computed_at: datetime
    format_version: int
    min_sessions: int
    sessions: int
    stats: Mapping[str, Any] | None
    source_sha256: str | None = None

    @property
    def published(self) -> bool:
        return self.stats is not None


def _order(group: PublicStatsGroup) -> tuple[str, str]:
    return (group.source, group.id)


class PublicStatsRepository(ABC):
    """Los grupos guardados; los de Cadenza primero (`cadenza` < `corpus`) y, dentro, por id."""

    @abstractmethod
    def list(self) -> tuple[PublicStatsGroup, ...]:
        """Todos los grupos guardados."""

    @abstractmethod
    def replace(self, source: str, groups: Sequence[PublicStatsGroup]) -> None:
        """Sustituye los grupos de `source` por `groups`: los que no vienen se borran."""


class InMemoryPublicStatsRepository(PublicStatsRepository):
    """Repositorio en memoria para las pruebas."""

    def __init__(self) -> None:
        self._groups: dict[str, PublicStatsGroup] = {}

    def list(self) -> tuple[PublicStatsGroup, ...]:
        return tuple(sorted(self._groups.values(), key=_order))

    def replace(self, source: str, groups: Sequence[PublicStatsGroup]) -> None:
        self._groups = {k: g for k, g in self._groups.items() if g.source != source}
        self._groups.update({g.id: g for g in groups})
