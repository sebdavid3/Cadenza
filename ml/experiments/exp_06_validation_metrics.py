"""Experimento 6: métricas del validador sobre errores reales (Fase 7, Issue #18, D8).

Evalúa el catálogo completo de reglas de validación (`ValidationEngine`) sobre los
errores reales cometidos por HOMR en el corpus PrIMuS (obtenidos del diff simbólico
con el ground truth vía `derive_edit_events`).

Mide a nivel de compás:
1. Precisión, recall, F1, especificidad y exactitud globales.
2. Desglose por regla del catálogo (`DEFAULT_RULES_CATALOG`, ADR-0040 §3).
3. Cobertura por categoría de error real (duración, altura, alteración, estructura, clave/armadura).
4. Diagnóstico analítico de qué errores son detectables sintácticamente y cuáles
   requieren señal visual.

Cada salida lleva la versión de las reglas con que se midió: `rules_version` (la lista de
identificadores) y `rules_catalog_version` (`RULES_CATALOG_VERSION`), en el resumen, en la
cobertura y en cada fila de los CSV (ADR-0040 §15.6). Una medición con el catálogo nuevo es
una medición nueva, que se documenta junto a la anterior: el experimento no sobrescribe un
resumen de otra versión del catálogo (`common.guard_rules_catalog`) y pide otro `--output-dir`.

Salidas (`--output-dir`, por defecto `results/`):
- `validation_metrics_summary.json`
- `validation_metrics_by_rule.csv`
- `validation_metrics_by_measure.csv`
- `validation_error_coverage.json`
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from cadenza.interchange import read_score
from cadenza.learning import (
    MeasureEvaluationRecord,
    ValidationEvaluationReport,
    aggregate_validation_metrics,
    evaluate_pair,
)
from cadenza.validation import ValidationEngine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.experiments.common import guard_rules_catalog, rules_catalog_info  # noqa: E402

DATA_DIR = REPO_ROOT / "data"
RESULTS_DIR = REPO_ROOT / "results"
SUMMARY_NAME = "validation_metrics_summary.json"


def run_validation_experiment(
    manifest_path: Path,
    predictions_dir: Path | None = None,
    limit: int | None = None,
    output_dir: Path | None = None,
) -> ValidationEvaluationReport:
    results = RESULTS_DIR if output_dir is None else output_dir
    guard_rules_catalog(results / SUMMARY_NAME)
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"exp_06 requiere el corpus descargado y su manifiesto ({manifest_path}). "
            "Genéralo con `ml/experiments/corpus.py fetch` y `manifest` (ver ml/README.md)."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    corpus_name = str(manifest.get("corpus", "corpus"))

    if predictions_dir is None:
        predictions_dir = root / corpus_name / "predictions"

    validator = ValidationEngine()
    version = rules_catalog_info(validator)
    entries = list(manifest.get("entries", []))
    if limit is not None:
        entries = entries[:limit]

    all_records: list[MeasureEvaluationRecord] = []

    for entry in entries:
        eid = entry["id"]
        pred_file = predictions_dir / f"{eid}.musicxml"
        gt_file = root / entry["ground_truth"]

        if not pred_file.is_file() or not gt_file.is_file():
            continue

        score_pred = read_score(pred_file)
        score_gt = read_score(gt_file)

        records = evaluate_pair(eid, score_pred, score_gt, validator)
        all_records.extend(records)

    if not all_records:
        # Sin predicciones no hay medición: nada de resultados con ceros (CLAUDE.md §8.1, #139).
        raise ValueError(
            f"exp_06 no encontró ninguna predicción con su verdad de referencia en "
            f"{predictions_dir} para las {len(entries)} entradas de {manifest_path}: ejecuta "
            "antes `exp_04` (transcripción con HOMR) o indica `--predictions`."
        )
    results.mkdir(parents=True, exist_ok=True)
    report = aggregate_validation_metrics(
        all_records, known_rules=validator.rules_version.split(",")
    )

    # 1. Exportar CSV por compás
    measure_csv_path = results / "validation_metrics_by_measure.csv"
    measure_fields = [
        "score_id",
        "part_index",
        "staff_index",
        "measure_number",
        "has_real_error",
        "error_operations",
        "error_categories",
        "flagged_global",
        "flagged_rules",
        *version,
    ]
    with measure_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=measure_fields)
        writer.writeheader()
        for r in all_records:
            writer.writerow({**r.to_row(), **version})

    # 2. Exportar CSV por regla
    rules_csv_path = results / "validation_metrics_by_rule.csv"
    rule_fields = [
        "rule_id",
        "tp",
        "fp",
        "fn",
        "tn",
        "total",
        "precision",
        "recall",
        "f1",
        "accuracy",
        "specificity",
        *version,
    ]
    with rules_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rule_fields)
        writer.writeheader()
        # Fila global
        writer.writerow({"rule_id": "GLOBAL", **report.global_metrics.to_dict(), **version})
        for rule_id, metrics in sorted(report.metrics_by_rule.items()):
            writer.writerow({"rule_id": rule_id, **metrics.to_dict(), **version})

    # 3. Exportar JSON de cobertura por categoría
    coverage_json_path = results / "validation_error_coverage.json"
    coverage_dict = {
        **version,
        **{cat: cov.to_dict() for cat, cov in report.coverage_by_category.items()},
    }
    coverage_json_path.write_text(
        json.dumps(coverage_dict, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 4. Exportar resumen JSON completo
    summary_path = results / SUMMARY_NAME
    summary_data: dict[str, Any] = {
        "experiment": "exp_06_validation_metrics",
        "corpus": corpus_name,
        **version,
        "csv_measures": str(measure_csv_path),
        "csv_rules": str(rules_csv_path),
        "json_coverage": str(coverage_json_path),
        **report.to_dict(),
    }
    summary_path.write_text(
        json.dumps(summary_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Precisión, recall y F1 del validador sobre errores reales — Fase 7"
    )
    parser.add_argument("--manifest", type=Path, default=DATA_DIR / "manifest.json")
    parser.add_argument("--predictions", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="por defecto results/; no sobrescribe una medición de otra versión del catálogo",
    )
    args = parser.parse_args()

    report = run_validation_experiment(args.manifest, args.predictions, args.limit, args.output_dir)
    results = RESULTS_DIR if args.output_dir is None else args.output_dir
    print(
        f"[exp_06] Evaluados {report.total_measures} compases en {report.total_scores} partituras."
    )
    print(f"[exp_06] Compases con error real: {report.measures_with_real_errors}")
    print(f"[exp_06] Compases marcados por validador: {report.measures_flagged}")
    print(
        f"[exp_06] GLOBAL: Precision={report.global_metrics.precision} "
        f"Recall={report.global_metrics.recall} F1={report.global_metrics.f1} "
        f"(TP={report.global_metrics.tp}, FP={report.global_metrics.fp}, "
        f"FN={report.global_metrics.fn}, TN={report.global_metrics.tn})"
    )
    print("[exp_06] Por regla:")
    for rule_id, m in sorted(report.metrics_by_rule.items()):
        print(f"  - {rule_id}: P={m.precision} R={m.recall} F1={m.f1} (TP={m.tp}, FP={m.fp})")
    print("[exp_06] Cobertura por categoría de error:")
    for cat, cov in sorted(report.coverage_by_category.items()):
        det = cov.detected_measures
        tot = cov.total_measures_with_error
        print(f"  - {cat}: tasa={cov.coverage_rate} ({det}/{tot})")
    print(f"[exp_06] Resumen guardado en {results / SUMMARY_NAME}")


if __name__ == "__main__":
    main()
