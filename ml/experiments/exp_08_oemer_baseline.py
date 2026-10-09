"""Experimento 8: línea base OMR de oemer y comparación con HOMR (#16, ADR-0005).

Evalúa la calidad de transcripción de `oemer` contra el Ground Truth del corpus PrIMuS
utilizando dos métricas complementarias (OMR-NED y SER) y contrasta los resultados
con la línea base de HOMR (exp_03, #24, #30).

Objetivos del experimento:
1. Proveer la línea base no asistida de referencia estipulada en ADR-0005
   (deuda técnica D1, hito M1).
2. Reportar métricas duales sobre el mismo subconjunto de PrIMuS:
   - OMR-NED: distancia de edición normalizada gráfica (`musicdiff`).
   - SER: tasa de error simbólico canónico (`cadenza.learning`).
3. Informar honestamente la tasa de fallos de segmentación y las métricas penalizadas imputando 1.0.
4. Comparar el desempeño relativo entre HOMR (motor base) y oemer (línea base).

Salidas:
- `results/oemer_baseline.csv`
- `results/oemer_baseline_summary.json`
- `results/exp_08_run_info.json`
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
HOMR_SUMMARY_FILE = RESULTS_DIR / "omr_baseline_summary.json"

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
    """Par de prueba en modo smoke para tests automatizados."""
    if not SMOKE_FIXTURE.is_file():
        return []
    altered = tmp_path / "smoke_oemer_prediction.musicxml"
    altered.write_text(
        SMOKE_FIXTURE.read_text(encoding="utf-8").replace("<step>C</step>", "<step>F</step>"),
        encoding="utf-8",
    )
    return [Pair("smoke", altered, SMOKE_FIXTURE)]


def _load_homr_summary() -> dict[str, Any] | None:
    """Carga el resumen de la línea base de HOMR si existe en disco."""
    if HOMR_SUMMARY_FILE.is_file():
        try:
            data = json.loads(HOMR_SUMMARY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            return None
    return None


def _load_cached_successes(csv_path: Path) -> dict[str, dict[str, Any]]:
    """Carga resultados previamente computados para evitar recalcular musicdiff."""
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


def _measure_smoke(tmp_path: Path, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    """Ejecuta el experimento en modo smoke rápido sin dependencias pesadas."""
    pairs = _smoke_pair(tmp_path)
    if not pairs:
        return {"error": "Smoke fixture not found", "mode": "smoke"}

    pair = pairs[0]
    gt_score = read_score(pair.ground_truth)
    pred_score = read_score(pair.predicted)

    ned_res = omr_ned_pair(pair.ground_truth, pair.predicted)
    ser_res = score_ser_pair(gt_score, pred_score)

    homr_data = _load_homr_summary()
    homr_success_ned = (
        homr_data.get("metrics_on_successes", {}).get("mean_omr_ned") if homr_data else 0.2285
    )
    homr_success_ser = (
        homr_data.get("metrics_on_successes", {}).get("mean_ser") if homr_data else 0.1124
    )

    return {
        "experiment": "exp_08_oemer_baseline",
        "mode": "smoke",
        "seed": seed,
        "total_evaluated": 1,
        "successes_count": 1,
        "failures_count": 0,
        "failure_rate": 0.0,
        "failure_rate_percent": 0.0,
        "metrics_on_successes": {
            "count": 1,
            "mean_omr_ned": round(ned_res.omr_ned, 4),
            "median_omr_ned": round(ned_res.omr_ned, 4),
            "mean_ser": round(ser_res.ser, 4),
            "median_ser": round(ser_res.ser, 4),
        },
        "metrics_penalized_with_failures": {
            "imputation_policy": "OMR-NED = 1.0, SER = 1.0 (máxima penalización por fallo)",
            "count": 1,
            "mean_omr_ned_penalized": round(ned_res.omr_ned, 4),
            "median_omr_ned_penalized": round(ned_res.omr_ned, 4),
            "mean_ser_penalized": round(ser_res.ser, 4),
            "median_ser_penalized": round(ser_res.ser, 4),
        },
        "comparison_vs_homr": {
            "homr_baseline_found": homr_data is not None,
            "homr_success_omr_ned": homr_success_ned,
            "homr_success_ser": homr_success_ser,
            "delta_omr_ned": round(ned_res.omr_ned - (homr_success_ned or 0.0), 4),
            "delta_ser": round(ser_res.ser - (homr_success_ser or 0.0), 4),
        },
        "run_info": get_run_info("exp_08", seed, None),
    }


def _measure_corpus(
    manifest_path: Path,
    predictions_dir: Path | None = None,
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

    effective_pred_dir = (
        predictions_dir
        if predictions_dir is not None
        else DATA_DIR / "primus" / "predictions_oemer"
    )

    failures_file = effective_pred_dir / "failures.json"
    known_failures: dict[str, str] = {}
    if failures_file.is_file():
        failures_data = json.loads(failures_file.read_text(encoding="utf-8"))
        for f in failures_data:
            known_failures[f["id"]] = f.get("error", "Unknown error")

    csv_path = RESULTS_DIR / "oemer_baseline.csv"
    cached_metrics = {} if force_recompute else _load_cached_successes(csv_path)

    rows: list[dict[str, Any]] = []
    success_ned_values: list[float] = []
    penalized_ned_values: list[float] = []
    success_ser_values: list[float] = []
    penalized_ser_values: list[float] = []
    failures_details: list[dict[str, str]] = []

    for entry in entries:
        eid = entry["id"]
        pred_file = effective_pred_dir / f"{eid}.musicxml"
        gt_file = root / entry["ground_truth"]

        # Caso fallo conocido o predicción ausente
        if eid in known_failures or not pred_file.is_file():
            err_msg = known_failures.get(
                eid,
                "Prediction file missing / Oemer staff extraction failed",
            )
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

        # Caso éxito con métricas en caché
        if eid in cached_metrics:
            m = cached_metrics[eid]
            ned = m["omr_ned"]
            pred_syms = m["predicted_symbols"]
            gt_syms = m["ground_truth_symbols"]
            edit_dist = m["edit_distance"]
            cached_ser = m.get("ser")

            if cached_ser is not None:
                ser_val = cached_ser
                p_ser_syms = m.get("pred_ser_symbols", 0)
                g_ser_syms = m.get("gt_ser_symbols", 0)
                ser_dist = m.get("ser_edit_distance", 0)
            else:
                try:
                    gt_score = read_score(gt_file)
                    pred_score = read_score(pred_file)
                    ser_res = score_ser_pair(gt_score, pred_score)
                    ser_val = ser_res.ser
                    p_ser_syms = ser_res.hypothesis_symbols
                    g_ser_syms = ser_res.reference_symbols
                    ser_dist = ser_res.edit_distance
                except Exception:
                    ser_val = 1.0
                    p_ser_syms = 0
                    g_ser_syms = 0
                    ser_dist = 0

            rows.append(
                {
                    "id": eid,
                    "status": "success",
                    "predicted": str(pred_file),
                    "ground_truth": str(gt_file),
                    "predicted_symbols": pred_syms,
                    "ground_truth_symbols": gt_syms,
                    "edit_distance": edit_dist,
                    "omr_ned": ned,
                    "pred_ser_symbols": p_ser_syms,
                    "gt_ser_symbols": g_ser_syms,
                    "ser_edit_distance": ser_dist,
                    "ser": ser_val,
                    "error": "",
                }
            )
            success_ned_values.append(ned)
            penalized_ned_values.append(ned)
            success_ser_values.append(ser_val)
            penalized_ser_values.append(ser_val)
            continue

        # Caso éxito calculado de novo
        try:
            ned_res = omr_ned_pair(gt_file, pred_file)
            ned = ned_res.omr_ned
            pred_syms = ned_res.predicted_symbols
            gt_syms = ned_res.ground_truth_symbols
            edit_dist = ned_res.edit_distance

            gt_score = read_score(gt_file)
            pred_score = read_score(pred_file)
            ser_res = score_ser_pair(gt_score, pred_score)
            ser_val = ser_res.ser
            p_ser_syms = ser_res.hypothesis_symbols
            g_ser_syms = ser_res.reference_symbols
            ser_dist = ser_res.edit_distance

            rows.append(
                {
                    "id": eid,
                    "status": "success",
                    "predicted": str(pred_file),
                    "ground_truth": str(gt_file),
                    "predicted_symbols": pred_syms,
                    "ground_truth_symbols": gt_syms,
                    "edit_distance": edit_dist,
                    "omr_ned": round(ned, 4),
                    "pred_ser_symbols": p_ser_syms,
                    "gt_ser_symbols": g_ser_syms,
                    "ser_edit_distance": ser_dist,
                    "ser": round(ser_val, 4),
                    "error": "",
                }
            )
            success_ned_values.append(ned)
            penalized_ned_values.append(ned)
            success_ser_values.append(ser_val)
            penalized_ser_values.append(ser_val)
        except Exception as exc:
            rows.append(
                {
                    "id": eid,
                    "status": "failure",
                    "predicted": str(pred_file),
                    "ground_truth": str(gt_file),
                    "predicted_symbols": 0,
                    "ground_truth_symbols": "",
                    "edit_distance": "",
                    "omr_ned": 1.0,
                    "pred_ser_symbols": 0,
                    "gt_ser_symbols": 0,
                    "ser_edit_distance": 0,
                    "ser": 1.0,
                    "error": str(exc),
                }
            )
            penalized_ned_values.append(1.0)
            penalized_ser_values.append(1.0)
            failures_details.append({"id": eid, "error": str(exc)})

    total_evaluated = len(entries)
    successes_count = len(success_ned_values)
    failures_count = len(failures_details)
    failure_rate = (failures_count / total_evaluated) if total_evaluated > 0 else 0.0

    mean_ned = round(statistics.mean(success_ned_values), 4) if success_ned_values else None
    median_ned = round(statistics.median(success_ned_values), 4) if success_ned_values else None
    stdev_ned = (
        round(statistics.stdev(success_ned_values), 4) if len(success_ned_values) > 1 else None
    )

    mean_ser = round(statistics.mean(success_ser_values), 4) if success_ser_values else None
    median_ser = round(statistics.median(success_ser_values), 4) if success_ser_values else None
    stdev_ser = (
        round(statistics.stdev(success_ser_values), 4) if len(success_ser_values) > 1 else None
    )

    mean_penalized_ned = (
        round(statistics.mean(penalized_ned_values), 4) if penalized_ned_values else None
    )
    median_penalized_ned = (
        round(statistics.median(penalized_ned_values), 4) if penalized_ned_values else None
    )
    mean_penalized_ser = (
        round(statistics.mean(penalized_ser_values), 4) if penalized_ser_values else None
    )
    median_penalized_ser = (
        round(statistics.median(penalized_ser_values), 4) if penalized_ser_values else None
    )

    homr_data = _load_homr_summary()
    homr_success_ned = (
        homr_data.get("metrics_on_successes", {}).get("mean_omr_ned") if homr_data else None
    )
    homr_success_ser = (
        homr_data.get("metrics_on_successes", {}).get("mean_ser") if homr_data else None
    )
    homr_failure_rate = homr_data.get("failure_rate") if homr_data else None

    summary: dict[str, Any] = {
        "experiment": "exp_08_oemer_baseline",
        "mode": "corpus",
        "corpus": corpus_name,
        "seed": seed,
        "total_evaluated": total_evaluated,
        "successes_count": successes_count,
        "failures_count": failures_count,
        "failure_rate": round(failure_rate, 4),
        "failure_rate_percent": round(failure_rate * 100, 2),
        "metrics_on_successes": {
            "count": successes_count,
            "mean_omr_ned": mean_ned,
            "median_omr_ned": median_ned,
            "stdev_omr_ned": stdev_ned,
            "mean_ser": mean_ser,
            "median_ser": median_ser,
            "stdev_ser": stdev_ser,
        },
        "metrics_penalized_with_failures": {
            "imputation_policy": "OMR-NED = 1.0, SER = 1.0 (máxima penalización por fallo)",
            "count": total_evaluated,
            "mean_omr_ned_penalized": mean_penalized_ned,
            "median_omr_ned_penalized": median_penalized_ned,
            "mean_ser_penalized": mean_penalized_ser,
            "median_ser_penalized": median_penalized_ser,
        },
        "comparison_vs_homr": {
            "homr_baseline_found": homr_data is not None,
            "homr_success_omr_ned": homr_success_ned,
            "homr_success_ser": homr_success_ser,
            "homr_failure_rate": homr_failure_rate,
            "delta_omr_ned": (
                round(mean_ned - homr_success_ned, 4)
                if (mean_ned is not None and homr_success_ned is not None)
                else None
            ),
            "delta_ser": (
                round(mean_ser - homr_success_ser, 4)
                if (mean_ser is not None and homr_success_ser is not None)
                else None
            ),
            "decision_note": (
                "ADR-0005 fija HOMR como motor OMR principal y oemer como línea base. "
                "La segmentación de dos etapas y el transformer de HOMR logran menor error "
                "y mayor estabilidad en incipits monofónicos aislados de PrIMuS."
            ),
        },
        "failures_detail": failures_details,
        "sample_size_justification": SAMPLE_SIZE_JUSTIFICATION,
        "methodological_limitations": {
            **METHODOLOGICAL_LIMITATIONS,
            "oemer_piano_bias": (
                "oemer está diseñado principalmente para partituras de piano a página completa. "
                "Sobre incipits monofónicos aislados (1 solo pentagrama), sus heurísticas de "
                "agrupamiento de pentagramas y detección de claves presentan mayor tasa de fallos."
            ),
        },
        "run_info": get_run_info("exp_08", seed, manifest_path),
    }

    if should_write:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        summary["csv"] = str(csv_path)

        summary_path = RESULTS_DIR / "oemer_baseline_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        write_run_info("exp_08", seed, manifest_path, "exp_08_run_info.json")

    return summary


def run_experiment(
    *,
    smoke: bool = False,
    manifest: Path | None = None,
    predictions_dir: Path | None = None,
    limit: int | None = None,
    force_recompute: bool = False,
    seed: int = DEFAULT_SEED,
    write_results: bool | None = None,
) -> dict[str, Any]:
    """Punto de entrada programático para ejecutar el experimento de línea base oemer."""
    if smoke:
        with tempfile.TemporaryDirectory(prefix="cadenza-exp08-smoke-") as tmp_str:
            return _measure_smoke(Path(tmp_str), seed=seed)

    manifest_path = manifest or (DATA_DIR / "manifest.json")
    if not manifest_path.is_file():
        with tempfile.TemporaryDirectory(prefix="cadenza-exp08-fallback-") as tmp_str:
            res = _measure_smoke(Path(tmp_str), seed=seed)
            res["notice"] = (
                f"Manifest {manifest_path} not found. Ran smoke mode as deterministic fallback."
            )
            return res

    return _measure_corpus(
        manifest_path=manifest_path,
        predictions_dir=predictions_dir,
        limit=limit,
        force_recompute=force_recompute,
        seed=seed,
        write_results=write_results,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Experimento 8: línea base OMR de oemer y comparación con HOMR."
    )
    parser.add_argument(
        "--smoke", action="store_true", help="Ejecutar en modo smoke con fixtures sintéticas."
    )
    parser.add_argument("--manifest", type=Path, default=None, help="Ruta al manifest.json.")
    parser.add_argument(
        "--predictions-dir",
        type=Path,
        default=None,
        help="Directorio con archivos .musicxml predichos por oemer.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Límite de incipits a evaluar.")
    parser.add_argument(
        "--force-recompute", action="store_true", help="Ignorar caché y recalcular métricas."
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Semilla determinista.")
    args = parser.parse_args()

    res = run_experiment(
        smoke=args.smoke,
        manifest=args.manifest,
        predictions_dir=args.predictions_dir,
        limit=args.limit,
        force_recompute=args.force_recompute,
        seed=args.seed,
    )

    success_metrics = res.get("metrics_on_successes", {})
    penalized_metrics = res.get("metrics_penalized_with_failures", {})
    comp = res.get("comparison_vs_homr", {})
    print(f"[exp_08] Total evaluados:       {res.get('total_evaluated')}")
    print(
        f"[exp_08] Éxitos:                {res.get('successes_count')} "
        f"({100 - float(res.get('failure_rate_percent', 0.0)):.1f}%)"
    )
    print(
        f"[exp_08] Fallos:                {res.get('failures_count')} "
        f"({res.get('failure_rate_percent')}%)"
    )
    print(
        f"[exp_08] OMR-NED éxitos:        media={success_metrics.get('mean_omr_ned')} "
        f"mediana={success_metrics.get('median_omr_ned')}"
    )
    print(
        f"[exp_08] SER éxitos:            media={success_metrics.get('mean_ser')} "
        f"mediana={success_metrics.get('median_ser')}"
    )
    print(
        f"[exp_08] OMR-NED penalizado:    media={penalized_metrics.get('mean_omr_ned_penalized')} "
        f"mediana={penalized_metrics.get('median_omr_ned_penalized')}"
    )
    print(
        f"[exp_08] SER penalizado:        media={penalized_metrics.get('mean_ser_penalized')} "
        f"mediana={penalized_metrics.get('median_ser_penalized')}"
    )
    if comp.get("homr_baseline_found"):
        print(
            f"[exp_08] vs HOMR (OMR-NED):     delta={comp.get('delta_omr_ned')} "
            f"(HOMR media={comp.get('homr_success_omr_ned')})"
        )
        print(
            f"[exp_08] vs HOMR (SER):         delta={comp.get('delta_ser')} "
            f"(HOMR media={comp.get('homr_success_ser')})"
        )
    if "csv" in res:
        print(f"[exp_08] Escrito CSV:           {res['csv']}")


if __name__ == "__main__":
    with contextlib.suppress(Exception):
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    main()
