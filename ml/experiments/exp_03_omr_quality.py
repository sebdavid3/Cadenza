"""Experimento 3: calidad OMR (OMR-NED y SER) informando fallos y penalización (#24, #30).

Evalúa la calidad de transcripción de HOMR contra el Ground Truth del corpus PrIMuS
utilizando dos métricas complementarias:
1. OMR-NED: distancia de edición normalizada a nivel gráfico (`musicdiff`).
2. SER: tasa de error simbólico a nivel de secuencia de símbolos (`cadenza.learning`).

A diferencia de las líneas base iniciales que excluían silenciosamente los 9 fallos de detección,
este experimento informa con rigor:
1. Métricas sobre los éxitos (91 incipits transcritos):
   - OMR-NED: media 0.2285, mediana 0.1727.
   - SER: media 0.1124 (11.24%), mediana 0.0385 (3.85%).
2. Tasa de fallos (`failure_rate`): 9 de 100 imágenes (9.0%) fallaron con
   'Exception: No staffs found'.
3. Métricas penalizadas (`penalized_with_failures`): incluye los 100 incipits imputando
   OMR-NED = 1.0 y SER = 1.0 (distancia máxima de edición por omisión total de contenido musical).
   - OMR-NED penalizado: media 0.2979.
   - SER penalizado: media 0.1923 (19.23%).
4. Justificación muestral, limitaciones y trazabilidad determinista (`run_info.json`).

Salidas:
- `results/omr_baseline.csv` (100 filas con estado, métricas OMR-NED/SER y detalle de fallos)
- `results/omr_baseline_summary.json`
- `results/exp_03_run_info.json`
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import statistics
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cadenza.interchange import read_score
from cadenza.learning import omr_ned_pair, score_ser_pair, score_to_symbol_sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.experiments.common import (  # noqa: E402
    DEFAULT_SEED,
    METHODOLOGICAL_LIMITATIONS,
    RESULTS_DIR,
    SAMPLE_SIZE_JUSTIFICATION,
    get_run_info,
    write_run_info,
)

DATA_DIR = REPO_ROOT / "data"
SMOKE_FIXTURE = REPO_ROOT / "packages" / "interchange" / "tests" / "fixtures" / "simple.musicxml"
CSV_FIELDS = [
    "id",
    "status",
    "predicted",
    "ground_truth",
    "predicted_symbols",
    "ground_truth_symbols",
    "edit_distance",
    "omr_ned",
    "pred_ser_symbols",
    "gt_ser_symbols",
    "ser_edit_distance",
    "ser",
    "error",
]


@dataclass(frozen=True, slots=True)
class Pair:
    identifier: str
    predicted: Path
    ground_truth: Path


def _smoke_pair(tmp_path: Path) -> list[Pair]:
    """Par de prueba en modo smoke."""
    if not SMOKE_FIXTURE.is_file():
        return []
    altered = tmp_path / "smoke_prediction.musicxml"
    altered.write_text(
        SMOKE_FIXTURE.read_text(encoding="utf-8").replace("<step>C</step>", "<step>E</step>"),
        encoding="utf-8",
    )
    return [Pair("smoke", altered, SMOKE_FIXTURE)]


def _load_cached_successes(csv_path: Path) -> dict[str, dict[str, Any]]:
    """Carga resultados previamente computados para evitar recalculado costoso de musicdiff."""
    cached: dict[str, dict[str, Any]] = {}
    if not csv_path.is_file():
        return cached
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status") == "failure" or not row.get("omr_ned"):
                continue
            with contextlib.suppress(ValueError, KeyError):
                cached[row["id"]] = {
                    "predicted": row["predicted"],
                    "ground_truth": row["ground_truth"],
                    "predicted_symbols": int(row["predicted_symbols"]),
                    "ground_truth_symbols": int(row["ground_truth_symbols"]),
                    "edit_distance": int(row["edit_distance"]),
                    "omr_ned": float(row["omr_ned"]),
                    "pred_ser_symbols": (
                        int(row["pred_ser_symbols"]) if row.get("pred_ser_symbols") else None
                    ),
                    "gt_ser_symbols": (
                        int(row["gt_ser_symbols"]) if row.get("gt_ser_symbols") else None
                    ),
                    "ser_edit_distance": (
                        int(row["ser_edit_distance"]) if row.get("ser_edit_distance") else None
                    ),
                    "ser": float(row["ser"]) if row.get("ser") else None,
                }
    return cached


def _measure_corpus(
    manifest_path: Path,
    predictions_dir: Path,
    limit: int | None = None,
    force_recompute: bool = False,
    seed: int = DEFAULT_SEED,
    write_results: bool | None = None,
) -> dict[str, Any]:
    should_write = write_results if write_results is not None else (limit is None)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    corpus_name = str(manifest.get("corpus", "corpus"))
    entries = list(manifest.get("entries", []))
    if limit is not None:
        entries = entries[:limit]

    failures_file = predictions_dir / "failures.json"
    known_failures: dict[str, str] = {}
    if failures_file.is_file():
        failures_data = json.loads(failures_file.read_text(encoding="utf-8"))
        for f in failures_data:
            known_failures[f["id"]] = f.get("error", "Unknown error")

    csv_path = RESULTS_DIR / "omr_baseline.csv"
    cached_metrics = {} if force_recompute else _load_cached_successes(csv_path)

    rows: list[dict[str, Any]] = []
    success_ned_values: list[float] = []
    penalized_ned_values: list[float] = []
    success_ser_values: list[float] = []
    penalized_ser_values: list[float] = []
    failures_details: list[dict[str, str]] = []

    for entry in entries:
        eid = entry["id"]
        pred_file = predictions_dir / f"{eid}.musicxml"
        gt_file = root / entry["ground_truth"]

        # Caso fallo
        if eid in known_failures or not pred_file.is_file():
            err_msg = known_failures.get(eid, "Prediction file missing / No staffs found")
            gt_symbols_len = 0
            if gt_file.is_file():
                with contextlib.suppress(Exception):
                    gt_symbols_len = len(score_to_symbol_sequence(read_score(gt_file)))

            row = {
                "id": eid,
                "status": "failure",
                "predicted": str(pred_file) if pred_file.is_file() else "none",
                "ground_truth": str(gt_file),
                "predicted_symbols": 0,
                "ground_truth_symbols": "",
                "edit_distance": "",
                "omr_ned": 1.0,
                "pred_ser_symbols": 0,
                "gt_ser_symbols": gt_symbols_len,
                "ser_edit_distance": gt_symbols_len,
                "ser": 1.0,
                "error": err_msg,
            }
            rows.append(row)
            penalized_ned_values.append(1.0)
            penalized_ser_values.append(1.0)
            failures_details.append({"id": eid, "error": err_msg})
            continue

        # Caso éxito - OMR-NED
        if eid in cached_metrics:
            m = cached_metrics[eid]
            ned = m["omr_ned"]
            pred_syms = m["predicted_symbols"]
            gt_syms = m["ground_truth_symbols"]
            edit_dist = m["edit_distance"]
            cached_ser = m.get("ser")
            cached_pred_ser = m.get("pred_ser_symbols")
            cached_gt_ser = m.get("gt_ser_symbols")
            cached_ser_dist = m.get("ser_edit_distance")
        else:
            res_ned = omr_ned_pair(pred_file, gt_file)
            ned = res_ned.omr_ned
            pred_syms = res_ned.predicted_symbols
            gt_syms = res_ned.ground_truth_symbols
            edit_dist = res_ned.edit_distance
            cached_ser = None
            cached_pred_ser = None
            cached_gt_ser = None
            cached_ser_dist = None

        # SER
        if (
            cached_ser is not None
            and cached_pred_ser is not None
            and cached_gt_ser is not None
            and cached_ser_dist is not None
        ):
            ser_val = cached_ser
            pred_ser_syms = cached_pred_ser
            gt_ser_syms = cached_gt_ser
            ser_dist = cached_ser_dist
        else:
            gt_score = read_score(gt_file)
            pred_score = read_score(pred_file)
            ser_res = score_ser_pair(gt_score, pred_score)
            ser_val = ser_res.ser
            pred_ser_syms = ser_res.hypothesis_symbols
            gt_ser_syms = ser_res.reference_symbols
            ser_dist = ser_res.edit_distance

        row = {
            "id": eid,
            "status": "success",
            "predicted": str(pred_file),
            "ground_truth": str(gt_file),
            "predicted_symbols": pred_syms,
            "ground_truth_symbols": gt_syms,
            "edit_distance": edit_dist,
            "omr_ned": ned,
            "pred_ser_symbols": pred_ser_syms,
            "gt_ser_symbols": gt_ser_syms,
            "ser_edit_distance": ser_dist,
            "ser": ser_val,
            "error": "",
        }

        rows.append(row)
        success_ned_values.append(ned)
        penalized_ned_values.append(ned)
        success_ser_values.append(ser_val)
        penalized_ser_values.append(ser_val)

    if should_write:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    total_count = len(rows)
    successes_count = len(success_ned_values)
    failures_count = len(failures_details)
    failure_rate = (failures_count / total_count) if total_count else 0.0

    mean_success = statistics.fmean(success_ned_values) if success_ned_values else None
    median_success = statistics.median(success_ned_values) if success_ned_values else None
    stdev_success = statistics.stdev(success_ned_values) if len(success_ned_values) > 1 else None

    mean_penalized = statistics.fmean(penalized_ned_values) if penalized_ned_values else None
    median_penalized = statistics.median(penalized_ned_values) if penalized_ned_values else None

    mean_ser_success = statistics.fmean(success_ser_values) if success_ser_values else None
    median_ser_success = statistics.median(success_ser_values) if success_ser_values else None
    stdev_ser_success = (
        statistics.stdev(success_ser_values) if len(success_ser_values) > 1 else None
    )

    mean_ser_penalized = statistics.fmean(penalized_ser_values) if penalized_ser_values else None
    median_ser_penalized = statistics.median(penalized_ser_values) if penalized_ser_values else None

    if should_write:
        run_info = write_run_info("exp_03", seed=seed, manifest_path=manifest_path)
    else:
        run_info = get_run_info("exp_03", seed=seed, manifest_path=manifest_path)

    summary: dict[str, Any] = {
        "experiment": "exp_03_omr_quality",
        "mode": "corpus",
        "corpus": corpus_name,
        "seed": seed,
        "total_evaluated": total_count,
        "successes_count": successes_count,
        "failures_count": failures_count,
        "failure_rate": round(failure_rate, 4),
        "failure_rate_percent": round(failure_rate * 100, 2),
        "metrics_on_successes": {
            "count": successes_count,
            "mean_omr_ned": round(mean_success, 4) if mean_success is not None else None,
            "median_omr_ned": round(median_success, 4) if median_success is not None else None,
            "stdev_omr_ned": round(stdev_success, 4) if stdev_success is not None else None,
            "mean_ser": round(mean_ser_success, 4) if mean_ser_success is not None else None,
            "median_ser": round(median_ser_success, 4) if median_ser_success is not None else None,
            "stdev_ser": round(stdev_ser_success, 4) if stdev_ser_success is not None else None,
        },
        "metrics_penalized_with_failures": {
            "imputation_policy": (
                "OMR-NED = 1.0, SER = 1.0 (máxima penalización por fallo de segmentación)"
            ),
            "count": total_count,
            "mean_omr_ned_penalized": (
                round(mean_penalized, 4) if mean_penalized is not None else None
            ),
            "median_omr_ned_penalized": (
                round(median_penalized, 4) if median_penalized is not None else None
            ),
            "mean_ser_penalized": (
                round(mean_ser_penalized, 4) if mean_ser_penalized is not None else None
            ),
            "median_ser_penalized": (
                round(median_ser_penalized, 4) if median_ser_penalized is not None else None
            ),
        },
        "failures_detail": failures_details,
        "sample_size_justification": SAMPLE_SIZE_JUSTIFICATION,
        "methodological_limitations": METHODOLOGICAL_LIMITATIONS,
        "run_info": run_info,
        "csv": str(csv_path),
    }

    if should_write:
        out_json = RESULTS_DIR / "omr_baseline_summary.json"
        out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def _measure_smoke(tmp_path: Path, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    pairs = _smoke_pair(tmp_path)
    if not pairs:
        return {"experiment": "exp_03_omr_quality", "mode": "smoke", "count": 0}
    pair = pairs[0]
    res_ned = omr_ned_pair(pair.predicted, pair.ground_truth)
    ser_res = score_ser_pair(read_score(pair.ground_truth), read_score(pair.predicted))
    run_info = write_run_info("exp_03", seed=seed)
    return {
        "experiment": "exp_03_omr_quality",
        "mode": "smoke",
        "corpus": "smoke",
        "total_evaluated": 1,
        "successes_count": 1,
        "failures_count": 0,
        "failure_rate": 0.0,
        "metrics_on_successes": {
            "count": 1,
            "mean_omr_ned": res_ned.omr_ned,
            "median_omr_ned": res_ned.omr_ned,
            "mean_ser": round(ser_res.ser, 4),
            "median_ser": round(ser_res.ser, 4),
        },
        "metrics_penalized_with_failures": {
            "count": 1,
            "mean_omr_ned_penalized": res_ned.omr_ned,
            "median_omr_ned_penalized": res_ned.omr_ned,
            "mean_ser_penalized": round(ser_res.ser, 4),
            "median_ser_penalized": round(ser_res.ser, 4),
        },
        "failures_detail": [],
        "run_info": run_info,
    }


def run(
    manifest: Path,
    predictions: Path | None,
    limit: int | None,
    force_recompute: bool = False,
    seed: int = DEFAULT_SEED,
    write_results: bool | None = None,
) -> dict[str, Any]:
    if predictions is None:
        corpus_name = str(json.loads(manifest.read_text(encoding="utf-8")).get("corpus", "corpus"))
        predictions = manifest.parent / corpus_name / "predictions"
    return _measure_corpus(
        manifest,
        predictions,
        limit=limit,
        force_recompute=force_recompute,
        seed=seed,
        write_results=write_results,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calidad OMR (OMR-NED y SER) con tasa de fallos y métricas penalizadas — Fase 7"
    )
    parser.add_argument("--manifest", type=Path, default=DATA_DIR / "manifest.json")
    parser.add_argument("--predictions", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--force", action="store_true", help="Forzar recomputación de OMR-NED y SER"
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    if args.manifest.is_file():
        summary = run(
            args.manifest,
            args.predictions,
            args.limit,
            force_recompute=args.force,
            seed=args.seed,
        )
    else:
        with tempfile.TemporaryDirectory(prefix="cadenza-exp03-") as tmp:
            summary = _measure_smoke(Path(tmp), seed=args.seed)

    print(
        f"[exp_03] Modo={summary['mode']} Total={summary['total_evaluated']} "
        f"Éxitos={summary['successes_count']} Fallos={summary['failures_count']} "
        f"Tasa de fallos={summary.get('failure_rate_percent', 0.0)}%"
    )
    success_metrics = summary.get("metrics_on_successes", {})
    penalized_metrics = summary.get("metrics_penalized_with_failures", {})
    print(
        f"[exp_03] OMR-NED sobre éxitos: media={success_metrics.get('mean_omr_ned')} "
        f"mediana={success_metrics.get('median_omr_ned')}"
    )
    print(
        f"[exp_03] SER sobre éxitos:     media={success_metrics.get('mean_ser')} "
        f"mediana={success_metrics.get('median_ser')}"
    )
    print(
        f"[exp_03] OMR-NED penalizado:    media={penalized_metrics.get('mean_omr_ned_penalized')} "
        f"mediana={penalized_metrics.get('median_omr_ned_penalized')}"
    )
    print(
        f"[exp_03] SER penalizado:        media={penalized_metrics.get('mean_ser_penalized')} "
        f"mediana={penalized_metrics.get('median_ser_penalized')}"
    )
    if "csv" in summary:
        print(f"[exp_03] Escrito CSV: {summary['csv']}")


if __name__ == "__main__":
    main()
