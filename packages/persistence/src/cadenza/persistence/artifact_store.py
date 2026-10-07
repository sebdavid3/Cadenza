"""Adaptador FilesystemArtifactStore con direccionamiento por contenido sha256 (ADR-0004)."""

from __future__ import annotations

from pathlib import Path

from cadenza.application import ArtifactNotFound, ArtifactStore, compute_sha256
from sqlalchemy.orm import Session as DbSession

from .models import ArtifactRecord

_DEFAULT_MEDIA_TYPES: dict[str, str] = {
    "image": "image/png",
    "score_xml": "application/vnd.recordare.musicxml+xml",
    "musicxml": "application/vnd.recordare.musicxml+xml",
    "midi": "audio/midi",
    "onnx_model": "application/octet-stream",
    "onnx": "application/octet-stream",
}


class FilesystemArtifactStore(ArtifactStore):
    """Almacén de artefactos en el sistema de archivos con índice en PostgreSQL/SQLite.

    Estructura en disco: ``<root_dir>/sha256/ab/cd/<hash>``
    Garantiza idempotencia y deduplicación natural tanto en disco como en base de datos.
    """

    def __init__(self, root_dir: Path | str, session: DbSession | None = None) -> None:
        self._root_dir = Path(root_dir)
        self._session = session

    @property
    def root_dir(self) -> Path:
        return self._root_dir

    def _relative_path(self, sha256: str) -> Path:
        return Path("sha256") / sha256[:2] / sha256[2:4] / sha256

    def _absolute_path(self, sha256: str) -> Path:
        return self._root_dir / self._relative_path(sha256)

    def put(self, content: bytes, kind: str, media_type: str | None = None) -> str:
        sha256 = compute_sha256(content)
        rel_path = self._relative_path(sha256)
        abs_path = self._root_dir / rel_path

        # 1. Escritura idempotente en disco
        if not abs_path.is_file():
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            # Escritura atómica mediante archivo temporal adyacente
            temp_path = abs_path.with_name(f".tmp_{sha256}")
            temp_path.write_bytes(content)
            temp_path.replace(abs_path)

        # 2. Registro idempotente en la base de datos (si hay sesión disponible)
        if self._session is not None:
            existing = self._session.get(ArtifactRecord, sha256)
            if existing is None:
                resolved_media = media_type or _DEFAULT_MEDIA_TYPES.get(
                    kind, "application/octet-stream"
                )
                record = ArtifactRecord(
                    sha256=sha256,
                    kind=kind,
                    media_type=resolved_media,
                    size_bytes=len(content),
                    path=rel_path.as_posix(),
                )
                self._session.add(record)
                self._session.flush()

        return sha256

    def get(self, sha256: str) -> bytes:
        abs_path = self._absolute_path(sha256)
        if not abs_path.is_file():
            raise ArtifactNotFound(sha256)
        return abs_path.read_bytes()

    def exists(self, sha256: str) -> bool:
        return self._absolute_path(sha256).is_file()

    def get_record(self, sha256: str) -> ArtifactRecord | None:
        """Consulta el registro relacional en base de datos si la sesión está conectada."""
        if self._session is None:
            return None
        return self._session.get(ArtifactRecord, sha256)
