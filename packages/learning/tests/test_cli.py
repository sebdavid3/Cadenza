"""Pruebas de integración del CLI offline de aprendizaje activo (ADR-0008, #22)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cadenza.application import (
    Role,
    User,
    append_edit,
    finalize_session,
    transcribe_score,
)
from cadenza.domain import Anchor, EditOp
from cadenza.omr import FakeOMREngine
from cadenza.persistence import (
    SqlAlchemyEditEventRepository,
    SqlAlchemyModelRegistry,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
    create_engine_for_url,
    create_schema,
    create_session_factory,
    session_scope,
)
from cadenza.validation import ValidationEngine

from ml.cli import main


@pytest.fixture
def populated_db_url(tmp_path: Path) -> str:
    """Crea una base de datos SQLite con una sesión finalizada, ediciones y hallazgos."""
    db_file = tmp_path / "cadenza_test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    engine = create_engine_for_url(db_url)
    create_schema(engine)
    factory = create_session_factory(engine)

    img_path = tmp_path / "score.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\nfakeimage")

    user = User(
        id="user-trans",
        username="transcriptor1",
        password_hash="hash",
        role=Role.TRANSCRIPTOR,
    )

    with session_scope(factory) as db:
        user_repo = SqlAlchemyUserRepository(db)
        user_repo.add(user)
        session_repo = SqlAlchemySessionRepository(db)
        edit_repo = SqlAlchemyEditEventRepository(db)

        # 1. Transcribir
        res = transcribe_score(
            img_path,
            omr_engine=FakeOMREngine(),
            validator=ValidationEngine([]),
            session_repository=session_repo,
            current_user=user,
            session_id="sess-al-1",
        )
        assert res.session_id == "sess-al-1"

        # 2. Agregar ediciones
        anchor = Anchor(
            part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="part-0-staff-0"
        )
        append_edit(
            session_id="sess-al-1",
            op=EditOp.SET_PITCH,
            anchor=anchor,
            before={"pitch": "C4"},
            after={"pitch": "D4"},
            base_seq=0,
            current_user=user,
            session_repository=session_repo,
            edit_repository=edit_repo,
        )

        anchor2 = Anchor(
            part=0, staff=0, measure=1, voice=0, event_index=1, staff_id="part-0-staff-0"
        )
        append_edit(
            session_id="sess-al-1",
            op=EditOp.SET_PITCH,
            anchor=anchor2,
            before={"pitch": "D4"},
            after={"pitch": "E4"},
            base_seq=1,
            current_user=user,
            session_repository=session_repo,
            edit_repository=edit_repo,
        )

        # 3. Finalizar sesión para que entre al dataset
        finalize_session(
            session_id="sess-al-1",
            current_user=user,
            session_repository=session_repo,
            edit_repository=edit_repo,
            validator=ValidationEngine([]),
        )

    return db_url


def test_cli_build_dataset_and_select(tmp_path: Path, populated_db_url: str) -> None:
    dataset_path = tmp_path / "dataset.json"
    selected_path = tmp_path / "selected.json"

    # 1. build-dataset
    rc = main(
        [
            "build-dataset",
            "--db-url",
            populated_db_url,
            "--output",
            str(dataset_path),
        ]
    )
    assert rc == 0
    assert dataset_path.is_file()

    dataset_content = json.loads(dataset_path.read_text(encoding="utf-8"))
    assert dataset_content["count"] == 2
    assert "dataset_hash" in dataset_content
    assert len(dataset_content["samples"]) == 2

    # 2. select con estrategia diversity y presupuesto 1
    rc_sel = main(
        [
            "select",
            "--input",
            str(dataset_path),
            "--output",
            str(selected_path),
            "--strategy",
            "diversity",
            "--budget",
            "1",
        ]
    )
    assert rc_sel == 0
    assert selected_path.is_file()

    selected_content = json.loads(selected_path.read_text(encoding="utf-8"))
    assert selected_content["count"] == 1
    assert selected_content["strategy"] == "diversity"
    assert "dataset_hash" in selected_content
    assert selected_content["source_dataset_hash"] == dataset_content["dataset_hash"]


def test_cli_train_evaluate_and_promote(tmp_path: Path, populated_db_url: str) -> None:
    dataset_path = tmp_path / "dataset.json"
    trained_path = tmp_path / "trained.json"
    eval_path = tmp_path / "eval.json"
    promoted_path = tmp_path / "promoted.json"
    artifacts_dir = tmp_path / "artifacts"

    # Extraer dataset
    main(["build-dataset", "--db-url", populated_db_url, "--output", str(dataset_path)])

    # 1. train con FakeTrainer y métricas de alta calidad
    rc_tr = main(
        [
            "train",
            "--input",
            str(dataset_path),
            "--output",
            str(trained_path),
            "--artifacts-dir",
            str(artifacts_dir),
            "--db-url",
            populated_db_url,
            "--ser",
            "0.05",
            "--omr-ned",
            "0.04",
        ]
    )
    assert rc_tr == 0
    assert trained_path.is_file()

    tr_data = json.loads(trained_path.read_text(encoding="utf-8"))
    artifact_hash = tr_data["artifact_hash"]
    assert artifact_hash is not None
    assert tr_data["metrics"]["ser"] == 0.05
    assert "dataset_hash" in tr_data
    assert "config_hash" in tr_data
    assert "seed" in tr_data

    # 2. evaluate
    rc_ev = main(
        [
            "evaluate",
            "--input",
            str(trained_path),
            "--output",
            str(eval_path),
        ]
    )
    assert rc_ev == 0
    eval_data = json.loads(eval_path.read_text(encoding="utf-8"))
    assert eval_data["meets_threshold"] is True
    assert eval_data["artifact_hash"] == artifact_hash
    assert "dataset_hash" in eval_data
    assert "config_hash" in eval_data
    assert "seed" in eval_data

    # 3. promote
    rc_pr = main(
        [
            "promote",
            "--input",
            str(trained_path),
            "--version",
            "v1.0.0-test",
            "--db-url",
            populated_db_url,
            "--output",
            str(promoted_path),
        ]
    )
    assert rc_pr == 0
    assert promoted_path.is_file()

    pr_data = json.loads(promoted_path.read_text(encoding="utf-8"))
    assert pr_data["promoted"] is True
    assert pr_data["active_model_version"] == "v1.0.0-test"
    assert pr_data["artifact_hash"] == artifact_hash
    assert "dataset_hash" in pr_data
    assert "config_hash" in pr_data
    assert "seed" in pr_data

    # Verificar que el modelo está activo en la base de datos
    engine = create_engine_for_url(populated_db_url)
    factory = create_session_factory(engine)
    with session_scope(factory) as db:
        reg = SqlAlchemyModelRegistry(db)
        active = reg.active()
        assert active is not None
        assert active.version == "v1.0.0-test"
        assert active.artifact_hash == artifact_hash


def test_cli_promote_rejected_when_metrics_exceed_threshold(
    tmp_path: Path, populated_db_url: str
) -> None:
    dataset_path = tmp_path / "dataset.json"
    trained_bad_path = tmp_path / "trained_bad.json"
    promoted_path = tmp_path / "promoted_bad.json"
    artifacts_dir = tmp_path / "artifacts"

    main(["build-dataset", "--db-url", populated_db_url, "--output", str(dataset_path)])

    # Entrenar con métricas malas (SER=0.8, OMR-NED=0.7)
    main(
        [
            "train",
            "--input",
            str(dataset_path),
            "--output",
            str(trained_bad_path),
            "--artifacts-dir",
            str(artifacts_dir),
            "--db-url",
            populated_db_url,
            "--ser",
            "0.80",
            "--omr-ned",
            "0.70",
        ]
    )

    # Intento de promoción debe fallar con código 1
    rc = main(
        [
            "promote",
            "--input",
            str(trained_bad_path),
            "--version",
            "v-bad-quality",
            "--db-url",
            populated_db_url,
            "--output",
            str(promoted_path),
        ]
    )
    assert rc == 1
    bad_data = json.loads(promoted_path.read_text(encoding="utf-8"))
    assert bad_data["promoted"] is False
    assert "no supera el umbral" in str(bad_data["rejection_reason"])


def test_cli_pipeline_run_end_to_end(tmp_path: Path, populated_db_url: str) -> None:
    work_dir = tmp_path / "pipeline_run"
    artifacts_dir = tmp_path / "artifacts"

    rc = main(
        [
            "run",
            "--work-dir",
            str(work_dir),
            "--db-url",
            populated_db_url,
            "--artifacts-dir",
            str(artifacts_dir),
            "--strategy",
            "hybrid",
            "--budget",
            "2",
            "--version",
            "v2.0.0-pipeline",
            "--ser",
            "0.02",
            "--omr-ned",
            "0.03",
        ]
    )
    assert rc == 0

    # Verificar que los artefactos encadenados existen en el disco y contienen trazabilidad
    for filename in (
        "dataset.json",
        "selected.json",
        "trained_artifact.json",
        "evaluation_report.json",
        "promotion_result.json",
    ):
        file_path = work_dir / filename
        assert file_path.is_file()
        content = json.loads(file_path.read_text(encoding="utf-8"))
        assert "dataset_hash" in content
        assert "config_hash" in content
        assert "seed" in content

    # Verificar que el modelo quedó activo en la BD
    engine = create_engine_for_url(populated_db_url)
    factory = create_session_factory(engine)
    with session_scope(factory) as db:
        reg = SqlAlchemyModelRegistry(db)
        active = reg.active()
        assert active is not None
        assert active.version == "v2.0.0-pipeline"


def test_cli_subprocess_invocation(tmp_path: Path, populated_db_url: str) -> None:
    """Verifica que el CLI pueda ejecutarse vía proceso hijo `python -m ml`."""
    import subprocess
    import sys

    dataset_path = tmp_path / "sub_dataset.json"
    cmd = [
        sys.executable,
        "-m",
        "ml",
        "build-dataset",
        "--db-url",
        populated_db_url,
        "--output",
        str(dataset_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, f"Error en CLI: {result.stderr}"
    assert dataset_path.is_file()
    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    assert data["count"] == 2
    assert "dataset_hash" in data
