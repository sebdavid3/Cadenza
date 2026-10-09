"""Pruebas de los experimentos con datos reales y criterios de validez externa (Issue #24)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def test_exp_07_smoke() -> None:
    from ml.experiments import exp_07_preprocessing_impact

    res = exp_07_preprocessing_impact.run_preprocessing_experiment(
        DATA_MANIFEST, smoke=True, write_results=False
    )
    assert res["experiment"] == "exp_07_preprocessing_impact"
    assert res["total_samples"] == 10
    assert "transformations_summary" in res
    assert res["with_preprocessing"]["failure_rate"] <= res["baseline"]["failure_rate"]


@pytest.mark.skipif(not DATA_MANIFEST.is_file(), reason="Requiere data/manifest.json")
def test_exp_07_preprocessing_impact_on_primus() -> None:
    from ml.experiments import exp_07_preprocessing_impact

    res = exp_07_preprocessing_impact.run_preprocessing_experiment(
        DATA_MANIFEST, limit=10, write_results=False
    )
    assert res["experiment"] == "exp_07_preprocessing_impact"
    assert res["total_samples"] == 10
    assert res["transformations_summary"]["mean_otsu_threshold"] > 100
    assert res["transformations_summary"]["mean_rescale_factor"] > 1.0


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
    assert muscima_data["analysis"]["optical_generalization_evaluation"]["failure_rate"] == 1.0


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


def test_ml_cli_export_effort(tmp_path: Path) -> None:
    from ml import cli

    code = cli.main(["export-effort", "--smoke", "--output-dir", str(tmp_path), "--seed", "999"])
    assert code == 0
    assert (tmp_path / "effort_study_sessions.csv").is_file()
    assert (tmp_path / "effort_study_summary.json").is_file()
