"""Puerto de las transcripciones sin cuenta de la portada (#278, ADR-0054).

Una transcripción sin cuenta no es una sesión: no tiene dueño, ni log, ni hallazgos guardados.
Guarda el documento que leyó HOMR, la imagen y los datos de la partitura hasta que caduca o
hasta que alguien que entra la reclama con su token, que solo se guarda resumido (SHA-256).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from cadenza.domain import ScoreMetadata


@dataclass(frozen=True)
class PreviewData:
    """Una transcripción sin cuenta, tal como se guarda."""

    id: str
    token_hash: str
    document: dict[str, Any]
    image: bytes
    image_media_type: str
    created_at: datetime
    expires_at: datetime
    metadata: ScoreMetadata = field(default_factory=ScoreMetadata)
    source_filename: str | None = None


class PreviewRepository(ABC):
    """Guarda las transcripciones sin cuenta y las borra al reclamarlas o al caducar."""

    @abstractmethod
    def add(self, preview: PreviewData) -> None:
        """Guarda una transcripción sin cuenta nueva."""

    @abstractmethod
    def get(self, preview_id: str) -> PreviewData | None:
        """La transcripción `preview_id`, caducada o no; None si no existe."""

    @abstractmethod
    def delete(self, preview_id: str) -> bool:
        """La borra; False si ya no existía (otra petición la reclamó antes)."""

    @abstractmethod
    def count_active(self, now: datetime) -> int:
        """Cuántas siguen vigentes en `now`."""

    @abstractmethod
    def purge_expired(self, now: datetime) -> int:
        """Borra las caducadas en `now`, con su imagen; devuelve cuántas."""

    @abstractmethod
    def purge_all(self) -> int:
        """Las borra todas, vigentes o no; devuelve cuántas (al arrancar con el interruptor
        apagado, ADR-0054 §3)."""

    @abstractmethod
    def next_expiry(self, now: datetime) -> datetime | None:
        """Cuándo caduca la vigente más antigua; None si no hay ninguna."""


class InMemoryPreviewRepository(PreviewRepository):
    """Implementación en memoria, para pruebas unitarias."""

    def __init__(self) -> None:
        self.previews: dict[str, PreviewData] = {}

    def add(self, preview: PreviewData) -> None:
        self.previews[preview.id] = preview

    def get(self, preview_id: str) -> PreviewData | None:
        return self.previews.get(preview_id)

    def delete(self, preview_id: str) -> bool:
        return self.previews.pop(preview_id, None) is not None

    def count_active(self, now: datetime) -> int:
        return sum(1 for preview in self.previews.values() if preview.expires_at > now)

    def purge_expired(self, now: datetime) -> int:
        expired = [pid for pid, preview in self.previews.items() if preview.expires_at <= now]
        for pid in expired:
            del self.previews[pid]
        return len(expired)

    def purge_all(self) -> int:
        count = len(self.previews)
        self.previews.clear()
        return count

    def next_expiry(self, now: datetime) -> datetime | None:
        active = [
            preview.expires_at for preview in self.previews.values() if preview.expires_at > now
        ]
        return min(active, default=None)
