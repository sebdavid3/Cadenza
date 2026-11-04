"""`POST /transcribe` no usa el nombre subido para el archivo temporal (#295).

HOMR lee la imagen con `cv2.imread`, que en Windows no abre rutas con caracteres fuera de
ASCII: «Íncipit de prueba.png» acababa en 422. Un nombre de solo espacios daba 500 en Windows,
porque el archivo temporal era el propio directorio. El archivo temporal lleva ahora un nombre
propio y solo la extensión subida, comprobada contra el tipo real de la imagen.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cadenza.api import Settings, create_app
from cadenza.application import Role, User
from cadenza.domain import ScoreDocument
from cadenza.omr import OMRTranscriptionError
from cadenza.omr.testing import FakeOMREngine
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi.testclient import TestClient

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
)
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
ACCENTED_NAME = "Íncipit de prueba.png"


class RecordingOMREngine(FakeOMREngine):
    """Doble que guarda la ruta que recibe y, si se pide, la lee como HOMR (`cv2.imread`)."""

    def __init__(self, *, read_with_cv2: bool = False) -> None:
        super().__init__()
        self.paths: list[Path] = []
        self._read_with_cv2 = read_with_cv2

    def transcribe(self, image_path: Path) -> ScoreDocument:
        self.paths.append(image_path)
        if self._read_with_cv2:
            import cv2

            if cv2.imread(str(image_path)) is None:
                raise OMRTranscriptionError("The file format is not supported")
        return super().transcribe(image_path)


def _client(tmp_path: Path, engine: FakeOMREngine) -> TestClient:
    db_engine = create_memory_engine()
    create_schema(db_engine)
    session_factory = create_session_factory(db_engine)
    with session_factory() as db:
        SqlAlchemyUserRepository(db).add(
            User(id="u1", username="transcriptor1", password_hash="x", role=Role.TRANSCRIPTOR)
        )
        db.commit()
    app = create_app(
        session_factory,
        omr_engine=engine,
        settings=Settings(
            auth_secret_key="secret-key-at-least-32-bytes-long-for-testing",
            artifacts_dir=tmp_path / "artifacts",
        ),
    )
    token = app.state.token_service.create_access_token(user_id="u1", role=Role.TRANSCRIPTOR)
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def _upload(client: TestClient, name: str, content: bytes, media_type: str) -> int:
    response = client.post("/transcribe", files={"file": (name, content, media_type)})
    status_code: int = response.status_code
    return status_code


def test_accented_name_does_not_reach_the_temporary_file(tmp_path: Path) -> None:
    engine = RecordingOMREngine()
    client = _client(tmp_path, engine)

    assert _upload(client, ACCENTED_NAME, PNG_BYTES, "image/png") == 201

    (seen,) = engine.paths
    assert seen.name.isascii()
    assert "cipit" not in seen.name
    assert seen.suffix == ".png"


def test_accented_name_is_readable_by_opencv(tmp_path: Path) -> None:
    """Reproduce el 422: `cv2.imread` no abre en Windows una ruta con «Í»."""

    cv2 = pytest.importorskip("cv2")
    numpy = pytest.importorskip("numpy")
    ok, encoded = cv2.imencode(".png", numpy.full((8, 8, 3), 255, dtype=numpy.uint8))
    assert ok
    engine = RecordingOMREngine(read_with_cv2=True)
    client = _client(tmp_path, engine)

    assert _upload(client, ACCENTED_NAME, encoded.tobytes(), "image/png") == 201


def test_blank_name_is_accepted(tmp_path: Path) -> None:
    engine = RecordingOMREngine()
    client = _client(tmp_path, engine)

    assert _upload(client, "   ", PNG_BYTES, "image/png") == 201

    (seen,) = engine.paths
    assert seen.name.strip() == seen.name
    assert seen.suffix == ".png"


@pytest.mark.parametrize(
    ("name", "content", "media_type", "suffix"),
    [
        # La extensión subida se conserva si corresponde al tipo real de la imagen.
        ("partitura.JPEG", JPEG_BYTES, "image/jpeg", ".jpeg"),
        ("partitura.jpg", JPEG_BYTES, "image/jpeg", ".jpg"),
        # Si no corresponde, o no la hay, se usa la del tipo real.
        ("partitura.jpg", PNG_BYTES, "image/png", ".png"),
        ("partitura.exe", PNG_BYTES, "image/png", ".png"),
        ("partitura", JPEG_BYTES, "image/jpeg", ".jpg"),
        ("partitura.p ng", PNG_BYTES, "image/png", ".png"),
    ],
    ids=["jpeg-mayusculas", "jpg", "jpg-con-png", "exe", "sin-extension", "con-espacio"],
)
def test_temporary_suffix_is_checked_against_the_content(
    tmp_path: Path, name: str, content: bytes, media_type: str, suffix: str
) -> None:
    engine = RecordingOMREngine()
    client = _client(tmp_path, engine)

    assert _upload(client, name, content, media_type) == 201

    (seen,) = engine.paths
    assert seen.suffix == suffix
    assert "partitura" not in seen.name
