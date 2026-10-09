"""Tests unitarios para el benchmark de latencia de OMR (#37, D42)."""

import json
from pathlib import Path

from ml.experiments.exp_11_latency_benchmark import compute_latency_stats, run_benchmark


def test_compute_latency_stats_empty() -> None:
    stats = compute_latency_stats([])
    assert stats.count == 0
    assert stats.mean_ms == 0.0
    assert stats.client_timeout_margin_percent == 100.0


def test_compute_latency_stats_with_data() -> None:
    # 5 duraciones en ms: 1000, 2000, 3000, 4000, 5000 (máx 5s frente a 30s)
    data = [1000.0, 2000.0, 3000.0, 4000.0, 5000.0]
    stats = compute_latency_stats(data, timeout_s=30.0)
    assert stats.count == 5
    assert stats.mean_ms == 3000.0
    assert stats.median_ms == 3000.0
    assert stats.min_ms == 1000.0
    assert stats.max_ms == 5000.0
    assert stats.max_s == 5.0
    # Margen: (1 - 5/30) * 100 = 83.33%
    assert 83.0 <= stats.client_timeout_margin_percent <= 84.0


def test_run_benchmark_smoke(tmp_path: Path) -> None:
    res = run_benchmark(smoke=True, output_dir=tmp_path)
    assert res["smoke_mode"] is True
    assert "incipit_1_staff" in res["configurations"]
    assert "full_page_2_staves" in res["configurations"]

    eval_data = res["architectural_evaluation"]
    assert eval_data["recommendation"] == "SYNCHRONOUS_SUFFICIENT"
    assert eval_data["worst_case_margin_percent"] > 50.0

    # Comprobar que los archivos se crearon
    summary_file = tmp_path / "latency_benchmark_summary.json"
    run_info_file = tmp_path / "exp_11_run_info.json"
    assert summary_file.exists()
    assert run_info_file.exists()

    with summary_file.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["smoke_mode"] is True
