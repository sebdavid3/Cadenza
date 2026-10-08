"""Pruebas del adaptador SqlAlchemyModelRegistry y su integración con OMR (ADR-0008, #21)."""

from __future__ import annotations

from pathlib import Path

import pytest
from cadenza.application import (
    EvaluationMetrics,
    ModelVersionData,
    PromotionRejected,
    PromotionThreshold,
    Role,
    User,
    transcribe_score,
)
from cadenza.omr import FakeOMREngine, HOMREngine
from cadenza.persistence import (
    ArtifactRecord,
    FilesystemArtifactStore,
    SqlAlchemyModelRegistry,
    SqlAlchemySessionRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from cadenza.validation import ValidationEngine
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def session_factory() -> sessionmaker[DbSession]:
    engine = create_memory_engine()
    create_schema(engine)
    return create_session_factory(engine)


@pytest.fixture
def sample_artifact(session_factory: sessionmaker[DbSession]) -> str:
    with session_factory() as db:
        artifact = ArtifactRecord(
            sha256="model_onnx_weights_sha256",
            kind="model",
            media_type="application/octet-stream",
            size_bytes=2048,
            path="sha256/mo/de/model_onnx_weights_sha256",
        )
        db.add(artifact)
        db.commit()
    return "model_onnx_weights_sha256"


def test_register_and_list_versions(
    session_factory: sessionmaker[DbSession], sample_artifact: str
) -> None:
    with session_factory() as db:
        registry = SqlAlchemyModelRegistry(db)
        assert registry.active() is None
        assert registry.versions() == ()

        v1 = ModelVersionData(
            version="v1.0.0",
            artifact_hash=sample_artifact,
            dataset_hash="dataset_1",
            config_hash="config_1",
            metrics=EvaluationMetrics(ser=0.04, omr_ned=0.08),
        )
        saved_v1 = registry.register(v1)
        assert saved_v1.version == "v1.0.0"
        assert saved_v1.promoted is False
        assert saved_v1.created_at is not None

        # Intento de duplicado falla
        with pytest.raises(ValueError, match="already registered"):
            registry.register(v1)

        v2 = ModelVersionData(
            version="v1.1.0",
            artifact_hash=sample_artifact,
            dataset_hash="dataset_2",
            config_hash="config_2",
            metrics=EvaluationMetrics(ser=0.02, omr_ned=0.05),
        )
        registry.register(v2)

        versions = registry.versions()
        assert len(versions) == 2
        assert [v.version for v in versions] == ["v1.0.0", "v1.1.0"]


def test_promotion_governed_by_threshold(
    session_factory: sessionmaker[DbSession], sample_artifact: str
) -> None:
    threshold = PromotionThreshold(max_ser=0.05, max_omr_ned=0.10)

    with session_factory() as db:
        registry = SqlAlchemyModelRegistry(db, threshold=threshold)

        # Versión de baja calidad (no cumple umbral de OMR-NED)
        v_bad = ModelVersionData(
            version="v-bad",
            artifact_hash=sample_artifact,
            dataset_hash="d1",
            config_hash="c1",
            metrics=EvaluationMetrics(ser=0.04, omr_ned=0.15),
        )
        registry.register(v_bad)

        with pytest.raises(PromotionRejected, match="no supera el umbral"):
            registry.promote("v-bad")

        assert registry.active() is None

        # Versión de alta calidad (supera umbral)
        v_good = ModelVersionData(
            version="v-good",
            artifact_hash=sample_artifact,
            dataset_hash="d2",
            config_hash="c2",
            metrics=EvaluationMetrics(ser=0.03, omr_ned=0.06),
        )
        registry.register(v_good)

        promoted = registry.promote("v-good")
        assert promoted.version == "v-good"
        assert promoted.promoted is True

        active = registry.active()
        assert active is not None
        assert active.version == "v-good"


def test_promotion_exclusivity(
    session_factory: sessionmaker[DbSession], sample_artifact: str
) -> None:
    threshold = PromotionThreshold(max_ser=0.10, max_omr_ned=0.10)

    with session_factory() as db:
        registry = SqlAlchemyModelRegistry(db, threshold=threshold)

        registry.register(
            ModelVersionData(
                version="v1",
                artifact_hash=sample_artifact,
                dataset_hash="d1",
                config_hash="c1",
                metrics=EvaluationMetrics(ser=0.05, omr_ned=0.05),
            )
        )
        registry.register(
            ModelVersionData(
                version="v2",
                artifact_hash=sample_artifact,
                dataset_hash="d2",
                config_hash="c2",
                metrics=EvaluationMetrics(ser=0.03, omr_ned=0.03),
            )
        )

        registry.promote("v1")
        active1 = registry.active()
        assert active1 is not None
        assert active1.version == "v1"

        # Al promover v2, v1 deja de estar activa
        registry.promote("v2")
        active2 = registry.active()
        assert active2 is not None
        assert active2.version == "v2"

        # Versión inexistente lanza KeyError
        with pytest.raises(KeyError):
            registry.promote("non-existent")


def test_model_weights_linked_to_artifact_store(
    tmp_path: Path, session_factory: sessionmaker[DbSession]
) -> None:
    weights_bytes = b"fake-onnx-weights-content-for-testing"
    weights_path = tmp_path / "model.onnx"
    weights_path.write_bytes(weights_bytes)

    with session_factory() as db:
        store = FilesystemArtifactStore(tmp_path / "artifacts", session=db)
        artifact_hash = store.put(
            weights_bytes, kind="model", media_type="application/octet-stream"
        )
        assert store.exists(artifact_hash)

        registry = SqlAlchemyModelRegistry(db)
        version_data = ModelVersionData(
            version="v2.0-finetuned",
            artifact_hash=artifact_hash,
            dataset_hash="dataset_al_hash",
            config_hash="config_al_hash",
            metrics=EvaluationMetrics(ser=0.01, omr_ned=0.02),
        )
        registered = registry.register(version_data)
        assert registered.artifact_hash == artifact_hash

        promoted = registry.promote("v2.0-finetuned")
        assert promoted.promoted is True

        # Verificar que HOMREngine.from_active_model resuelve la versión y pesos
        engine = HOMREngine.from_active_model(registry, store, use_gpu=False)
        assert engine._model_version == "v2.0-finetuned"
        assert engine._weights_path is not None
        assert engine._weights_path.is_file()


def test_transcribe_score_uses_active_model_version(
    tmp_path: Path, session_factory: sessionmaker[DbSession], sample_artifact: str
) -> None:
    img_path = tmp_path / "test.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\nfakeimage")

    user = User(
        id="user-1",
        username="transcriptor",
        password_hash="fake-hash",
        role=Role.TRANSCRIPTOR,
    )
    validator = ValidationEngine([])

    with session_factory() as db:
        session_repo = SqlAlchemySessionRepository(db)
        registry = SqlAlchemyModelRegistry(db)

        # 1. Sin versión promovida -> usa versión de fábrica
        engine_default = FakeOMREngine.from_active_model(registry)
        res1 = transcribe_score(
            img_path,
            omr_engine=engine_default,
            validator=validator,
            session_repository=session_repo,
            current_user=user,
            session_id="sess-default",
        )
        assert res1.session_id == "sess-default"
        s1 = session_repo.get("sess-default")
        assert s1 is not None
        assert s1.model_version == "fake-1"
        assert isinstance(s1.document, dict)
        prov1 = s1.document.get("provenance")
        assert isinstance(prov1, dict)
        assert prov1.get("model_version") == "fake-1"

        # 2. Con versión promovida -> usa la versión activa
        registry.register(
            ModelVersionData(
                version="promoted-v2.5",
                artifact_hash=sample_artifact,
                dataset_hash="d_hash",
                config_hash="c_hash",
                metrics=EvaluationMetrics(ser=0.01, omr_ned=0.01),
            )
        )
        registry.promote("promoted-v2.5")

        engine_active = FakeOMREngine.from_active_model(registry)
        res2 = transcribe_score(
            img_path,
            omr_engine=engine_active,
            validator=validator,
            session_repository=session_repo,
            current_user=user,
            session_id="sess-active",
        )
        assert res2.session_id == "sess-active"
        s2 = session_repo.get("sess-active")
        assert s2 is not None
        assert s2.model_version == "promoted-v2.5"
        assert isinstance(s2.document, dict)
        prov2 = s2.document.get("provenance")
        assert isinstance(prov2, dict)
        assert prov2.get("model_version") == "promoted-v2.5"
