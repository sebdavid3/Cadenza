"""Pruebas de integración del motor OMR en la API (ADR-0005, #8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cadenza.api import Settings, create_app
from cadenza.application import Role, User
from cadenza.domain import ScoreDocument
from cadenza.omr import HOMREngine, OMREngine, OMRTranscriptionError
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi.testclient import TestClient


def _is_homr_available() -> bool:
    try:
        from homr import main  # noqa: F401

        return True
    except (ImportError, RuntimeError):
        return False


HOMR_AVAILABLE = _is_homr_available()


class _FailingOMREngine(OMREngine):
    """Motor fake que simula un fallo durante la transcripción (ej. imagen sin pentagramas)."""

    @property
    def engine_id(self) -> str:
        return "failing-omr"

    def transcribe(self, image_path: Path) -> ScoreDocument:
        raise OMRTranscriptionError("No staffs found in image")


def _client_with_engine(engine: OMREngine) -> TestClient:
    db_engine = create_memory_engine()
    create_schema(db_engine)
    session_factory = create_session_factory(db_engine)
    with session_factory() as db:
        user_repo = SqlAlchemyUserRepository(db)
        user_repo.add(
            User(
                id="test-user",
                username="tester",
                password_hash="test-pass",
                role=Role.INVESTIGADOR,
                active=True,
            )
        )
        db.commit()

    app = create_app(
        session_factory,
        omr_engine=engine,
        settings=Settings(auth_secret_key="test-jwt-signing-key-minimum-32-bytes-long"),
    )
    token = app.state.token_service.create_access_token(user_id="test-user", role=Role.INVESTIGADOR)
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def test_omr_transcription_error_returns_422() -> None:
    client = _client_with_engine(_FailingOMREngine())
    upload = {"file": ("empty.png", b"\x89PNG\r\n\x1a\n", "image/png")}

    response = client.post("/transcribe", files=upload)
    assert response.status_code == 422
    data = response.json()
    assert "No staffs found in image" in data["detail"]


@pytest.mark.skipif(not HOMR_AVAILABLE, reason="requiere el extra opcional 'homr'")
def test_homr_engine_transcribe_e2e(tmp_path: Path) -> None:
    # La imagen sale del manifiesto del corpus: un glob sobre `data/primus` devuelve
    # primero archivos AppleDouble (`._*.png`), que no son imágenes válidas (#97).
    manifest_path = Path(__file__).resolve().parents[3] / "data" / "manifest.json"
    if not manifest_path.is_file():
        pytest.skip("no hay data/manifest.json para ejecutar inferencia real de HOMR")
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))["entries"]
    real_image = manifest_path.parent / entries[0]["image"]
    if not real_image.is_file():
        pytest.skip(f"no existe la imagen del manifiesto: {real_image}")
    engine = HOMREngine(use_gpu=False)
    client = _client_with_engine(engine)

    with real_image.open("rb") as handle:
        upload = {"file": (real_image.name, handle.read(), "image/png")}

    response = client.post("/transcribe", files=upload)
    assert response.status_code == 201
    body = response.json()
    assert body["omr_engine"] == "homr"
    assert body["session_id"]
    assert body["document_id"]

    # Detalle de la sesión con device registrado
    session_res = client.get(f"/sessions/{body['session_id']}")
    assert session_res.status_code == 200
    detail = session_res.json()
    assert detail["document"]["provenance"]["device"] in ("cpu", "cuda")
    # El motor real devuelve música, no un documento vacío.
    measures = detail["document"]["score"]["parts"][0]["staves"][0]["measures"]
    assert measures
    assert any(event["kind"] == "note" for measure in measures for event in measure["events"])
    assert detail["anchor_index"]["entries"]

    # Flujo completo sobre la transcripción real: editar, conflicto de secuencia,
    # revalidar, deshacer, exportar y cerrar.
    session_id = body["session_id"]
    anchor = next(
        entry["anchor"]
        for entry in detail["anchor_index"]["entries"]
        if entry["event"]["kind"] == "note"
        and entry["anchor"]["part"] == 0
        and entry["anchor"]["staff"] == 0
    )
    voice_events = [
        event
        for measure in measures
        if measure["number"] == anchor["measure"]
        for event in measure["events"]
        if event["voice"] == anchor["voice"]
    ]
    current_pitch = voice_events[anchor["event_index"]]["pitch"]
    edit_body = {
        "base_seq": detail["current_seq"],
        "op": "SetPitch",
        "anchor": anchor,
        "before": {"pitch": current_pitch},
        "after": {"pitch": "D5" if current_pitch == "C5" else "C5"},
    }
    edit_res = client.post(f"/sessions/{session_id}/edits", json=edit_body)
    assert edit_res.status_code == 201
    assert edit_res.json()["author"] == "tester"
    # La misma edición sobre un estado ya obsoleto se rechaza (ADR-0011).
    assert client.post(f"/sessions/{session_id}/edits", json=edit_body).status_code == 409

    assert client.post(f"/sessions/{session_id}/validate").status_code == 200
    assert client.post(f"/sessions/{session_id}/undo").status_code == 200
    assert client.get(f"/sessions/{session_id}").json()["current_seq"] == 2

    musicxml = client.get(f"/sessions/{session_id}/export", params={"format": "musicxml"})
    assert musicxml.status_code == 200
    assert b"<score-partwise" in musicxml.content
    midi = client.get(f"/sessions/{session_id}/export", params={"format": "midi"})
    assert midi.status_code == 200
    assert midi.content[:4] == b"MThd"

    assert client.post(f"/sessions/{session_id}/finalize").status_code == 200


def test_homr_configured_in_api_transcribes_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    from cadenza.api import Settings, create_default_app
    from cadenza.domain import Provenance, ScoreDocument, build_anchor_index
    from cadenza.omr.testing import _sample_ir

    sample_score = _sample_ir()
    fake_doc = ScoreDocument(
        id="homr-doc-test",
        score=sample_score,
        anchors=build_anchor_index(sample_score),
        provenance=Provenance(
            omr_engine="homr",
            model_version="0.7.0",
            device="cuda",
        ),
    )

    monkeypatch.setattr(HOMREngine, "transcribe", lambda self, path: fake_doc)

    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        omr_use_gpu=True,
        auth_secret_key="test-jwt-signing-key-minimum-32-bytes-long",
    )
    app = create_default_app(settings)
    with app.state.session_factory() as db:
        user_repo = SqlAlchemyUserRepository(db)
        user_repo.add(
            User(
                id="homr-tester",
                username="homr_user",
                password_hash="test-pass",
                role=Role.INVESTIGADOR,
                active=True,
            )
        )
        db.commit()

    token = app.state.token_service.create_access_token(
        user_id="homr-tester", role=Role.INVESTIGADOR
    )
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {token}"

    upload = {"file": ("score.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    response = client.post("/transcribe", files=upload)
    assert response.status_code == 201
    body = response.json()
    assert body["omr_engine"] == "homr"
    assert body["document_id"] == "homr-doc-test"

    detail = client.get(f"/sessions/{body['session_id']}").json()
    assert detail["omr_engine"] == "homr"
    assert detail["document"]["provenance"]["omr_engine"] == "homr"
    assert detail["document"]["provenance"]["device"] == "cuda"
