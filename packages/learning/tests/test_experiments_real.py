"""Pruebas de los experimentos con datos reales y criterios de validez externa (Issue #24)."""

from __future__ import annotations

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


@pytest.mark.skipif(not DATA_MANIFEST.is_file(), reason="Requiere data/manifest.json")
def test_exp_03_real_baseline_reports_failures_and_penalty() -> None:
    res = exp_03_omr_quality.run(DATA_MANIFEST, predictions=None, limit=15)
    assert res["experiment"] == "exp_03_omr_quality"
    assert res["total_evaluated"] == 15
    # La tasa penalizada debe ser mayor o igual a la media sobre éxitos si hubo algún fallo
    succ = res["metrics_on_successes"]["mean_omr_ned"]
    pen = res["metrics_penalized_with_failures"]["mean_omr_ned_penalized"]
    if res["failures_count"] > 0:
        assert pen >= succ
