"""Experimento 7: impacto real del preprocesado de imagen sobre HOMR (#15, #98, D2).

Transcribe con HOMR el subconjunto del corpus una vez por cada configuración de
preprocesado y compara, partitura a partitura, con la línea base sin preprocesado
(las predicciones de `exp_04`, medidas como en `exp_03`).

Las configuraciones están fijadas en este archivo antes de medir. No hay valores de
reserva ni listas de casos escritas a mano: sin el motor, sin el corpus o sin las
predicciones de la línea base el script termina con un error. Solo cuenta como fallo
de una partitura el error de transcripción del motor (`OMRTranscriptionError`);
cualquier otro error es del entorno y detiene la ejecución.

La configuración `control` transcribe sin preprocesado en la misma ejecución que las
demás. Su diferencia con la línea base no se debe al preprocesado: mide cuánto varía
el resultado entre dos ejecuciones (revisión del adaptador, dispositivo, no
determinismo del motor) y es el umbral por debajo del cual un efecto no es atribuible.

Fases:
1. `transcribe_config`: una predicción MusicXML por imagen en
   `data/<corpus>/predictions_pre_<configuración>/`, con `failures.json`.
2. `measure_predictions`: OMR-NED y SER de cada predicción frente al *ground truth*.
3. `compare`: fallos, métricas sobre éxitos y penalizadas, partituras recuperadas,
   regresiones y diferencia pareada sobre las partituras que funcionan en ambos casos.

Salidas:
- `results/preprocessing_impact_summary.json`
- `results/preprocessing_comparison.csv`
- `results/exp_07_run_info.json`
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from cadenza.interchange import read_score
from cadenza.learning import omr_ned_pair, score_ser_pair
from cadenza.omr import OMRTranscriptionError
from cadenza.omr.preprocessing import PreprocessingConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.experiments.common import (  # noqa: E402
    DATA_DIR,
    DEFAULT_SEED,
    METHODOLOGICAL_LIMITATIONS,
    RESULTS_DIR,
    write_run_info,
)

# Configuraciones evaluadas, fijadas antes de medir. `control` no preprocesa.
CONTROL = "control"
CONFIGS: dict[str, PreprocessingConfig] = {
    CONTROL: PreprocessingConfig(enabled=False),
    "binarize": PreprocessingConfig(enabled=True, binarize=True),
    "rescale": PreprocessingConfig(enabled=True, rescale=True),
    "deskew_binarize_rescale": PreprocessingConfig(
        enabled=True, deskew=True, binarize=True, rescale=True
    ),
}

CSV_FIELDS = ["id", "config", "status", "omr_ned", "ser", "error"]
# Diferencias menores que esto se consideran empate (ruido de redondeo).
TIE_TOLERANCE = 1e-9
# Valor imputado a OMR-NED y a SER cuando la transcripción falla: el máximo de ambas.
FAILURE_PENALTY = 1.0


class Transcriber(Protocol):
    def transcribe_musicxml(self, image_path: Path) -> str: ...


EngineFactory = Callable[[PreprocessingConfig, bool], Transcriber]


def _default_engine_factory(config: PreprocessingConfig, use_gpu: bool) -> Transcriber:
    from cadenza.omr import HOMREngine

    return HOMREngine(use_gpu=use_gpu, preprocessing=config)


def _load_manifest(manifest_path: Path, limit: int | None) -> tuple[str, list[dict[str, Any]]]:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"No existe el manifiesto del corpus: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = list(manifest.get("entries", []))
    if limit is not None:
        entries = entries[:limit]
    if not entries:
        raise ValueError(f"El manifiesto {manifest_path} no tiene entradas")
    return str(manifest.get("corpus", "corpus")), entries


def predictions_dir(manifest_path: Path, config_name: str | None) -> Path:
    """Directorio de predicciones: el de la línea base o el de una configuración."""
    corpus, _ = _load_manifest(manifest_path, None)
    suffix = "predictions" if config_name is None else f"predictions_pre_{config_name}"
    return manifest_path.parent / corpus / suffix


def transcribe_config(
    manifest_path: Path,
    config_name: str,
    config: PreprocessingConfig,
    *,
    use_gpu: bool = True,
    force: bool = False,
    retry_failures: bool = False,
    limit: int | None = None,
    engine_factory: EngineFactory | None = None,
) -> dict[str, Any]:
    """Transcribe el corpus con una configuración de preprocesado.

    Reutiliza las predicciones y los fallos ya registrados salvo que `force` sea cierto,
    de modo que una ejecución interrumpida se puede reanudar. Con `retry_failures` se
    conservan las predicciones y se vuelven a intentar solo los fallos registrados. Se
    niega a reutilizar las predicciones de otra configuración de preprocesado.
    """
    _, entries = _load_manifest(manifest_path, limit)
    out_dir = predictions_dir(manifest_path, config_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    failures_file = out_dir / "failures.json"
    info_file = out_dir / "run_info.json"

    if info_file.is_file() and not force:
        previous = json.loads(info_file.read_text(encoding="utf-8")).get("preprocessing")
        if previous != config.to_primitive():
            raise ValueError(
                f"Las predicciones de {out_dir} se generaron con otra configuración de "
                f"preprocesado ({previous}); repite la transcripción con --force."
            )

    failures: dict[str, str] = {}
    if failures_file.is_file() and not force:
        failures = {
            item["id"]: item["error"]
            for item in json.loads(failures_file.read_text(encoding="utf-8"))
        }
    retry = set(failures) if retry_failures else set()

    engine = (engine_factory or _default_engine_factory)(config, use_gpu)
    written = 0
    reused = 0
    for entry in entries:
        entry_id = entry["id"]
        target = out_dir / f"{entry_id}.musicxml"
        if not force and entry_id not in retry and (target.is_file() or entry_id in failures):
            reused += 1
            continue
        try:
            xml_text = engine.transcribe_musicxml(manifest_path.parent / entry["image"])
        except OMRTranscriptionError as exc:
            # Un fallo del motor es un resultado del experimento, no un error del script.
            # El adaptador envuelve la excepción original: se conserva su tipo.
            cause = type(exc.__cause__).__name__ if exc.__cause__ is not None else "sin causa"
            failures[entry_id] = f"{type(exc).__name__} [{cause}]: {exc}"
            target.unlink(missing_ok=True)
        else:
            failures.pop(entry_id, None)
            target.write_text(xml_text, encoding="utf-8")
            written += 1
        failures_file.write_text(
            json.dumps(
                [{"id": key, "error": value} for key, value in sorted(failures.items())],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    info_file.write_text(
        json.dumps(
            {
                "config": config_name,
                "preprocessing": config.to_primitive(),
                "use_gpu_requested": use_gpu,
                "device": getattr(engine, "device", None),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    in_scope = sum(1 for entry in entries if entry["id"] in failures)
    return {"written": written, "reused": reused, "failures": in_scope}


def measure_predictions(
    manifest_path: Path, predictions: Path, *, limit: int | None = None
) -> dict[str, dict[str, Any]]:
    """Mide OMR-NED y SER de cada predicción frente a su *ground truth*.

    Una partitura cuenta como fallo si está en `failures.json`. Una predicción ausente
    que no figura allí es un error: el experimento no puede dar por fallida una
    transcripción que nunca se intentó.
    """
    if not predictions.is_dir():
        raise FileNotFoundError(f"No existe el directorio de predicciones: {predictions}")
    _, entries = _load_manifest(manifest_path, limit)

    failures_file = predictions / "failures.json"
    failures: dict[str, str] = {}
    if failures_file.is_file():
        failures = {
            item["id"]: item.get("error", "")
            for item in json.loads(failures_file.read_text(encoding="utf-8"))
        }

    measured: dict[str, dict[str, Any]] = {}
    for entry in entries:
        entry_id = entry["id"]
        pred_file = predictions / f"{entry_id}.musicxml"
        if entry_id in failures:
            measured[entry_id] = {
                "status": "failure",
                "omr_ned": FAILURE_PENALTY,
                "ser": FAILURE_PENALTY,
                "error": failures[entry_id],
            }
            continue
        if not pred_file.is_file():
            raise FileNotFoundError(
                f"Falta la predicción de {entry_id} en {predictions} y no está registrada "
                "como fallo: ejecuta antes la transcripción."
            )
        gt_file = manifest_path.parent / entry["ground_truth"]
        ned = omr_ned_pair(pred_file, gt_file).omr_ned
        ser = score_ser_pair(read_score(gt_file), read_score(pred_file)).ser
        measured[entry_id] = {"status": "success", "omr_ned": ned, "ser": ser, "error": ""}
    return measured


def _mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 4) if values else None


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 4) if values else None


def summarize(measured: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Resumen de un conjunto de predicciones: fallos y métricas sobre éxitos y penalizadas."""
    successes = [m for m in measured.values() if m["status"] == "success"]
    total = len(measured)
    failures = total - len(successes)
    return {
        "total": total,
        "successes": len(successes),
        "failures": failures,
        "failure_rate": round(failures / total, 4) if total else None,
        "mean_omr_ned_successes": _mean([m["omr_ned"] for m in successes]),
        "median_omr_ned_successes": _median([m["omr_ned"] for m in successes]),
        "mean_ser_successes": _mean([m["ser"] for m in successes]),
        "mean_omr_ned_penalized": _mean([m["omr_ned"] for m in measured.values()]),
        "mean_ser_penalized": _mean([m["ser"] for m in measured.values()]),
    }


def compare(
    baseline: Mapping[str, Mapping[str, Any]], variant: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """Compara una configuración con la línea base, partitura a partitura."""
    recovered = sorted(
        key
        for key, item in variant.items()
        if item["status"] == "success" and baseline[key]["status"] == "failure"
    )
    regressed = sorted(
        key
        for key, item in variant.items()
        if item["status"] == "failure" and baseline[key]["status"] == "success"
    )
    common = sorted(
        key
        for key, item in variant.items()
        if item["status"] == "success" and baseline[key]["status"] == "success"
    )
    ned_deltas = [variant[key]["omr_ned"] - baseline[key]["omr_ned"] for key in common]
    ser_deltas = [variant[key]["ser"] - baseline[key]["ser"] for key in common]
    return {
        "recovered": recovered,
        "regressed": regressed,
        "paired_successes": len(common),
        "paired_mean_omr_ned_delta": _mean(ned_deltas),
        "paired_mean_ser_delta": _mean(ser_deltas),
        "paired_omr_ned_improved": sum(1 for delta in ned_deltas if delta < -TIE_TOLERANCE),
        "paired_omr_ned_worsened": sum(1 for delta in ned_deltas if delta > TIE_TOLERANCE),
        "paired_omr_ned_equal": sum(1 for delta in ned_deltas if abs(delta) <= TIE_TOLERANCE),
    }


def run_preprocessing_experiment(
    manifest_path: Path | None = None,
    *,
    configs: Mapping[str, PreprocessingConfig] | None = None,
    transcribe: bool = True,
    use_gpu: bool = True,
    force: bool = False,
    retry_failures: bool = False,
    limit: int | None = None,
    write_results: bool = True,
    engine_factory: EngineFactory | None = None,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Ejecuta el experimento completo y devuelve el resumen."""
    manifest = manifest_path or DATA_DIR / "manifest.json"
    selected = dict(configs or CONFIGS)

    baseline = measure_predictions(manifest, predictions_dir(manifest, None), limit=limit)

    per_config: dict[str, Any] = {}
    rows: list[dict[str, Any]] = [
        {"id": key, "config": "baseline", **{f: item[f] for f in CSV_FIELDS[2:]}}
        for key, item in baseline.items()
    ]
    for name, config in selected.items():
        transcription = None
        if transcribe:
            transcription = transcribe_config(
                manifest,
                name,
                config,
                use_gpu=use_gpu,
                force=force,
                retry_failures=retry_failures,
                limit=limit,
                engine_factory=engine_factory,
            )
        measured = measure_predictions(manifest, predictions_dir(manifest, name), limit=limit)
        per_config[name] = {
            "preprocessing": config.to_primitive(),
            "transcription": transcription,
            "summary": summarize(measured),
            "versus_baseline": compare(baseline, measured),
        }
        rows.extend(
            {"id": key, "config": name, **{f: item[f] for f in CSV_FIELDS[2:]}}
            for key, item in measured.items()
        )

    summary: dict[str, Any] = {
        "experiment": "exp_07_preprocessing_impact",
        "simulated": False,
        "manifest": str(manifest),
        "total_samples": len(baseline),
        "failure_imputation": (
            f"OMR-NED = {FAILURE_PENALTY} y SER = {FAILURE_PENALTY} por cada transcripción "
            "fallida, en las métricas penalizadas y en el CSV"
        ),
        "baseline": summarize(baseline),
        "configurations": per_config,
        "methodological_limitations": METHODOLOGICAL_LIMITATIONS,
    }

    if write_results:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        (RESULTS_DIR / "preprocessing_impact_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        with (RESULTS_DIR / "preprocessing_comparison.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        write_run_info(
            "exp_07_preprocessing_impact",
            seed=seed,
            manifest_path=manifest,
            output_filename="exp_07_run_info.json",
        )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Impacto real del preprocesado de imagen sobre HOMR (Experimento 7)."
    )
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--cpu", action="store_true", help="Forzar inferencia en CPU")
    parser.add_argument("--force", action="store_true", help="Repetir las transcripciones")
    parser.add_argument(
        "--retry-failures",
        action="store_true",
        help="Volver a intentar solo las transcripciones registradas como fallo",
    )
    parser.add_argument(
        "--no-transcribe",
        action="store_true",
        help="No transcribir: medir solo las predicciones ya existentes",
    )
    args = parser.parse_args()

    summary = run_preprocessing_experiment(
        args.manifest,
        transcribe=not args.no_transcribe,
        use_gpu=not args.cpu,
        force=args.force,
        retry_failures=args.retry_failures,
        limit=args.limit,
    )
    base = summary["baseline"]
    print(
        f"[exp_07] línea base: fallos={base['failures']}/{base['total']} "
        f"OMR-NED éxitos={base['mean_omr_ned_successes']} "
        f"penalizado={base['mean_omr_ned_penalized']}"
    )
    for name, result in summary["configurations"].items():
        stats, versus = result["summary"], result["versus_baseline"]
        print(
            f"[exp_07] {name}: fallos={stats['failures']}/{stats['total']} "
            f"OMR-NED éxitos={stats['mean_omr_ned_successes']} "
            f"penalizado={stats['mean_omr_ned_penalized']} "
            f"recuperadas={len(versus['recovered'])} regresiones={len(versus['regressed'])} "
            f"Δ OMR-NED pareado={versus['paired_mean_omr_ned_delta']}"
        )


if __name__ == "__main__":
    main()
