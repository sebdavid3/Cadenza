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

PUBLIC_STATS_FORMAT_VERSION: Final = 4
"""La versión de lo que lleva `PublicStatsGroup.stats` (y `PublicStatsScore.detail`). La API no
publica otra. La 2 añade los ejemplos de los corpus; la 3, su historial con el detalle de cada
partitura (#424), y la 4, las barras de compás mal leídas, con la alineación del íncipit entero
(#466, ADR-0075): al desplegar una nueva, las filas de la anterior no se publican hasta el
siguiente cálculo."""
MIN_PUBLIC_SESSIONS: Final = 5
"""Sesiones que necesita un grupo de Cadenza para publicarse (ADR-0073 §5). Lo aplica quien
calcula y lo vuelve a comprobar la API."""
MIN_PUBLIC_ACCOUNTS: Final = 3
"""Cuentas distintas que necesita un grupo de Cadenza: cinco sesiones de una sola persona serían
sus cifras, no unas de conjunto (ADR-0073 §5)."""


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


@dataclass(frozen=True, slots=True)
class PublicStatsScore:
    """El detalle de una partitura del historial de un corpus (ADR-0073, enmienda de #424): sus
    cifras y sus ejemplos con el compás dibujado. Nunca de una partitura de Cadenza.

    `source` es el del grupo al que pertenece, para que quien lo publique lo compruebe.
    """

    group_id: str
    score_id: str
    source: str
    computed_at: datetime
    format_version: int
    detail: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class PublicStatsImage:
    """La imagen de una partitura de un corpus público (PrIMuS: la del íncipit; Camera-PrIMuS:
    su versión distorsionada), que se enseña con sus ejemplos (ADR-0073, enmienda de #424)."""

    media_type: str
    content: bytes


def _order(group: PublicStatsGroup) -> tuple[str, str]:
    return (group.source, group.id)


class PublicStatsRepository(ABC):
    """Los grupos guardados; los de Cadenza primero (`cadenza` < `corpus`) y, dentro, por id."""

    @abstractmethod
    def list(self) -> tuple[PublicStatsGroup, ...]:
        """Todos los grupos guardados."""

    @abstractmethod
    def replace(self, source: str, groups: Sequence[PublicStatsGroup]) -> None:
        """Sustituye los grupos de `source` por `groups`: los que no vienen se borran, con el
        detalle de sus partituras."""

    @abstractmethod
    def replace_scores(
        self,
        group: PublicStatsGroup,
        scores: Mapping[str, Mapping[str, Any]],
        images: Mapping[str, PublicStatsImage] | None = None,
    ) -> None:
        """Sustituye el detalle de las partituras de `group` (por su íncipit) por `scores`, con
        la imagen de las que la tienen."""

    @abstractmethod
    def get_score(self, group_id: str, score_id: str) -> PublicStatsScore | None:
        """El detalle de una partitura, si su grupo sigue guardado."""

    @abstractmethod
    def get_image(self, group_id: str, score_id: str) -> PublicStatsImage | None:
        """La imagen de una partitura, si la tiene y su grupo sigue guardado."""


class InMemoryPublicStatsRepository(PublicStatsRepository):
    """Repositorio en memoria para las pruebas."""

    def __init__(self) -> None:
        self._groups: dict[str, PublicStatsGroup] = {}
        self._scores: dict[tuple[str, str], tuple[PublicStatsGroup, Mapping[str, Any]]] = {}
        self._images: dict[tuple[str, str], PublicStatsImage] = {}

    def list(self) -> tuple[PublicStatsGroup, ...]:
        return tuple(sorted(self._groups.values(), key=_order))

    def replace(self, source: str, groups: Sequence[PublicStatsGroup]) -> None:
        if any(group.source != source for group in groups):
            raise ValueError(f"todos los grupos han de ser de {source}")
        self._groups = {k: g for k, g in self._groups.items() if g.source != source}
        self._groups.update({g.id: g for g in groups})
        self._scores = {k: v for k, v in self._scores.items() if k[0] in self._groups}
        self._images = {k: v for k, v in self._images.items() if k[0] in self._groups}

    def replace_scores(
        self,
        group: PublicStatsGroup,
        scores: Mapping[str, Mapping[str, Any]],
        images: Mapping[str, PublicStatsImage] | None = None,
    ) -> None:
        self._scores = {k: v for k, v in self._scores.items() if k[0] != group.id}
        self._scores.update({(group.id, sid): (group, d) for sid, d in scores.items()})
        self._images = {k: v for k, v in self._images.items() if k[0] != group.id}
        self._images.update(
            {(group.id, sid): image for sid, image in (images or {}).items() if sid in scores}
        )

    def get_image(self, group_id: str, score_id: str) -> PublicStatsImage | None:
        if group_id not in self._groups:
            return None
        return self._images.get((group_id, score_id))

    def get_score(self, group_id: str, score_id: str) -> PublicStatsScore | None:
        found = self._scores.get((group_id, score_id))
        stored = self._groups.get(group_id)
        if found is None or stored is None:
            return None
        group, detail = found
        return PublicStatsScore(
            group_id=group_id,
            score_id=score_id,
            source=stored.source,
            computed_at=group.computed_at,
            format_version=group.format_version,
            detail=detail,
        )
