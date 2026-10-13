"""Tests del benchmark de latencia de OMR (#37, #97, D42).

El benchmark mide un motor real. Aquí se comprueba el arnés de medición con un motor
de prueba y un reloj manual: cada duración que aparece en el resumen se contrasta con
la que el motor «tardó», de modo que un arnés que no cronometre no pasa.
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from cadenza.omr import OMRTranscriptionError
from PIL import Image

from ml.experiments import exp_11_latency_benchmark as exp_11
from ml.experiments.exp_11_latency_benchmark import (
    ASYNC_REQUIRED,
    SYNC_SUFFICIENT,
    SYNC_WITH_WARMUP,
    compose_page,
    compute_latency_stats,
    evaluate_decision,
    run_benchmark,
)


class _ManualClock:
    """Reloj que solo avanza cuando el motor de prueba «trabaja»."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _StubEngine:
    """Motor de prueba: tarda lo programado y falla en las imágenes indicadas."""

    def __init__(
        self,
        clock: _ManualClock | None = None,
        durations_ms: list[float] | None = None,
        fail_on: str | None = None,
        error: type[Exception] = OMRTranscriptionError,
    ) -> None:
        self.calls: list[Path] = []
        self._clock = clock
        self._durations: Iterator[float] = iter(durations_ms or [])
        self._fail_on = fail_on
        self._error = error

    def transcribe_musicxml(self, image_path: Path) -> str:
        self.calls.append(image_path)
        if self._fail_on is not None and self._fail_on in image_path.name:
            raise self._error("No staffs found")
        if self._clock is not None:
            self._clock.now += next(self._durations) / 1000.0
        return "<score-partwise/>"


def _manifest(tmp_path: Path, count: int = 4) -> Path:
    entries = []
    for index in range(count):
        image = tmp_path / f"staff_{index}.png"
        Image.new("L", (200 + 10 * index, 40), color=0).save(image)
        entries.append({"id": f"staff_{index}", "image": image.name})
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return manifest


def _timed_run(tmp_path: Path, durations_ms: list[float], **kwargs: Any) -> dict[str, Any]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    clock = _ManualClock()
    engine = _StubEngine(clock, durations_ms)
    return run_benchmark(
        device="cpu",
        manifest=_manifest(tmp_path),
        output_dir=tmp_path / "out",
        engine_factory=lambda _use_gpu: engine,
        clock=clock,
        **kwargs,
    )


def test_compute_latency_stats_empty_has_no_margin() -> None:
    stats = compute_latency_stats([])
    assert stats.count == 0
    assert stats.mean_ms == 0.0
    # Sin muestras no se afirma ningún margen frente al timeout.
    assert stats.client_timeout_margin_percent is None


def test_compute_latency_stats_with_data() -> None:
    stats = compute_latency_stats([5000.0, 1000.0, 3000.0, 2000.0, 4000.0], timeout_s=30.0)
    assert stats.count == 5
    assert stats.mean_ms == 3000.0
    assert stats.median_ms == 3000.0
    assert stats.min_ms == 1000.0
    assert stats.max_ms == 5000.0
    assert stats.max_s == 5.0
    assert stats.p90_ms == 4600.0
    assert stats.p95_ms == 4800.0
    assert stats.std_ms == 1581.14
    assert stats.client_timeout_margin_percent == 83.33


def test_compute_latency_stats_single_value_percentiles() -> None:
    stats = compute_latency_stats([1500.0])
    assert stats.p90_ms == 1500.0
    assert stats.p95_ms == 1500.0
    assert stats.std_ms == 0.0


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
        # Fondo blanco y cada pentagrama (negro) en su franja.
        assert composed.getpixel((0, 0)) == 255
        for index in range(3):
            assert composed.getpixel((5, 5 + 5 + index * 50)) == 0


def test_run_benchmark_reports_the_measured_durations(tmp_path: Path) -> None:
    cold = [5000.0]
    incipits = [100.0, 200.0, 300.0, 400.0, 500.0, 600.0]
    page_2 = [1000.0, 1100.0, 1200.0]
    page_4 = [2000.0, 2100.0, 2200.0]

    summary = _timed_run(
        tmp_path, cold + incipits + page_2 + page_4, incipits=2, staves=(2, 4), runs=3
    )

    assert summary["simulated"] is False
    measured = summary["devices"]["cpu"]
    assert measured["cold_start_samples_ms"] == cold
    assert measured["cold_start_failures"] == 0
    configs = measured["configurations"]
    assert configs["incipit_1_staff"]["warm_ms"] == incipits
    assert configs["page_2_staves"]["warm_ms"] == page_2
    assert configs["page_4_staves"]["warm_ms"] == page_4
    assert configs["incipit_1_staff"]["stats"]["median_ms"] == 350.0
    assert measured["max_warm_ms"] == 2200.0

    evaluation = summary["architectural_evaluation"]
    assert evaluation["max_warm_ms"] == 2200.0
    assert evaluation["max_cold_start_ms"] == 5000.0
    assert evaluation["recommendation"] == SYNC_SUFFICIENT

    out = tmp_path / "out"
    written = json.loads((out / "latency_benchmark_summary.json").read_text(encoding="utf-8"))
    assert written["devices"]["cpu"]["configurations"]["page_4_staves"]["warm_ms"] == page_4
    assert (out / "exp_11_run_info.json").is_file()


def test_run_benchmark_verdict_follows_the_measurements(tmp_path: Path) -> None:
    slow_warm = _timed_run(
        tmp_path / "a", [1000.0, 100.0, 31_000.0], incipits=1, staves=(2,), runs=1
    )
    assert slow_warm["architectural_evaluation"]["recommendation"] == ASYNC_REQUIRED

    slow_cold = _timed_run(
        tmp_path / "b", [45_000.0, 100.0, 200.0], incipits=1, staves=(2,), runs=1
    )
    assert slow_cold["architectural_evaluation"]["recommendation"] == SYNC_WITH_WARMUP


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


def test_run_benchmark_accumulates_samples_of_the_same_protocol(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    out = tmp_path / "out"

    def measure(runs: int = 2, reset: bool = False) -> dict[str, Any]:
        summary = run_benchmark(
            device="cpu",
            manifest=manifest,
            output_dir=out,
            incipits=1,
            staves=(2,),
            runs=runs,
            engine_factory=lambda _use_gpu: _StubEngine(),
            reset=reset,
        )
        measured: dict[str, Any] = summary["devices"]["cpu"]
        return measured

    measure()
    second = measure()
    assert second["invocations"] == 2
    assert len(second["cold_start_samples_ms"]) == 2
    assert second["configurations"]["incipit_1_staff"]["stats"]["count"] == 4

    # Otro protocolo no es comparable: no se mezclan las muestras.
    other_protocol = measure(runs=3)
    assert other_protocol["invocations"] == 1
    assert other_protocol["configurations"]["incipit_1_staff"]["stats"]["count"] == 3

    fresh = measure(runs=3, reset=True)
    assert fresh["invocations"] == 1
    assert len(fresh["cold_start_samples_ms"]) == 1


def test_run_benchmark_counts_transcription_failures(tmp_path: Path) -> None:
    summary = run_benchmark(
        device="cpu",
        manifest=_manifest(tmp_path),
        output_dir=tmp_path / "out",
        incipits=2,
        staves=(2,),
        runs=2,
        engine_factory=lambda _use_gpu: _StubEngine(fail_on="staff_1"),
    )
    measured = summary["devices"]["cpu"]
    incipits = measured["configurations"]["incipit_1_staff"]
    assert incipits["failures"] == 2
    assert incipits["stats"]["count"] == 2
    assert measured["cold_start_failures"] == 0


def test_run_benchmark_keeps_a_failed_cold_call_apart(tmp_path: Path) -> None:
    summary = run_benchmark(
        device="cpu",
        manifest=_manifest(tmp_path),
        output_dir=tmp_path / "out",
        incipits=2,
        staves=(2,),
        runs=2,
        engine_factory=lambda _use_gpu: _StubEngine(fail_on="staff_0"),
    )
    measured = summary["devices"]["cpu"]
    assert measured["cold_start_samples_ms"] == []
    assert measured["cold_start_failures"] == 1
    assert measured["cold_start_ms"] is None
    # Solo los dos intentos en caliente sobre la imagen que falla.
    assert measured["configurations"]["incipit_1_staff"]["failures"] == 2
    assert summary["architectural_evaluation"]["max_cold_start_ms"] is None


def test_run_benchmark_without_any_measurement_fails_and_writes_nothing(tmp_path: Path) -> None:
    out = tmp_path / "out"
    with pytest.raises(RuntimeError, match="ninguna medición"):
        run_benchmark(
            device="cpu",
            manifest=_manifest(tmp_path),
            output_dir=out,
            incipits=1,
            staves=(2,),
            runs=1,
            engine_factory=lambda _use_gpu: _StubEngine(fail_on="."),
        )
    assert not (out / "latency_benchmark_summary.json").exists()


def test_run_benchmark_does_not_swallow_unexpected_engine_errors(tmp_path: Path) -> None:
    """Un motor ausente o roto no es un «fallo de transcripción»: debe detener el benchmark."""
    with pytest.raises(RuntimeError, match="No staffs found"):
        run_benchmark(
            device="cpu",
            manifest=_manifest(tmp_path),
            output_dir=tmp_path / "out",
            incipits=1,
            staves=(2,),
            runs=1,
            engine_factory=lambda _use_gpu: _StubEngine(fail_on="staff_0", error=RuntimeError),
        )


def test_default_engine_factory_requires_homr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: None)
    with pytest.raises(RuntimeError, match="homr"):
        exp_11._default_engine_factory(False)


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
