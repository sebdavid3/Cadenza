"""Pruebas de integración del CLI offline de aprendizaje activo (ADR-0008, #22)."""

from __future__ import annotations

import json
import secrets
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
from cadenza.omr.testing import FakeOMREngine
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
        if filename != "dataset.json" and filename != "selected.json":
            # Las métricas de `train` no son mediciones (D14): la marca llega a los tres (#139).
            assert content["simulated"] is True, filename

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


def test_cli_evaluate_and_promote_with_real_ser(tmp_path: Path, populated_db_url: str) -> None:
    """Verifica que evaluate reporte SER y OMR-NED y que promote registre la SER real (#30)."""
    dataset_path = tmp_path / "dataset.json"
    trained_path = tmp_path / "trained.json"
    eval_path = tmp_path / "eval_report.json"
    promoted_path = tmp_path / "promoted.json"
    artifacts_dir = tmp_path / "artifacts"

    # 1. build-dataset & train
    main(["build-dataset", "--db-url", populated_db_url, "--output", str(dataset_path)])
    main(
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
        ]
    )

    # 2. evaluate con SER y OMR-NED reales (ej. del baseline HOMR sobre PrIMuS)
    rc_ev = main(
        [
            "evaluate",
            "--input",
            str(trained_path),
            "--output",
            str(eval_path),
            "--ser",
            "0.1124",
            "--omr-ned",
            "0.0850",
        ]
    )
    assert rc_ev == 0
    report = json.loads(eval_path.read_text(encoding="utf-8"))
    assert report["metrics"]["ser"] == 0.1124
    assert report["metrics"]["omr_ned"] == 0.0850
    assert report["meets_threshold"] is True

    # 3. promote registra la SER real en la base de datos
    rc_pr = main(
        [
            "promote",
            "--input",
            str(eval_path),
            "--version",
            "v1.5.0-real-ser",
            "--db-url",
            populated_db_url,
            "--output",
            str(promoted_path),
        ]
    )
    assert rc_pr == 0
    engine = create_engine_for_url(populated_db_url)
    factory = create_session_factory(engine)
    with session_scope(factory) as db:
        reg = SqlAlchemyModelRegistry(db)
        active = reg.active()
        assert active is not None
        assert active.version == "v1.5.0-real-ser"
        assert active.metrics.ser == 0.1124
        assert active.metrics.omr_ned == 0.0850


def test_cli_train_with_trainer_options(tmp_path: Path, populated_db_url: str) -> None:
    dataset_path = tmp_path / "dataset.json"
    trained_fake = tmp_path / "trained_fake.json"
    trained_auto = tmp_path / "trained_auto.json"
    artifacts_dir = tmp_path / "artifacts"

    # Construir dataset
    main(["build-dataset", "--db-url", populated_db_url, "--output", str(dataset_path)])

    # 1. train explícito con --trainer fake
    rc_fake = main(
        [
            "train",
            "--input",
            str(dataset_path),
            "--output",
            str(trained_fake),
            "--artifacts-dir",
            str(artifacts_dir),
            "--db-url",
            populated_db_url,
            "--trainer",
            "fake",
        ]
    )
    assert rc_fake == 0
    fake_data = json.loads(trained_fake.read_text(encoding="utf-8"))
    assert fake_data["trainer"] == "FakeTrainer"

    # 2. train con --trainer auto (fallback a FakeTrainer cuando torch no está)
    rc_auto = main(
        [
            "train",
            "--input",
            str(dataset_path),
            "--output",
            str(trained_auto),
            "--artifacts-dir",
            str(artifacts_dir),
            "--db-url",
            populated_db_url,
            "--trainer",
            "auto",
        ]
    )
    assert rc_auto == 0
    auto_data = json.loads(trained_auto.read_text(encoding="utf-8"))
    assert auto_data["trainer"] in ("FakeTrainer", "PyTorchTrainer")


CONFIG_PATH = Path(__file__).resolve().parents[3] / "configs" / "learning" / "default.json"


def _artifact(tmp_path: Path, metrics: dict[str, float] | None) -> Path:
    data: dict[str, object] = {"artifact_hash": "abc", "dataset_hash": "def"}
    if metrics is not None:
        data["metrics"] = metrics
    path = tmp_path / "trained.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_cli_evaluate_fails_without_measured_metrics(tmp_path: Path) -> None:
    """Sin métricas en el artefacto, manifiesto ni argumentos no hay SER/OMR-NED (#139)."""
    report = tmp_path / "eval.json"
    rc = main(
        [
            "evaluate",
            "--input",
            str(_artifact(tmp_path, None)),
            "--config",
            str(CONFIG_PATH),
            "--output",
            str(report),
        ]
    )
    assert rc == 1
    assert not report.exists()


def test_cli_evaluate_fails_when_manifest_is_missing(tmp_path: Path) -> None:
    """Un `--manifest` inexistente es un error, no se ignora en silencio (#139)."""
    report = tmp_path / "eval.json"
    rc = main(
        [
            "evaluate",
            "--input",
            str(_artifact(tmp_path, {"ser": 0.05, "omr_ned": 0.04})),
            "--config",
            str(CONFIG_PATH),
            "--output",
            str(report),
            "--manifest",
            str(tmp_path / "missing.json"),
        ]
    )
    assert rc == 1
    assert not report.exists()


def test_cli_evaluate_uses_artifact_metrics(tmp_path: Path) -> None:
    report = tmp_path / "eval.json"
    rc = main(
        [
            "evaluate",
            "--input",
            str(_artifact(tmp_path, {"ser": 0.05, "omr_ned": 0.04})),
            "--config",
            str(CONFIG_PATH),
            "--output",
            str(report),
        ]
    )
    assert rc == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["metrics"] == {"ser": 0.05, "omr_ned": 0.04}
    # Un artefacto sin la marca (anterior a #139) cuenta como no medido.
    assert data["simulated"] is True
    assert data["metrics_source"] == {"ser": "artifact", "omr_ned": "artifact"}


def test_cli_promote_fails_without_metrics(tmp_path: Path) -> None:
    """Sin métricas, promote no imputa 0.0 (que superaría cualquier umbral) (#139)."""
    output = tmp_path / "promoted.json"
    rc = main(
        [
            "promote",
            "--input",
            str(_artifact(tmp_path, None)),
            "--config",
            str(CONFIG_PATH),
            "--db-url",
            f"sqlite:///{(tmp_path / 'registry.db').as_posix()}",
            "--output",
            str(output),
        ]
    )
    assert rc == 1
    assert not output.exists()


def test_cli_evaluate_fails_when_manifest_measures_no_success(tmp_path: Path) -> None:
    """Si el corpus no da ningún éxito, no se usan en su lugar las métricas del artefacto (#139)."""
    fixture = Path(__file__).parent / "fixtures" / "simple.musicxml"
    (tmp_path / "mini" / "gt").mkdir(parents=True)
    (tmp_path / "mini" / "gt" / "s1.musicxml").write_text(
        fixture.read_text(encoding="utf-8"), encoding="utf-8"
    )
    predictions = tmp_path / "mini" / "predictions"
    predictions.mkdir()
    (predictions / "failures.json").write_text(
        json.dumps([{"id": "s1", "error": "Exception: No staffs found"}]), encoding="utf-8"
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {"corpus": "mini", "entries": [{"id": "s1", "ground_truth": "mini/gt/s1.musicxml"}]}
        ),
        encoding="utf-8",
    )
    report = tmp_path / "eval.json"
    rc = main(
        [
            "evaluate",
            "--input",
            str(_artifact(tmp_path, {"ser": 0.05, "omr_ned": 0.04})),
            "--config",
            str(CONFIG_PATH),
            "--output",
            str(report),
            "--manifest",
            str(manifest),
        ]
    )
    assert rc == 1
    assert not report.exists()


def _identity_corpus(tmp_path: Path) -> tuple[Path, Path]:
    """Corpus de una partitura cuya predicción es idéntica a la verdad: SER y OMR-NED = 0."""
    fixture = (Path(__file__).parent / "fixtures" / "simple.musicxml").read_text(encoding="utf-8")
    (tmp_path / "mini" / "gt").mkdir(parents=True)
    (tmp_path / "mini" / "gt" / "s1.musicxml").write_text(fixture, encoding="utf-8")
    predictions = tmp_path / "mini" / "predictions"
    predictions.mkdir()
    (predictions / "s1.musicxml").write_text(fixture, encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    entries = [{"id": "s1", "ground_truth": "mini/gt/s1.musicxml"}]
    manifest.write_text(json.dumps({"corpus": "mini", "entries": entries}), encoding="utf-8")
    return manifest, predictions


def test_cli_evaluate_prefers_arguments_then_manifest_over_artifact(tmp_path: Path) -> None:
    """Prioridad de las métricas: argumentos, medición con --manifest y artefacto (#139)."""
    manifest, predictions = _identity_corpus(tmp_path)
    report = tmp_path / "eval.json"
    rc = main(
        [
            "evaluate",
            "--input",
            str(_artifact(tmp_path, {"ser": 0.05, "omr_ned": 0.04})),
            "--config",
            str(CONFIG_PATH),
            "--output",
            str(report),
            "--manifest",
            str(manifest),
            "--predictions-dir",
            str(predictions),
            "--ser",
            "0.07",
        ]
    )
    assert rc == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["metrics"] == {"ser": 0.07, "omr_ned": 0.0}
    assert data["metrics_source"] == {"ser": "arguments", "omr_ned": "manifest"}
    assert data["simulated"] is False


def test_cli_trainer_default_metrics_are_marked_simulated_downstream(
    tmp_path: Path, populated_db_url: str
) -> None:
    """Las métricas fijas del entrenador salen marcadas en train, evaluate y promote (#139, D14)."""
    dataset = tmp_path / "dataset.json"
    trained = tmp_path / "trained.json"
    report = tmp_path / "eval.json"
    promoted = tmp_path / "promoted.json"
    main(["build-dataset", "--db-url", populated_db_url, "--output", str(dataset)])
    rc = main(
        [
            "train",
            "--input",
            str(dataset),
            "--output",
            str(trained),
            "--artifacts-dir",
            str(tmp_path / "artifacts"),
            "--db-url",
            populated_db_url,
            "--trainer",
            "fake",
        ]
    )
    assert rc == 0
    trained_data = json.loads(trained.read_text(encoding="utf-8"))
    assert trained_data["simulated"] is True
    assert trained_data["metrics_source"] == "trainer_default"
    assert "simulation_warning" in trained_data

    assert main(["evaluate", "--input", str(trained), "--output", str(report)]) == 0
    report_data = json.loads(report.read_text(encoding="utf-8"))
    assert report_data["simulated"] is True
    assert report_data["metrics_source"] == {"ser": "artifact", "omr_ned": "artifact"}

    main(
        [
            "promote",
            "--input",
            str(trained),
            "--version",
            "v-simulada",
            "--db-url",
            populated_db_url,
            "--output",
            str(promoted),
            "--allow-rejected",
        ]
    )
    assert json.loads(promoted.read_text(encoding="utf-8"))["simulated"] is True


def test_cli_train_metrics_are_never_measurements(tmp_path: Path, populated_db_url: str) -> None:
    """Con --ser/--omr-ned las métricas del artefacto siguen sin medirse (D14, #139)."""
    dataset = tmp_path / "dataset.json"
    trained = tmp_path / "trained.json"
    main(["build-dataset", "--db-url", populated_db_url, "--output", str(dataset)])
    common_args = [
        "train",
        "--input",
        str(dataset),
        "--output",
        str(trained),
        "--artifacts-dir",
        str(tmp_path / "artifacts"),
        "--db-url",
        populated_db_url,
        "--trainer",
        "fake",
    ]
    assert main([*common_args, "--ser", "0.05"]) == 1
    assert not trained.exists()

    assert main([*common_args, "--ser", "0.05", "--omr-ned", "0.04"]) == 0
    data = json.loads(trained.read_text(encoding="utf-8"))
    assert data["simulated"] is True
    assert data["metrics_source"] == "arguments"

    report = tmp_path / "eval.json"
    assert (
        main(["evaluate", "--input", str(trained), "--output", str(report), "--ser", "0.01"]) == 0
    )
    mixed = json.loads(report.read_text(encoding="utf-8"))
    assert mixed["metrics_source"] == {"ser": "arguments", "omr_ned": "artifact"}
    assert mixed["simulated"] is True


def test_cli_promote_marks_artifact_without_flag_as_simulated(tmp_path: Path) -> None:
    """`promote` no da por medidas las métricas de un artefacto sin la marca (#139)."""
    output = tmp_path / "promoted.json"
    rc = main(
        [
            "promote",
            "--input",
            str(_artifact(tmp_path, {"ser": 0.05, "omr_ned": 0.04})),
            "--version",
            "v-sin-marca",
            "--config",
            str(CONFIG_PATH),
            "--db-url",
            f"sqlite:///{(tmp_path / 'registry.db').as_posix()}",
            "--output",
            str(output),
        ]
    )
    assert rc == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["simulated"] is True
    assert "simulation_warning" in result


def test_cli_build_dataset_leaves_out_self_registered_accounts(
    tmp_path: Path, populated_db_url: str
) -> None:
    # Una cuenta del registro público con una sesión finalizada y editada (ADR-0022, D55, #191).
    factory = create_session_factory(create_engine_for_url(populated_db_url))
    visitor = User(
        id="user-registro",
        username="visita",
        password_hash=secrets.token_hex(8),
        role=Role.TRANSCRIPTOR,
        self_registered=True,
    )
    img_path = tmp_path / "otra.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\notraimagen")
    with session_scope(factory) as db:
        SqlAlchemyUserRepository(db).add(visitor)
        session_repo = SqlAlchemySessionRepository(db)
        edit_repo = SqlAlchemyEditEventRepository(db)
        transcribe_score(
            img_path,
            omr_engine=FakeOMREngine(),
            validator=ValidationEngine([]),
            session_repository=session_repo,
            current_user=visitor,
            session_id="sess-registro",
        )
        append_edit(
            session_id="sess-registro",
            op=EditOp.SET_PITCH,
            anchor=Anchor(
                part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="part-0-staff-0"
            ),
            before={"pitch": "C4"},
            after={"pitch": "D4"},
            base_seq=0,
            current_user=visitor,
            session_repository=session_repo,
            edit_repository=edit_repo,
        )
        finalize_session(
            session_id="sess-registro",
            current_user=visitor,
            session_repository=session_repo,
            edit_repository=edit_repo,
            validator=ValidationEngine([]),
        )

    default_path = tmp_path / "sin_registro.json"
    included_path = tmp_path / "con_registro.json"
    base = ["build-dataset", "--db-url", populated_db_url, "--output"]
    assert main([*base, str(default_path)]) == 0
    assert main([*base, str(included_path), "--include-self-registered"]) == 0

    default = json.loads(default_path.read_text(encoding="utf-8"))
    included = json.loads(included_path.read_text(encoding="utf-8"))
    # Solo la sesión del estudio (dos ediciones), salvo que se pida la del registro (una más).
    assert default["count"] == 2
    assert default["self_registered_included"] is False
    assert included["count"] == 3
    assert included["self_registered_included"] is True
    assert included["dataset_hash"] != default["dataset_hash"]
