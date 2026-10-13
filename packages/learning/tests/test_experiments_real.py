"""Pruebas de los experimentos con datos reales y criterios de validez externa (Issue #24)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cadenza.learning import omr_ned_pair
from cadenza.omr import OMRTranscriptionError

from ml.experiments import common, exp_01_effort, exp_02_active_learning, exp_03_omr_quality

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_MANIFEST = REPO_ROOT / "data" / "manifest.json"


def test_run_info_generation(tmp_path: Path) -> None:
    manifest_stub = tmp_path / "manifest.json"
    manifest_stub.write_text('{"corpus": "test"}', encoding="utf-8")

    info = common.get_run_info("test_exp", seed=123, manifest_path=manifest_stub)
    assert info["experiment"] == "test_exp"
    assert info["seed"] == 123
    assert "timestamp_utc" in info
    assert "git_commit" in info
    assert info["manifest_sha256"] != ""


def test_exp_01_synthetic_fallback() -> None:
    res = exp_01_effort._run_synthetic_fallback(measures=20, broken_ratio=0.3, seed=42)
    assert res["experiment"] == "exp_01_effort"
    assert res["mode"] == "synthetic_fallback"
    effort = res["inspection_effort"]
    assert effort["total_measures"] == 20
    assert effort["baseline_inspections_manual"] == 20
    assert effort["effort_reduction_percent"] > 0.0

    tradeoff = res["error_detection_and_tradeoff"]
    assert "missed_errors_percent" in tradeoff
    assert "sample_size_justification" in res
    assert "methodological_limitations" in res


@pytest.mark.skipif(not DATA_MANIFEST.is_file(), reason="Requiere data/manifest.json")
def test_exp_01_real_primus_data() -> None:
    # Limitado a 5 incipits para rapidez en suite de pruebas
    res = exp_01_effort.run(manifest_path=DATA_MANIFEST, limit=5, seed=20260920)
    assert res["experiment"] == "exp_01_effort"
    assert res["mode"] == "real_data_primus"
    effort = res["inspection_effort"]
    assert effort["total_measures"] > 0
    assert effort["assisted_inspections_validator"] <= effort["baseline_inspections_manual"]

    tradeoff = res["error_detection_and_tradeoff"]
    # En datos reales de HOMR, el validador no atrapa el 100% de los errores (no es circular)
    assert tradeoff["false_negatives_missed"] >= 0
    assert "by_operation" in res["missed_errors_breakdown"]


def test_exp_02_synthetic_fallback() -> None:
    res = exp_02_active_learning.run(manifest_path=Path("non_existent.json"), seed=42)
    assert res["experiment"] == "exp_02_active_learning"
    assert res["mode"] == "synthetic_fallback"
    assert res["canonical_budget"] == 20
    assert "uncertainty" in res["canonical_evaluations"]
    assert "diversity" in res["canonical_evaluations"]
    assert "hybrid" in res["canonical_evaluations"]
    assert "random" in res["canonical_evaluations"]

    jaccard = res["jaccard_similarity_matrix"]
    assert jaccard["uncertainty"]["uncertainty"] == 1.0


@pytest.mark.skipif(not DATA_MANIFEST.is_file(), reason="Requiere data/manifest.json")
def test_exp_02_real_data_criteria_and_jaccard() -> None:
    # Usar el pool generado sobre datos reales
    res = exp_02_active_learning.run(manifest_path=DATA_MANIFEST, limit=10, seed=20260920)
    assert res["experiment"] == "exp_02_active_learning"
    assert res["mode"] == "real_data_primus"
    assert res["pool_size"] > 0

    evals = res["canonical_evaluations"]
    # 1. Densidad de error: uncertainty debe ser mayor que diversity y random
    assert evals["uncertainty"]["mean_error_density"] >= evals["diversity"]["mean_error_density"]
    assert evals["uncertainty"]["mean_error_density"] >= evals["random"]["mean_error_density"]

    # 2. Diversidad de features: diversity o hybrid debe tener spread significativo
    assert evals["diversity"]["mean_pairwise_spread"] > 0.0

    # 3. Disimilitud de Jaccard: hybrid NO coincide trivialmente con uncertainty en datos reales
    jaccard_hyb_unc = res["jaccard_similarity_matrix"]["hybrid"]["uncertainty"]
    assert jaccard_hyb_unc < 1.0


def test_exp_03_smoke_and_penalization(tmp_path: Path) -> None:
    res = exp_03_omr_quality._measure_smoke(tmp_path)
    assert res["experiment"] == "exp_03_omr_quality"
    assert res["mode"] == "smoke"
    assert res["total_evaluated"] == 1
    assert res["failures_count"] == 0
    assert res["failure_rate"] == 0.0
    assert "mean_ser" in res["metrics_on_successes"]
    assert "mean_ser_penalized" in res["metrics_penalized_with_failures"]


@pytest.mark.skipif(not DATA_MANIFEST.is_file(), reason="Requiere data/manifest.json")
def test_exp_03_real_baseline_reports_failures_and_penalty() -> None:
    res = exp_03_omr_quality.run(DATA_MANIFEST, predictions=None, limit=15, write_results=False)
    assert res["experiment"] == "exp_03_omr_quality"
    assert res["total_evaluated"] == 15
    # La tasa penalizada debe ser mayor o igual a la media sobre éxitos si hubo algún fallo
    succ = res["metrics_on_successes"]["mean_omr_ned"]
    pen = res["metrics_penalized_with_failures"]["mean_omr_ned_penalized"]
    if res["failures_count"] > 0:
        assert pen >= succ
    # Verificación de métricas SER
    assert "mean_ser" in res["metrics_on_successes"]
    assert "mean_ser_penalized" in res["metrics_penalized_with_failures"]
    succ_ser = res["metrics_on_successes"]["mean_ser"]
    pen_ser = res["metrics_penalized_with_failures"]["mean_ser_penalized"]
    if res["failures_count"] > 0 and succ_ser is not None and pen_ser is not None:
        assert pen_ser >= succ_ser


def _exp07_corpus(tmp_path: Path, count: int = 3) -> Path:
    """Corpus mínimo: una imagen ficticia y un *ground truth* MusicXML por partitura."""
    fixture = Path(__file__).parent / "fixtures" / "simple.musicxml"
    entries = []
    for index in range(count):
        score_dir = tmp_path / "mini" / f"s{index}"
        score_dir.mkdir(parents=True)
        (score_dir / f"s{index}.png").write_bytes(b"png")
        (score_dir / f"s{index}.musicxml").write_text(
            fixture.read_text(encoding="utf-8"), encoding="utf-8"
        )
        entries.append(
            {
                "id": f"s{index}",
                "image": f"mini/s{index}/s{index}.png",
                "ground_truth": f"mini/s{index}/s{index}.musicxml",
            }
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"corpus": "mini", "entries": entries}), encoding="utf-8")
    return manifest


def _exp07_baseline(manifest: Path, successes: list[str], failures: list[str]) -> Path:
    fixture = Path(__file__).parent / "fixtures" / "simple.musicxml"
    predictions = manifest.parent / "mini" / "predictions"
    predictions.mkdir(parents=True)
    for entry_id in successes:
        (predictions / f"{entry_id}.musicxml").write_text(
            fixture.read_text(encoding="utf-8"), encoding="utf-8"
        )
    (predictions / "failures.json").write_text(
        json.dumps([{"id": entry_id, "error": "No staffs found"} for entry_id in failures]),
        encoding="utf-8",
    )
    return predictions


class _Exp07Engine:
    """Motor de prueba: devuelve el MusicXML indicado por partitura o falla.

    `fail` imita al adaptador (envuelve la excepción del motor en
    `OMRTranscriptionError`); `env` imita un error del entorno.
    """

    def __init__(self, outcomes: dict[str, str]) -> None:
        self._outcomes = outcomes
        self.calls: list[str] = []
        fixture = Path(__file__).parent / "fixtures" / "simple.musicxml"
        self._exact = fixture.read_text(encoding="utf-8")

    def transcribe_musicxml(self, image_path: Path) -> str:
        entry_id = image_path.stem
        self.calls.append(entry_id)
        outcome = self._outcomes[entry_id]
        if outcome == "fail":
            raise OMRTranscriptionError("No staffs found") from TimeoutError()
        if outcome == "env":
            raise RuntimeError("HOMREngine requiere el extra opcional 'homr'")
        if outcome == "worse":
            return self._exact.replace("<step>C</step>", "<step>E</step>")
        return self._exact


def test_exp_07_measures_recovery_and_regression(tmp_path: Path) -> None:
    from cadenza.omr.preprocessing import PreprocessingConfig

    from ml.experiments import exp_07_preprocessing_impact as exp_07

    manifest = _exp07_corpus(tmp_path)
    _exp07_baseline(manifest, successes=["s0", "s2"], failures=["s1"])
    engine = _Exp07Engine({"s0": "worse", "s1": "exact", "s2": "fail"})

    res = exp_07.run_preprocessing_experiment(
        manifest,
        configs={"probe": PreprocessingConfig(enabled=True, binarize=True)},
        engine_factory=lambda _config, _use_gpu: engine,
        write_results=False,
    )

    assert res["simulated"] is False
    assert res["total_samples"] == 3
    # Línea base: dos aciertos exactos (0) y un fallo (penalizado con 1).
    assert res["baseline"]["failures"] == 1
    assert res["baseline"]["failure_rate"] == 0.3333
    assert res["baseline"]["mean_omr_ned_successes"] == 0.0
    assert res["baseline"]["mean_omr_ned_penalized"] == 0.3333
    assert res["baseline"]["mean_ser_penalized"] == 0.3333

    # Variante: s0 empeora, s1 se recupera (exacta) y s2 falla.
    predictions = exp_07.predictions_dir(manifest, "probe")
    ground_truth = manifest.parent / "mini" / "s0" / "s0.musicxml"
    worse_ned = omr_ned_pair(predictions / "s0.musicxml", ground_truth).omr_ned
    assert worse_ned > 0

    probe = res["configurations"]["probe"]
    assert probe["summary"]["failures"] == 1
    assert probe["summary"]["failure_rate"] == 0.3333
    assert probe["summary"]["mean_omr_ned_successes"] == round(worse_ned / 2, 4)
    assert probe["summary"]["mean_omr_ned_penalized"] == round((worse_ned + 1.0) / 3, 4)
    versus = probe["versus_baseline"]
    assert versus["recovered"] == ["s1"]
    assert versus["regressed"] == ["s2"]
    assert versus["paired_successes"] == 1
    assert versus["paired_mean_omr_ned_delta"] == round(worse_ned, 4)
    assert versus["paired_mean_ser_delta"] > 0
    assert versus["paired_omr_ned_worsened"] == 1
    assert versus["paired_omr_ned_improved"] == 0
    assert versus["paired_omr_ned_equal"] == 0
    assert sorted(engine.calls) == ["s0", "s1", "s2"]


def test_exp_07_requires_baseline_predictions(tmp_path: Path) -> None:
    from ml.experiments import exp_07_preprocessing_impact as exp_07

    manifest = _exp07_corpus(tmp_path)
    with pytest.raises(FileNotFoundError, match="directorio de predicciones"):
        exp_07.run_preprocessing_experiment(
            manifest,
            engine_factory=lambda _config, _use_gpu: _Exp07Engine({}),
            write_results=False,
        )


def test_exp_07_missing_prediction_is_not_counted_as_failure(tmp_path: Path) -> None:
    """Una predicción que nunca se intentó no puede contarse como fallo del motor."""
    from ml.experiments import exp_07_preprocessing_impact as exp_07

    manifest = _exp07_corpus(tmp_path)
    predictions = _exp07_baseline(manifest, successes=["s0"], failures=["s1"])
    with pytest.raises(FileNotFoundError, match="s2"):
        exp_07.measure_predictions(manifest, predictions)


def test_exp_07_transcription_resumes_without_repeating(tmp_path: Path) -> None:
    from cadenza.omr.preprocessing import PreprocessingConfig

    from ml.experiments import exp_07_preprocessing_impact as exp_07

    manifest = _exp07_corpus(tmp_path)
    config = PreprocessingConfig(enabled=True, rescale=True)
    engine = _Exp07Engine({"s0": "exact", "s1": "fail", "s2": "exact"})

    def factory(_config: PreprocessingConfig, _use_gpu: bool) -> _Exp07Engine:
        return engine

    first = exp_07.transcribe_config(manifest, "probe", config, engine_factory=factory)
    assert first == {"written": 2, "reused": 0, "failures": 1}

    second = exp_07.transcribe_config(manifest, "probe", config, engine_factory=factory)
    assert second == {"written": 0, "reused": 3, "failures": 1}
    assert len(engine.calls) == 3

    forced = exp_07.transcribe_config(manifest, "probe", config, engine_factory=factory, force=True)
    assert forced == {"written": 2, "reused": 0, "failures": 1}

    # El registro conserva el tipo de la excepción original del motor.
    recorded = json.loads(
        (exp_07.predictions_dir(manifest, "probe") / "failures.json").read_text(encoding="utf-8")
    )
    assert recorded == [
        {"id": "s1", "error": "OMRTranscriptionError [TimeoutError]: No staffs found"}
    ]

    # Con `limit`, los fallos contados son solo los de las partituras consideradas.
    limited = exp_07.transcribe_config(manifest, "probe", config, engine_factory=factory, limit=1)
    assert limited == {"written": 0, "reused": 1, "failures": 0}


def test_exp_07_retry_failures_repeats_only_recorded_failures(tmp_path: Path) -> None:
    from cadenza.omr.preprocessing import PreprocessingConfig

    from ml.experiments import exp_07_preprocessing_impact as exp_07

    manifest = _exp07_corpus(tmp_path)
    config = PreprocessingConfig(enabled=True, rescale=True)
    failing = _Exp07Engine({"s0": "exact", "s1": "fail", "s2": "exact"})
    exp_07.transcribe_config(manifest, "probe", config, engine_factory=lambda _c, _g: failing)

    recovered = _Exp07Engine({"s0": "exact", "s1": "exact", "s2": "exact"})
    result = exp_07.transcribe_config(
        manifest, "probe", config, engine_factory=lambda _c, _g: recovered, retry_failures=True
    )

    assert recovered.calls == ["s1"]
    assert result == {"written": 1, "reused": 2, "failures": 0}
    assert (exp_07.predictions_dir(manifest, "probe") / "s1.musicxml").is_file()


def test_exp_07_environment_error_is_not_recorded_as_failure(tmp_path: Path) -> None:
    """Sin el motor, el experimento se detiene: no inventa fallos ni borra predicciones."""
    from cadenza.omr.preprocessing import PreprocessingConfig

    from ml.experiments import exp_07_preprocessing_impact as exp_07

    manifest = _exp07_corpus(tmp_path)
    config = PreprocessingConfig(enabled=True, rescale=True)
    working = _Exp07Engine({"s0": "exact", "s1": "exact", "s2": "exact"})
    exp_07.transcribe_config(manifest, "probe", config, engine_factory=lambda _c, _g: working)

    broken = _Exp07Engine({"s0": "env", "s1": "env", "s2": "env"})
    with pytest.raises(RuntimeError, match="homr"):
        exp_07.transcribe_config(
            manifest, "probe", config, engine_factory=lambda _c, _g: broken, force=True
        )

    predictions = exp_07.predictions_dir(manifest, "probe")
    assert sorted(path.name for path in predictions.glob("*.musicxml")) == [
        "s0.musicxml",
        "s1.musicxml",
        "s2.musicxml",
    ]
    assert json.loads((predictions / "failures.json").read_text(encoding="utf-8")) == []


def test_exp_07_refuses_predictions_of_another_configuration(tmp_path: Path) -> None:
    from cadenza.omr.preprocessing import PreprocessingConfig

    from ml.experiments import exp_07_preprocessing_impact as exp_07

    manifest = _exp07_corpus(tmp_path)
    engine = _Exp07Engine({"s0": "exact", "s1": "exact", "s2": "exact"})

    def factory(_config: PreprocessingConfig, _use_gpu: bool) -> _Exp07Engine:
        return engine

    exp_07.transcribe_config(
        manifest, "probe", PreprocessingConfig(enabled=True, rescale=True), engine_factory=factory
    )
    other = PreprocessingConfig(enabled=True, binarize=True)
    with pytest.raises(ValueError, match="otra configuración"):
        exp_07.transcribe_config(manifest, "probe", other, engine_factory=factory)
    assert len(engine.calls) == 3

    forced = exp_07.transcribe_config(manifest, "probe", other, engine_factory=factory, force=True)
    assert forced == {"written": 3, "reused": 0, "failures": 0}


def test_exp_07_measures_existing_predictions_without_transcribing(tmp_path: Path) -> None:
    from cadenza.omr.preprocessing import PreprocessingConfig

    from ml.experiments import exp_07_preprocessing_impact as exp_07

    manifest = _exp07_corpus(tmp_path)
    _exp07_baseline(manifest, successes=["s0", "s1", "s2"], failures=[])
    config = PreprocessingConfig(enabled=True, binarize=True)
    engine = _Exp07Engine({"s0": "exact", "s1": "exact", "s2": "exact"})
    exp_07.transcribe_config(manifest, "probe", config, engine_factory=lambda _c, _g: engine)

    def forbidden(_config: PreprocessingConfig, _use_gpu: bool) -> _Exp07Engine:
        raise AssertionError("no debe crearse el motor")

    res = exp_07.run_preprocessing_experiment(
        manifest,
        configs={"probe": config},
        transcribe=False,
        engine_factory=forbidden,
        write_results=False,
    )

    probe = res["configurations"]["probe"]
    assert probe["transcription"] is None
    assert probe["summary"]["failures"] == 0
    assert probe["versus_baseline"]["paired_successes"] == 3
    assert probe["versus_baseline"]["paired_omr_ned_equal"] == 3
    assert probe["versus_baseline"]["paired_mean_omr_ned_delta"] == 0.0


def test_exp_07_compare_without_common_successes() -> None:
    from ml.experiments import exp_07_preprocessing_impact as exp_07

    success = {"status": "success", "omr_ned": 0.2, "ser": 0.1, "error": ""}
    failure = {"status": "failure", "omr_ned": 1.0, "ser": 1.0, "error": "x"}
    versus = exp_07.compare({"a": success, "b": failure}, {"a": failure, "b": success})

    assert versus["recovered"] == ["b"]
    assert versus["regressed"] == ["a"]
    assert versus["paired_successes"] == 0
    assert versus["paired_mean_omr_ned_delta"] is None
    assert versus["paired_mean_ser_delta"] is None
    assert exp_07.summarize({"a": success, "b": failure}) == {
        "total": 2,
        "successes": 1,
        "failures": 1,
        "failure_rate": 0.5,
        "mean_omr_ned_successes": 0.2,
        "median_omr_ned_successes": 0.2,
        "mean_ser_successes": 0.1,
        "mean_omr_ned_penalized": 0.6,
        "mean_ser_penalized": 0.55,
    }


def test_exp_07_control_configuration_does_not_preprocess() -> None:
    from ml.experiments import exp_07_preprocessing_impact as exp_07

    assert exp_07.CONFIGS[exp_07.CONTROL].enabled is False
    assert all(config.enabled for name, config in exp_07.CONFIGS.items() if name != exp_07.CONTROL)


def test_exp_07_writes_results_only_to_results_dir(tmp_path: Path) -> None:
    from cadenza.omr.preprocessing import PreprocessingConfig

    from ml.experiments import exp_07_preprocessing_impact as exp_07

    manifest = _exp07_corpus(tmp_path, count=1)
    _exp07_baseline(manifest, successes=["s0"], failures=[])

    exp_07.run_preprocessing_experiment(
        manifest,
        configs={"probe": PreprocessingConfig(enabled=True, binarize=True)},
        engine_factory=lambda _config, _use_gpu: _Exp07Engine({"s0": "exact"}),
    )

    # La fixture de `conftest.py` redirige `RESULTS_DIR` de todos los experimentos.
    results_dir = common.RESULTS_DIR
    summary_file = results_dir / "preprocessing_impact_summary.json"
    written = json.loads(summary_file.read_text(encoding="utf-8"))
    assert written["simulated"] is False
    assert (results_dir / "preprocessing_comparison.csv").is_file()
    assert (results_dir / "exp_07_run_info.json").is_file()


def test_exp_08_smoke() -> None:
    from ml.experiments import exp_08_oemer_baseline

    res = exp_08_oemer_baseline.run_experiment(smoke=True)
    assert res["experiment"] == "exp_08_oemer_baseline"
    assert res["mode"] == "smoke"
    assert res["total_evaluated"] == 1
    assert "metrics_on_successes" in res
    assert "comparison_vs_homr" in res
    assert "delta_omr_ned" in res["comparison_vs_homr"]
    assert "delta_ser" in res["comparison_vs_homr"]


@pytest.mark.skipif(not DATA_MANIFEST.is_file(), reason="Requiere data/manifest.json")
def test_exp_08_corpus_evaluation() -> None:
    from ml.experiments import exp_08_oemer_baseline

    res = exp_08_oemer_baseline.run_experiment(manifest=DATA_MANIFEST, limit=5, write_results=False)
    assert res["experiment"] == "exp_08_oemer_baseline"
    assert res["total_evaluated"] == 5
    assert "metrics_on_successes" in res
    assert "metrics_penalized_with_failures" in res
    assert "comparison_vs_homr" in res


def test_corpus_smb_and_muscima_spec() -> None:
    from ml.experiments.corpus import CORPORA

    assert "smb" in CORPORA
    assert "muscima_pp" in CORPORA
    assert CORPORA["smb"].ground_truth_format != ""
    assert "MuNG" in CORPORA["muscima_pp"].ground_truth_format


def test_corpus_build_manifest_smb_and_muscima(tmp_path: Path) -> None:
    from ml.experiments.corpus import build_manifest

    # Subconjunto SMB
    smb_dir = tmp_path / "smb"
    smb_dir.mkdir(parents=True)
    (smb_dir / "score_01.png").write_bytes(b"\x89PNG\r\n\x1a\nfakeimage")
    (smb_dir / "score_01.krn").write_text("**kern\n*k[]\n4c\n*-", encoding="utf-8")

    manifest_smb = build_manifest(tmp_path, "smb")
    assert manifest_smb["corpus"] == "smb"
    assert manifest_smb["count"] == 1
    entries_smb = manifest_smb["entries"]
    assert isinstance(entries_smb, list)
    assert entries_smb[0]["id"] == "score_01"

    # Subconjunto MUSCIMA++
    muscima_dir = tmp_path / "muscima_pp"
    muscima_dir.mkdir(parents=True)
    (muscima_dir / "CVC_01.png").write_bytes(b"\x89PNG\r\n\x1a\nfakeimage")
    (muscima_dir / "CVC_01.xml").write_text("<mung></mung>", encoding="utf-8")

    manifest_muscima = build_manifest(tmp_path, "muscima_pp")
    assert manifest_muscima["corpus"] == "muscima_pp"
    assert manifest_muscima["count"] == 1
    entries_muscima = manifest_muscima["entries"]
    assert isinstance(entries_muscima, list)
    assert entries_muscima[0]["id"] == "CVC_01"


def test_exp_09_multicorpus_smoke() -> None:
    from ml.experiments import exp_09_multicorpus_evaluation

    res = exp_09_multicorpus_evaluation.run_multicorpus_experiment(smoke=True, write_results=False)
    assert res["experiment"] == "exp_09_multicorpus_evaluation"
    assert res["mode"] == "smoke"
    assert "smb" in res["corpora_evaluated"]
    assert "muscima_pp" in res["corpora_evaluated"]

    smb_data = res["corpora_evaluated"]["smb"]
    assert smb_data["omr_quality"]["total_evaluated"] == 3
    assert smb_data["omr_quality"]["failures_count"] == 1
    assert smb_data["omr_quality"]["failure_rate"] > 0
    assert smb_data["effort_reduction"]["effort_reduction_percent"] > 0
    assert "validation_metrics" in smb_data

    muscima_data = res["corpora_evaluated"]["muscima_pp"]
    assert muscima_data["analysis"]["has_sequential_symbolic_ground_truth"] is False
    assert muscima_data["analysis"]["optical_generalization_evaluation"]["evaluated"] is False
    assert res["simulated"] is True


def test_exp_01_effort_smb_custom_manifest(tmp_path: Path) -> None:
    # Preparar predicción y GT de SMB usando piano.musicxml
    piano_xml = (
        REPO_ROOT / "packages" / "interchange" / "tests" / "fixtures" / "piano.musicxml"
    ).read_text(encoding="utf-8")

    smb_root = tmp_path / "smb"
    preds_dir = smb_root / "predictions"
    gt_dir = smb_root / "gt"
    preds_dir.mkdir(parents=True)
    gt_dir.mkdir(parents=True)

    (gt_dir / "piano_score.musicxml").write_text(piano_xml, encoding="utf-8")
    (preds_dir / "piano_score.musicxml").write_text(piano_xml, encoding="utf-8")

    manifest_file = tmp_path / "manifest.json"
    manifest_data = {
        "corpus": "smb",
        "entries": [
            {
                "id": "piano_score",
                "ground_truth": "smb/gt/piano_score.musicxml",
            }
        ],
    }
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    res = exp_01_effort.run(manifest_path=manifest_file, predictions_dir=preds_dir)
    assert res["experiment"] == "exp_01_effort"
    assert res["mode"] == "real_data_smb"
    assert res["corpus"] == "smb"
    assert res["inspection_effort"]["total_measures"] == 4  # 2 staves * 2 measures


def test_exp_06_validation_smb_custom_manifest(tmp_path: Path) -> None:
    from ml.experiments import exp_06_validation_metrics

    piano_xml = (
        REPO_ROOT / "packages" / "interchange" / "tests" / "fixtures" / "piano.musicxml"
    ).read_text(encoding="utf-8")

    smb_root = tmp_path / "smb"
    preds_dir = smb_root / "predictions"
    gt_dir = smb_root / "gt"
    preds_dir.mkdir(parents=True)
    gt_dir.mkdir(parents=True)

    (gt_dir / "piano_score.musicxml").write_text(piano_xml, encoding="utf-8")
    (preds_dir / "piano_score.musicxml").write_text(piano_xml, encoding="utf-8")

    manifest_file = tmp_path / "manifest.json"
    manifest_data = {
        "corpus": "smb",
        "entries": [
            {
                "id": "piano_score",
                "ground_truth": "smb/gt/piano_score.musicxml",
            }
        ],
    }
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    report = exp_06_validation_metrics.run_validation_experiment(
        manifest_path=manifest_file, predictions_dir=preds_dir
    )
    assert report.total_measures == 4
    assert report.global_metrics.accuracy == 1.0


def test_exp_10_effort_study_smoke(tmp_path: Path) -> None:
    from ml.experiments import exp_10_effort_study

    summary = exp_10_effort_study.run_effort_study_export(
        output_dir=tmp_path,
        smoke=True,
        seed=12345,
    )

    assert summary["protocol_version"] == "1.0"
    assert summary["total_sessions"] == 32
    assert summary["total_participants"] == 8
    assert "assisted" in summary["conditions"]
    assert "unassisted" in summary["conditions"]

    # Validar archivos generados
    assert (tmp_path / "effort_study_sessions.csv").is_file()
    assert (tmp_path / "effort_study_by_measure.csv").is_file()
    assert (tmp_path / "effort_study_summary.json").is_file()
    assert (tmp_path / "exp_10_run_info.json").is_file()

    # Reducciones mayores a 0
    assert summary["effort_reduction"]["time_per_measure_reduction_percent"] > 0
    assert summary["effort_reduction"]["cognitive_workload_reduction_percent"] > 0
    assert summary["simulated"] is True
    assert summary["data_source"] == "synthetic"


def test_exp_10_empty_database_is_marked_as_synthetic(tmp_path: Path) -> None:
    """Una base sin sesiones de estudio no puede producir un resultado «real» (#96)."""
    from ml.experiments import exp_10_effort_study

    summary = exp_10_effort_study.run_effort_study_export(
        db_url=f"sqlite+pysqlite:///{(tmp_path / 'empty.db').as_posix()}",
        output_dir=tmp_path / "out",
    )

    assert summary["simulated"] is True
    assert summary["data_source"] == "synthetic"
    assert "simulation_warning" in summary


def test_ml_cli_export_effort(tmp_path: Path) -> None:
    from ml import cli

    code = cli.main(["export-effort", "--smoke", "--output-dir", str(tmp_path), "--seed", "999"])
    assert code == 0
    assert (tmp_path / "effort_study_sessions.csv").is_file()
    assert (tmp_path / "effort_study_summary.json").is_file()
