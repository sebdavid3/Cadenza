"""Pruebas de la API para persistencia y descarga de imágenes de sesión (Issue #9, ADR-0012)."""

from __future__ import annotations

from pathlib import Path

from cadenza.api import Settings, create_app
from cadenza.application import (
    Role,
    User,
    compute_sha256,
)
from cadenza.omr import FakeOMREngine
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
PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"


def _build_test_app(
    tmp_path: Path,
    max_upload_size: int = 20 * 1024 * 1024,
) -> tuple[TestClient, dict[str, str]]:
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as db:
        user_repo = SqlAlchemyUserRepository(db)
        user_repo.add(
            User(
                id="user-t1",
                username="transcriptor1",
                password_hash="test",
                role=Role.TRANSCRIPTOR,
                active=True,
            )
        )
        user_repo.add(
            User(
                id="user-t2",
                username="transcriptor2",
                password_hash="test",
                role=Role.TRANSCRIPTOR,
                active=True,
            )
        )
        user_repo.add(
            User(
                id="user-inv",
                username="investigador1",
                password_hash="test",
                role=Role.INVESTIGADOR,
                active=True,
            )
        )
        db.commit()

    settings = Settings(
        auth_secret_key="secret-key-at-least-32-bytes-long-for-testing",
        artifacts_dir=tmp_path / "artifacts",
        max_upload_size_bytes=max_upload_size,
    )
    app = create_app(
        session_factory,
        omr_engine=FakeOMREngine(),
        settings=settings,
    )

    t1_token = app.state.token_service.create_access_token(
        user_id="user-t1", role=Role.TRANSCRIPTOR
    )
    t2_token = app.state.token_service.create_access_token(
        user_id="user-t2", role=Role.TRANSCRIPTOR
    )
    inv_token = app.state.token_service.create_access_token(
        user_id="user-inv", role=Role.INVESTIGADOR
    )

    client = TestClient(app)
    tokens = {
        "t1": t1_token,
        "t2": t2_token,
        "inv": inv_token,
    }
    return client, tokens


def test_transcribe_and_get_session_image(tmp_path: Path) -> None:
    client, tokens = _build_test_app(tmp_path)
    client.headers["Authorization"] = f"Bearer {tokens['t1']}"

    # 1. Subida exitosa de PNG
    upload_resp = client.post(
        "/transcribe",
        files={"file": ("score.png", PNG_BYTES, "image/png")},
    )
    assert upload_resp.status_code == 201
    session_id = upload_resp.json()["session_id"]
    expected_sha256 = compute_sha256(PNG_BYTES)

    # 2. Verificar detalle de sesión
    session_detail = client.get(f"/sessions/{session_id}").json()
    assert session_detail["image_artifact"] == expected_sha256
    # Provenance.source_image_hash coincide con el sha256 del artefacto
    assert session_detail["document"]["provenance"]["source_image_hash"] == expected_sha256

    # 3. GET /sessions/{id}/image devuelve la imagen con media_type correcto
    img_resp = client.get(f"/sessions/{session_id}/image")
    assert img_resp.status_code == 200
    assert img_resp.headers["content-type"].startswith("image/png")
    assert img_resp.content == PNG_BYTES


def test_get_session_image_permissions_adr0012(tmp_path: Path) -> None:
    client, tokens = _build_test_app(tmp_path)

    # Transcriptor 1 crea una sesión
    client.headers["Authorization"] = f"Bearer {tokens['t1']}"
    resp = client.post(
        "/transcribe",
        files={"file": ("score.png", PNG_BYTES, "image/png")},
    )
    session_id = resp.json()["session_id"]

    # Transcriptor 2 intenta descargar la imagen de la sesión ajena -> 404 (no revela existencia)
    client.headers["Authorization"] = f"Bearer {tokens['t2']}"
    resp_t2 = client.get(f"/sessions/{session_id}/image")
    assert resp_t2.status_code == 404

    # Investigador descarga la imagen de cualquier sesión -> 200
    client.headers["Authorization"] = f"Bearer {tokens['inv']}"
    resp_inv = client.get(f"/sessions/{session_id}/image")
    assert resp_inv.status_code == 200
    assert resp_inv.content == PNG_BYTES

    # Sesión inexistente -> 404
    resp_missing = client.get("/sessions/non-existent-session/image")
    assert resp_missing.status_code == 404


def test_deduplication_on_repeated_upload(tmp_path: Path) -> None:
    client, tokens = _build_test_app(tmp_path)
    client.headers["Authorization"] = f"Bearer {tokens['t1']}"

    # Primera subida
    resp1 = client.post(
        "/transcribe",
        files={"file": ("score1.png", PNG_BYTES, "image/png")},
    )
    assert resp1.status_code == 201
    s1_id = resp1.json()["session_id"]

    # Segunda subida con el mismo contenido
    resp2 = client.post(
        "/transcribe",
        files={"file": ("score2.png", PNG_BYTES, "image/png")},
    )
    assert resp2.status_code == 201
    s2_id = resp2.json()["session_id"]

    assert s1_id != s2_id

    d1 = client.get(f"/sessions/{s1_id}").json()
    d2 = client.get(f"/sessions/{s2_id}").json()

    assert d1["image_artifact"] == d2["image_artifact"]
    expected_sha256 = compute_sha256(PNG_BYTES)
    assert d1["image_artifact"] == expected_sha256

    # Verificar que en el sistema de archivos sólo existe un archivo para ese hash
    store_file = (
        tmp_path
        / "artifacts"
        / "sha256"
        / expected_sha256[:2]
        / expected_sha256[2:4]
        / expected_sha256
    )
    assert store_file.is_file()


def test_reject_non_image_pdf_returns_415(tmp_path: Path) -> None:
    client, tokens = _build_test_app(tmp_path)
    client.headers["Authorization"] = f"Bearer {tokens['t1']}"

    # Declarado como PDF
    resp1 = client.post(
        "/transcribe",
        files={"file": ("score.pdf", PDF_BYTES, "application/pdf")},
    )
    assert resp1.status_code == 415

    # Con extensión o cabecera PDF disfrazada como PNG
    resp2 = client.post(
        "/transcribe",
        files={"file": ("disguised.png", PDF_BYTES, "image/png")},
    )
    assert resp2.status_code == 415

    # Texto plano
    resp3 = client.post(
        "/transcribe",
        files={"file": ("text.txt", b"plain text score", "text/plain")},
    )
    assert resp3.status_code == 415


def test_reject_oversized_file_returns_413(tmp_path: Path) -> None:
    # Límite pequeño de 100 bytes
    client, tokens = _build_test_app(tmp_path, max_upload_size=100)
    client.headers["Authorization"] = f"Bearer {tokens['t1']}"

    # Imagen válida pero de más de 100 bytes
    large_image = PNG_BYTES + b"\x00" * 200
    resp = client.post(
        "/transcribe",
        files={"file": ("large.png", large_image, "image/png")},
    )
    assert resp.status_code == 413
