"""Experimento 11: latencia real de transcripción con HOMR (#37, #97, D42).

Mide el tiempo de `HOMREngine.transcribe_musicxml` en un dispositivo (CPU o GPU) sobre:

1. Incipits de un pentagrama tomados del manifiesto del corpus (PrIMuS).
2. Páginas de N pentagramas compuestas apilando las N primeras imágenes del manifiesto.
   No hay un corpus de página completa descargado: la composición es sintética, la
   inferencia es real.

Se cronometra solo la llamada al motor. Una petición `POST /transcribe` añade además la
conversión al modelo interno, la validación y la persistencia, de modo que estas cifras
son una cota inferior de la latencia que ve el cliente.

Para cada dispositivo registra por separado el arranque en frío (primera llamada del
proceso) y las repeticiones en caliente. Cada dispositivo se mide en una ejecución
distinta del script; ejecuciones sucesivas del mismo dispositivo acumulan sus muestras
(una muestra de arranque en frío por proceso) salvo que se pase `--reset`.

No hay valores de reserva: sin el extra `homr`, sin el corpus o sin ninguna medición
válida el script termina con un error en lugar de inventar cifras o emitir un veredicto.

Salidas:
- `results/latency_benchmark_summary.json`
- `results/exp_11_run_info.json`
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Protocol

from cadenza.omr import OMRTranscriptionError
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.experiments.common import (  # noqa: E402
    DATA_DIR,
    DEFAULT_SEED,
    RESULTS_DIR,
    get_run_info,
)

SUMMARY_FILENAME = "latency_benchmark_summary.json"
DEFAULT_TIMEOUT_S = 30.0

# Regla de decisión fijada antes de medir (ADR-0016).
SYNC_SUFFICIENT = "SYNCHRONOUS_SUFFICIENT"
SYNC_WITH_WARMUP = "SYNCHRONOUS_WITH_WARMUP"
ASYNC_REQUIRED = "ASYNCHRONOUS_REQUIRED"


class Transcriber(Protocol):
    """Lo único que el benchmark necesita de un motor OMR."""

    def transcribe_musicxml(self, image_path: Path) -> str: ...


EngineFactory = Callable[[bool], Transcriber]


@dataclass(frozen=True)
class LatencyStats:
    """Métricas estadísticas de latencia de inferencia en milisegundos y segundos."""

    count: int
    mean_ms: float
    std_ms: float
    median_ms: float
    p90_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float
    mean_s: float
    max_s: float
    # `None` cuando no hay muestras: sin datos no hay margen que afirmar.
    client_timeout_margin_percent: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_latency_stats(
    durations_ms: list[float], timeout_s: float = DEFAULT_TIMEOUT_S
) -> LatencyStats:
    """Calcula las métricas de distribución de latencia y margen de seguridad de timeout."""
    if not durations_ms:
        return LatencyStats(
            count=0,
            mean_ms=0.0,
            std_ms=0.0,
            median_ms=0.0,
            p90_ms=0.0,
            p95_ms=0.0,
            min_ms=0.0,
            max_ms=0.0,
            mean_s=0.0,
            max_s=0.0,
            client_timeout_margin_percent=None,
        )

    count = len(durations_ms)
    sorted_ms = sorted(durations_ms)
    mean_val = float(statistics.mean(sorted_ms))
    std_val = float(statistics.stdev(sorted_ms)) if count > 1 else 0.0
    median_val = float(statistics.median(sorted_ms))

    def percentile(p: float) -> float:
        k = (len(sorted_ms) - 1) * (p / 100.0)
        f = int(k)
        c = min(f + 1, len(sorted_ms) - 1)
        if f == c:
            return float(sorted_ms[f])
        return float(sorted_ms[f] * (c - k) + sorted_ms[c] * (k - f))

    max_val = float(sorted_ms[-1])
    max_s = max_val / 1000.0
    margin_percent = max(0.0, (1.0 - (max_s / timeout_s)) * 100.0)

    return LatencyStats(
        count=count,
        mean_ms=round(mean_val, 2),
        std_ms=round(std_val, 2),
        median_ms=round(median_val, 2),
        p90_ms=round(percentile(90.0), 2),
        p95_ms=round(percentile(95.0), 2),
        min_ms=round(float(sorted_ms[0]), 2),
        max_ms=round(max_val, 2),
        mean_s=round(mean_val / 1000.0, 3),
        max_s=round(max_s, 3),
        client_timeout_margin_percent=round(margin_percent, 2),
    )


def evaluate_decision(
    max_warm_ms: float, max_cold_ms: float, timeout_s: float = DEFAULT_TIMEOUT_S
) -> str:
    """Regla de decisión síncrono/asíncrono, definida antes de medir.

    - Si alguna petición en caliente alcanza el timeout, el modelo síncrono no sirve.
    - Si solo lo alcanza el arranque en frío, basta con precalentar el motor al iniciar.
    - En otro caso, el modelo síncrono es suficiente.
    """
    timeout_ms = timeout_s * 1000.0
    if max_warm_ms >= timeout_ms:
        return ASYNC_REQUIRED
    if max_cold_ms >= timeout_ms:
        return SYNC_WITH_WARMUP
    return SYNC_SUFFICIENT


def compose_page(
    image_paths: Sequence[Path], output: Path, *, gap: int = 60, margin: int = 80
) -> Path:
    """Compone una página apilando en vertical las imágenes de varios pentagramas."""
    if not image_paths:
        raise ValueError("se necesita al menos una imagen para componer la página")
    staves = [Image.open(path).convert("L") for path in image_paths]
    width = max(staff.width for staff in staves) + 2 * margin
    height = sum(staff.height + gap for staff in staves) + 2 * margin
    page = Image.new("L", (width, height), color=255)
    offset = margin
    for staff in staves:
        page.paste(staff, (margin, offset + gap // 2))
        offset += staff.height + gap
    page.save(output)
    return output


Clock = Callable[[], float]


def time_call(engine: Transcriber, image: Path, clock: Clock = time.perf_counter) -> float:
    """Devuelve la duración en milisegundos de una transcripción."""
    start = clock()
    engine.transcribe_musicxml(image)
    return (clock() - start) * 1000.0


def _default_engine_factory(use_gpu: bool) -> Transcriber:
    from cadenza.omr import HOMREngine, get_effective_device

    if importlib.util.find_spec("homr") is None:
        raise RuntimeError(
            "El benchmark necesita el motor real: instala el extra `homr` (ver README). "
            "No hay valores de reserva."
        )
    if use_gpu and get_effective_device(True) != "cuda":
        raise RuntimeError(
            "Se pidió medir en GPU pero onnxruntime no expone CUDAExecutionProvider. "
            "Instala onnxruntime-gpu (ver README) o mide con --device cpu."
        )
    return HOMREngine(use_gpu=use_gpu)


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _gpu_name() -> str | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    name = out.stdout.strip().splitlines()
    return name[0] if out.returncode == 0 and name else None


def describe_environment(device: str) -> dict[str, Any]:
    """Describe el hardware y las versiones con las que se midió."""
    return {
        "device": device,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "gpu": _gpu_name() if device == "gpu" else None,
        "python": platform.python_version(),
        "homr": _package_version("homr"),
        "onnxruntime": _package_version("onnxruntime-gpu") or _package_version("onnxruntime"),
    }


def _load_images(manifest: Path, needed: int) -> list[Path]:
    if not manifest.is_file():
        raise FileNotFoundError(f"No existe el manifiesto del corpus: {manifest}")
    entries = json.loads(manifest.read_text(encoding="utf-8")).get("entries", [])
    images = [manifest.parent / entry["image"] for entry in entries]
    images = [image for image in images if image.is_file()]
    if len(images) < needed:
        raise FileNotFoundError(
            f"El manifiesto {manifest} solo tiene {len(images)} imágenes disponibles; "
            f"el benchmark necesita {needed}."
        )
    return images[:needed]


def _measure(engine: Transcriber, image: Path, runs: int, clock: Clock) -> tuple[list[float], int]:
    durations: list[float] = []
    failures = 0
    for _ in range(runs):
        try:
            durations.append(round(time_call(engine, image, clock), 2))
        except OMRTranscriptionError:
            # El motor no pudo transcribir la imagen (p. ej. "No staffs found"): no es
            # una latencia válida. Cualquier otro error (motor ausente, entorno roto)
            # se propaga y detiene el benchmark.
            failures += 1
    return durations, failures


def measure_device(
    *,
    device: str,
    images: Sequence[Path],
    incipits: int,
    staves: Sequence[int],
    runs: int,
    engine_factory: EngineFactory,
    work_dir: Path,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    clock: Clock = time.perf_counter,
) -> dict[str, Any]:
    """Mide un dispositivo: arranque en frío, incipits y páginas compuestas."""
    engine = engine_factory(device == "gpu")

    # Arranque en frío: primera llamada del proceso, incluye la carga de los modelos.
    cold_durations, cold_failures = _measure(engine, images[0], 1, clock)
    cold_start_ms = cold_durations[0] if cold_durations else None

    configurations: dict[str, Any] = {}

    warm: list[float] = []
    failures = 0
    for image in images[:incipits]:
        durations, failed = _measure(engine, image, runs, clock)
        warm.extend(durations)
        failures += failed
    configurations["incipit_1_staff"] = {
        "description": f"{incipits} incipits de un pentagrama, {runs} repeticiones cada uno",
        "warm_ms": warm,
        "failures": failures,
        "stats": compute_latency_stats(warm, timeout_s).to_dict(),
    }

    for count in staves:
        page = compose_page(images[:count], work_dir / f"page_{count}_staves.png")
        durations, failed = _measure(engine, page, runs, clock)
        configurations[f"page_{count}_staves"] = {
            "description": (
                f"página compuesta apilando las {count} primeras imágenes del manifiesto "
                f"(composición sintética, inferencia real), {runs} repeticiones"
            ),
            "warm_ms": durations,
            "failures": failed,
            "stats": compute_latency_stats(durations, timeout_s).to_dict(),
        }

    if not any(config["warm_ms"] for config in configurations.values()):
        raise RuntimeError(
            "El benchmark no obtuvo ninguna medición válida: todas las transcripciones "
            "fallaron. No se escribe ningún resultado."
        )
    return _device_record(
        environment=describe_environment(device),
        cold_samples=[] if cold_start_ms is None else [cold_start_ms],
        cold_failures=cold_failures,
        configurations=configurations,
        invocations=1,
        protocol={"incipits": incipits, "staves": list(staves), "runs": runs},
    )


def _device_record(
    *,
    environment: dict[str, Any],
    cold_samples: list[float],
    cold_failures: int,
    configurations: dict[str, Any],
    invocations: int,
    protocol: dict[str, Any],
) -> dict[str, Any]:
    all_warm = [value for config in configurations.values() for value in config["warm_ms"]]
    return {
        "environment": environment,
        "protocol": protocol,
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "invocations": invocations,
        "cold_start_samples_ms": cold_samples,
        "cold_start_failures": cold_failures,
        "cold_start_ms": max(cold_samples) if cold_samples else None,
        "max_warm_ms": max(all_warm) if all_warm else None,
        "configurations": configurations,
    }


def _accumulate(
    previous: dict[str, Any], current: dict[str, Any], timeout_s: float
) -> dict[str, Any]:
    """Suma las muestras de una ejecución anterior del mismo dispositivo y protocolo.

    Si el protocolo cambió (otro número de incipits, repeticiones o pentagramas), las
    muestras no son comparables y se conserva solo la ejecución actual.
    """
    if previous.get("protocol") != current["protocol"]:
        return current
    configurations: dict[str, Any] = {}
    for name, config in current["configurations"].items():
        before = previous["configurations"][name]
        warm = [*before["warm_ms"], *config["warm_ms"]]
        configurations[name] = {
            "description": config["description"],
            "warm_ms": warm,
            "failures": before["failures"] + config["failures"],
            "stats": compute_latency_stats(warm, timeout_s).to_dict(),
        }
    return _device_record(
        environment=current["environment"],
        cold_samples=[
            *previous.get("cold_start_samples_ms", []),
            *current["cold_start_samples_ms"],
        ],
        cold_failures=int(previous.get("cold_start_failures", 0)) + current["cold_start_failures"],
        configurations=configurations,
        invocations=int(previous.get("invocations", 1)) + 1,
        protocol=current["protocol"],
    )


def _architectural_evaluation(devices: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    warm = [d["max_warm_ms"] for d in devices.values() if d.get("max_warm_ms") is not None]
    cold = [d["cold_start_ms"] for d in devices.values() if d.get("cold_start_ms") is not None]
    if not warm:
        raise RuntimeError("No hay mediciones en caliente: no se puede emitir un veredicto.")
    max_warm = max(warm)
    # Sin ninguna muestra de arranque en frío, el veredicto se apoya solo en las cálidas.
    max_cold = max(cold) if cold else None
    return {
        "client_timeout_reference_s": timeout_s,
        "max_warm_ms": max_warm,
        "max_cold_start_ms": max_cold,
        "recommendation": evaluate_decision(
            max_warm, max_cold if max_cold is not None else 0.0, timeout_s
        ),
        "decision_rule": (
            "ASYNCHRONOUS_REQUIRED si alguna petición en caliente alcanza el timeout; "
            "SYNCHRONOUS_WITH_WARMUP si solo lo alcanza el arranque en frío; "
            "SYNCHRONOUS_SUFFICIENT en otro caso."
        ),
    }


def run_benchmark(
    *,
    device: str,
    manifest: Path | None = None,
    output_dir: Path | None = None,
    incipits: int = 5,
    staves: Sequence[int] = (4, 8, 12),
    runs: int = 3,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    engine_factory: EngineFactory | None = None,
    reset: bool = False,
    clock: Clock = time.perf_counter,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Mide la latencia en un dispositivo y fusiona el resultado en el resumen.

    Las muestras se acumulan con las de ejecuciones anteriores del mismo dispositivo y
    protocolo; `reset=True` descarta las anteriores.
    """
    if device not in ("cpu", "gpu"):
        raise ValueError("device debe ser 'cpu' o 'gpu'")
    if incipits < 1 or runs < 1:
        raise ValueError("incipits y runs deben ser al menos 1")

    out_dir = output_dir or RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest or DATA_DIR / "manifest.json"
    images = _load_images(manifest_path, max([incipits, *staves]))
    factory = engine_factory or _default_engine_factory

    # El resumen previo se lee antes de medir: un archivo corrupto no debe costar
    # una ejecución entera.
    summary_file = out_dir / SUMMARY_FILENAME
    devices: dict[str, Any] = {}
    if summary_file.is_file():
        previous = json.loads(summary_file.read_text(encoding="utf-8"))
        # Solo se fusiona con resúmenes medidos; uno simulado anterior se descarta.
        if previous.get("simulated") is False:
            devices = dict(previous.get("devices", {}))

    with tempfile.TemporaryDirectory(prefix="cadenza-exp11-") as tmp_dir:
        measured = measure_device(
            device=device,
            images=images,
            incipits=incipits,
            staves=staves,
            runs=runs,
            engine_factory=factory,
            work_dir=Path(tmp_dir),
            timeout_s=timeout_s,
            clock=clock,
        )

    if device in devices and not reset:
        measured = _accumulate(devices[device], measured, timeout_s)
    devices[device] = measured

    summary: dict[str, Any] = {
        "experiment": "exp_11_latency_benchmark",
        "simulated": False,
        "protocol": {
            "manifest": str(manifest_path),
            "incipits": incipits,
            "staves_per_page": list(staves),
            "runs_per_image": runs,
            "note": (
                "Cada dispositivo se mide en un proceso propio. El arranque en frío es la "
                "primera llamada del proceso (una muestra por ejecución); el resto son "
                "repeticiones en caliente. Las ejecuciones sucesivas acumulan muestras."
            ),
        },
        "devices": devices,
        "architectural_evaluation": _architectural_evaluation(devices, timeout_s),
    }
    summary_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    run_info = get_run_info("exp_11_latency_benchmark", seed=seed, manifest_path=manifest_path)
    run_info["device"] = device
    run_info["recommendation"] = summary["architectural_evaluation"]["recommendation"]
    (out_dir / "exp_11_run_info.json").write_text(
        json.dumps(run_info, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Latencia real de transcripción con HOMR.")
    parser.add_argument("--device", choices=("cpu", "gpu"), required=True)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--incipits", type=int, default=5)
    parser.add_argument("--staves", type=str, default="4,8,12")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path, default=None, help="Directorio de resultados.")
    parser.add_argument(
        "--reset", action="store_true", help="Descarta las muestras previas del dispositivo."
    )
    args = parser.parse_args()

    summary = run_benchmark(
        device=args.device,
        manifest=args.manifest,
        output_dir=args.output,
        incipits=args.incipits,
        staves=[int(value) for value in args.staves.split(",") if value],
        runs=args.runs,
        reset=args.reset,
    )
    measured = summary["devices"][args.device]
    print(
        f"[exp_11] dispositivo={args.device} ejecuciones={measured['invocations']} "
        f"arranque en frío={measured['cold_start_samples_ms']} ms"
    )
    for name, config in measured["configurations"].items():
        stats = config["stats"]
        print(
            f"[exp_11] {name}: n={stats['count']} media={stats['mean_ms']} ms "
            f"máx={stats['max_ms']} ms fallos={config['failures']}"
        )
    print(f"[exp_11] recomendación: {summary['architectural_evaluation']['recommendation']}")


if __name__ == "__main__":
    main()
