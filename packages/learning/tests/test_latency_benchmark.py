"""Tests del benchmark de latencia de OMR (#37, #97, D42).

El benchmark mide un motor real; aquí se comprueba el arnés de medición con un motor
de prueba inyectado, sin cifras escritas a mano.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from ml.experiments.exp_11_latency_benchmark import (
    ASYNC_REQUIRED,
    SYNC_SUFFICIENT,
    SYNC_WITH_WARMUP,
    compose_page,
    compute_latency_stats,
    evaluate_decision,
    run_benchmark,
)


class _StubEngine:
    """Motor de prueba: cuenta llamadas y falla en las imágenes indicadas."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[Path] = []
        self._fail_on = fail_on

    def transcribe_musicxml(self, image_path: Path) -> str:
        self.calls.append(image_path)
        if self._fail_on is not None and self._fail_on in image_path.name:
            raise RuntimeError("No staffs found")
        return "<score-partwise/>"


def _manifest(tmp_path: Path, count: int = 4) -> Path:
    entries = []
    for index in range(count):
        image = tmp_path / f"staff_{index}.png"
        Image.new("L", (200 + 10 * index, 40), color=255).save(image)
        entries.append({"id": f"staff_{index}", "image": image.name})
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return manifest


def test_compute_latency_stats_empty() -> None:
    stats = compute_latency_stats([])
    assert stats.count == 0
    assert stats.mean_ms == 0.0
    assert stats.client_timeout_margin_percent == 100.0


def test_compute_latency_stats_with_data() -> None:
    stats = compute_latency_stats([1000.0, 2000.0, 3000.0, 4000.0, 5000.0], timeout_s=30.0)
    assert stats.count == 5
    assert stats.mean_ms == 3000.0
    assert stats.median_ms == 3000.0
    assert stats.min_ms == 1000.0
    assert stats.max_ms == 5000.0
    assert stats.max_s == 5.0
    assert 83.0 <= stats.client_timeout_margin_percent <= 84.0


def test_compute_latency_stats_single_value_percentiles() -> None:
    stats = compute_latency_stats([1500.0])
    assert stats.p90_ms == 1500.0
    assert stats.p95_ms == 1500.0


@pytest.mark.parametrize(
    ("max_warm_ms", "max_cold_ms", "expected"),
    [
        (5_000.0, 8_000.0, SYNC_SUFFICIENT),
        (5_000.0, 45_000.0, SYNC_WITH_WARMUP),
        (31_000.0, 45_000.0, ASYNC_REQUIRED),
        (30_000.0, 1_000.0, ASYNC_REQUIRED),
    ],
)
def test_evaluate_decision_rule(max_warm_ms: float, max_cold_ms: float, expected: str) -> None:
    assert evaluate_decision(max_warm_ms, max_cold_ms, timeout_s=30.0) == expected


def test_compose_page_stacks_staves(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path, count=3)
    images = [tmp_path / entry["image"] for entry in json.loads(manifest.read_text())["entries"]]
    page = compose_page(images, tmp_path / "page.png", gap=10, margin=5)
    with Image.open(page) as composed:
        assert composed.width == 220 + 2 * 5
        assert composed.height == 3 * (40 + 10) + 2 * 5


def test_run_benchmark_measures_injected_engine(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    engine = _StubEngine()
    out = tmp_path / "out"

    summary = run_benchmark(
        device="cpu",
        manifest=manifest,
        output_dir=out,
        incipits=2,
        staves=(2, 4),
        runs=3,
        engine_factory=lambda _use_gpu: engine,
    )

    assert summary["simulated"] is False
    measured = summary["devices"]["cpu"]
    assert measured["cold_start_ms"] is not None
    configs = measured["configurations"]
    assert set(configs) == {"incipit_1_staff", "page_2_staves", "page_4_staves"}
    assert configs["incipit_1_staff"]["stats"]["count"] == 2 * 3
    assert configs["page_4_staves"]["stats"]["count"] == 3
    # 1 llamada en frío + 2 incipits x 3 + 2 páginas x 3
    assert len(engine.calls) == 1 + 6 + 6
    assert summary["architectural_evaluation"]["recommendation"] == SYNC_SUFFICIENT

    written = json.loads((out / "latency_benchmark_summary.json").read_text(encoding="utf-8"))
    assert written["simulated"] is False
    assert (out / "exp_11_run_info.json").is_file()


def test_run_benchmark_merges_devices_and_discards_simulated(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "latency_benchmark_summary.json").write_text(
        json.dumps({"simulated": True, "devices": {"gpu": {"max_warm_ms": 1.0}}}),
        encoding="utf-8",
    )

    def factory(_use_gpu: bool) -> _StubEngine:
        return _StubEngine()

    first = run_benchmark(
        device="cpu",
        manifest=manifest,
        output_dir=out,
        incipits=1,
        staves=(2,),
        runs=1,
        engine_factory=factory,
    )
    assert set(first["devices"]) == {"cpu"}

    second = run_benchmark(
        device="gpu",
        manifest=manifest,
        output_dir=out,
        incipits=1,
        staves=(2,),
        runs=1,
        engine_factory=factory,
    )
    assert set(second["devices"]) == {"cpu", "gpu"}


def test_run_benchmark_accumulates_samples_per_device(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    out = tmp_path / "out"

    def factory(_use_gpu: bool) -> _StubEngine:
        return _StubEngine()

    def measure(reset: bool = False) -> dict[str, Any]:
        summary = run_benchmark(
            device="cpu",
            manifest=manifest,
            output_dir=out,
            incipits=1,
            staves=(2,),
            runs=2,
            engine_factory=factory,
            reset=reset,
        )
        measured: dict[str, Any] = summary["devices"]["cpu"]
        return measured

    measure()
    second = measure()
    assert second["invocations"] == 2
    assert len(second["cold_start_samples_ms"]) == 2
    configs = second["configurations"]
    assert configs["incipit_1_staff"]["stats"]["count"] == 4

    fresh = measure(reset=True)
    assert fresh["invocations"] == 1
    assert len(fresh["cold_start_samples_ms"]) == 1


def test_run_benchmark_counts_engine_failures(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    summary = run_benchmark(
        device="cpu",
        manifest=manifest,
        output_dir=tmp_path / "out",
        incipits=2,
        staves=(2,),
        runs=2,
        engine_factory=lambda _use_gpu: _StubEngine(fail_on="staff_1"),
    )
    incipits = summary["devices"]["cpu"]["configurations"]["incipit_1_staff"]
    assert incipits["failures"] == 2
    assert incipits["stats"]["count"] == 2


def test_run_benchmark_requires_corpus(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_benchmark(
            device="cpu",
            manifest=tmp_path / "missing.json",
            output_dir=tmp_path / "out",
            engine_factory=lambda _use_gpu: _StubEngine(),
        )


def test_run_benchmark_rejects_unknown_device(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="device"):
        run_benchmark(device="tpu", manifest=_manifest(tmp_path), output_dir=tmp_path / "out")
