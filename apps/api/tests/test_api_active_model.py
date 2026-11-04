"""Transcripción con un modelo promovido en el Model Registry (#21, D52, #133)."""

from __future__ import annotations

from pathlib import Path

import pytest
from cadenza.api import Settings, create_app
from cadenza.application import EvaluationMetrics, ModelVersionData, Role, User
from cadenza.domain import Provenance, ScoreDocument, build_anchor_index
from cadenza.omr import HOMREngine
from cadenza.omr.testing import _sample_ir
from cadenza.persistence import (
    FilesystemArtifactStore,
    SqlAlchemyModelRegistry,
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi.testclient import TestClient


@pytest.mark.parametrize("use_gpu", [False, True])
def test_transcribe_with_active_model_respects_use_gpu_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, use_gpu: bool
) -> None:
    """Con un modelo activo, HOMR se reconstruye con `CADENZA_OMR_USE_GPU` (D52)."""
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)
    artifacts_dir = tmp_path / "artifacts"

    with session_factory() as db:
        SqlAlchemyUserRepository(db).add(
            User(id="u1", username="investigador", password_hash="h", role=Role.INVESTIGADOR)
        )
        store = FilesystemArtifactStore(artifacts_dir, session=db)
        weights = store.put(b"onnx-weights", kind="model", media_type="application/octet-stream")
        registry = SqlAlchemyModelRegistry(db)
        registry.register(
            ModelVersionData(
                version="v-activo",
                artifact_hash=weights,
                dataset_hash="d",
                config_hash="c",
                metrics=EvaluationMetrics(ser=0.1, omr_ned=0.1),
            )
        )
        registry.promote("v-activo")
        db.commit()

    seen: dict[str, object] = {}

    def fake_transcribe(self: HOMREngine, image_path: Path) -> ScoreDocument:
        seen["use_gpu"] = self._use_gpu
        seen["model_version"] = self._model_version
        score = _sample_ir()
        return ScoreDocument(
            id="homr-doc-activo",
            score=score,
            anchors=build_anchor_index(score),
            provenance=Provenance(omr_engine="homr", model_version="v-activo", device="cpu"),
        )

    monkeypatch.setattr(HOMREngine, "transcribe", fake_transcribe)

    settings = Settings(
        auth_secret_key="test-jwt-signing-key-minimum-32-bytes-long",
        artifacts_dir=artifacts_dir,
        omr_use_gpu=use_gpu,
    )
    app = create_app(session_factory, settings=settings)
    token = app.state.token_service.create_access_token(user_id="u1", role=Role.INVESTIGADOR)
    client = TestClient(app, headers={"Authorization": f"Bearer {token}"})

    upload = {"file": ("score.png", b"\x89PNG\r\n\x1a\n", "image/png")}
    response = client.post("/transcribe", files=upload)

    assert response.status_code == 201
    assert seen == {"use_gpu": use_gpu, "model_version": "v-activo"}
