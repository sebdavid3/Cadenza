"""Puerto de almacén de artefactos direccionado por contenido (ADR-0004)."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

from ..exceptions import ArtifactNotFound


def compute_sha256(content: bytes) -> str:
    """Calcula el digest SHA-256 en hexadecimal de un contenido binario."""
    return hashlib.sha256(content).hexdigest()


def is_image_content(content: bytes) -> bool:
    """Verifica si el contenido binario corresponde a una firma de imagen válida."""
    if len(content) < 4:
        return False
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if content.startswith(b"\xff\xd8\xff"):
        return True
    if content.startswith((b"GIF87a", b"GIF89a")):
        return True
    if content.startswith(b"BM"):
        return True
    if content.startswith((b"II*\x00", b"MM\x00*")):
        return True
    return bool(content.startswith(b"RIFF") and len(content) >= 12 and content[8:12] == b"WEBP")


def detect_image_media_type(content: bytes) -> str:
    """Detecta el tipo MIME de una imagen a partir de sus magic bytes."""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if content.startswith(b"BM"):
        return "image/bmp"
    if content.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if content.startswith(b"RIFF") and len(content) >= 12 and content[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


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

    def get_media_type(self, sha256: str) -> str | None:
        """Recupera el tipo MIME registrado para el artefacto, o None si no se conoce."""
        return None


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

    def get_media_type(self, sha256: str) -> str | None:
        return self._media_types.get(sha256)
