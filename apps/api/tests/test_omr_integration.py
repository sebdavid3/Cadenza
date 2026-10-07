"""Pruebas de integración del motor OMR en la API (ADR-0005, #8)."""

from __future__ import annotations

from pathlib import Path

import pytest
from cadenza.api import create_app
from cadenza.domain import ScoreDocument
from cadenza.omr import HOMREngine, OMREngine, OMRTranscriptionError
from cadenza.persistence import create_memory_engine, create_schema, create_session_factory
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
    app = create_app(create_session_factory(db_engine), omr_engine=engine)
    return TestClient(app)


def test_omr_transcription_error_returns_422() -> None:
    client = _client_with_engine(_FailingOMREngine())
    upload = {"file": ("empty.png", b"\x89PNG\r\n\x1a\n", "image/png")}

    response = client.post("/transcribe", files=upload)
    assert response.status_code == 422
    data = response.json()
    assert "No staffs found in image" in data["detail"]


@pytest.mark.skipif(not HOMR_AVAILABLE, reason="requiere el extra opcional 'homr'")
def test_homr_engine_transcribe_e2e(tmp_path: Path) -> None:
    # Verificamos si existe alguna imagen de primus para prueba E2E real
    candidate_images = list(Path("data").glob("primus/**/*.png"))
    if not candidate_images:
        pytest.skip(
            "no hay imágenes de partituras en data/primus para ejecutar inferencia real de HOMR"
        )

    real_image = candidate_images[0]
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


def test_homr_configured_in_api_transcribes_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    from cadenza.api import Settings, create_default_app
    from cadenza.domain import Provenance, ScoreDocument, build_anchor_index
    from cadenza.omr.adapters.fake import _sample_ir

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
        omr_engine="homr",
        omr_use_gpu=True,
    )
    app = create_default_app(settings)
    client = TestClient(app)

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
