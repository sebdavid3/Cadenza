"""Puerto de almacén de artefactos direccionado por contenido (ADR-0004)."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

from ..exceptions import ArtifactNotFound


def compute_sha256(content: bytes) -> str:
    """Calcula el digest SHA-256 en hexadecimal de un contenido binario."""
    return hashlib.sha256(content).hexdigest()


class ArtifactStore(ABC):
    """Puerto para almacenamiento de binarios direccionados por hash sha256."""

    @abstractmethod
    def put(self, content: bytes, kind: str, media_type: str | None = None) -> str:
        """Almacena el contenido binario y retorna su identificador sha256.

        Debe ser idempotente: si el contenido ya existe, no debe fallar ni duplicar almacenamiento.
        """

    @abstractmethod
    def get(self, sha256: str) -> bytes:
        """Recupera el contenido binario correspondiente al sha256.

        Lanza ArtifactNotFound si no existe.
        """

    @abstractmethod
    def exists(self, sha256: str) -> bool:
        """Indica si el artefacto con el sha256 dado existe en el almacén."""


class InMemoryArtifactStore(ArtifactStore):
    """Adaptador de ArtifactStore en memoria, para pruebas unitarias."""

    def __init__(self) -> None:
        self._storage: dict[str, bytes] = {}
        self._kinds: dict[str, str] = {}
        self._media_types: dict[str, str | None] = {}

    def put(self, content: bytes, kind: str, media_type: str | None = None) -> str:
        sha256 = compute_sha256(content)
        if sha256 not in self._storage:
            self._storage[sha256] = content
            self._kinds[sha256] = kind
            self._media_types[sha256] = media_type
        return sha256

    def get(self, sha256: str) -> bytes:
        if sha256 not in self._storage:
            raise ArtifactNotFound(sha256)
        return self._storage[sha256]

    def exists(self, sha256: str) -> bool:
        return sha256 in self._storage
