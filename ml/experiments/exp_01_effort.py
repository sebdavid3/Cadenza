"""Experimento 1: reducción de esfuerzo de inspección con validador sobre datos reales.

Fase 7, Issue #24, D17, D19.
Compara dos flujos de revisión sobre transcripciones reales de HOMR del corpus PrIMuS:
1. **Línea base (manual no asistida):** el revisor inspecciona todos los compases
   secuencialmente, por lo que el esfuerzo es O(N) compases.
2. **Línea asistida con validador:** el revisor inspecciona únicamente los compases
   señalados con al menos un hallazgo (`flagged_measures`), reduciendo el esfuerzo a O(X).

Reporta con rigor metodológico:
- Compases totales inspeccionados con y sin validador.
- Reducción porcentual de esfuerzo de inspección.
- Compases con errores reales cometidos por HOMR (obtenidos del diff simbólico con Ground Truth).
- **Errores reales que quedarían sin revisar** (falsos negativos / tasa de fuga del validador)
  y su desglose por tipo de operación, documentando honestamente las limitaciones
  de un validador sintáctico frente a errores musicales semánticos dentro de escala.
- Justificación estadística del tamaño de muestra y limitaciones del corpus.

Salidas:
- `results/effort_comparison.json`
- `results/effort_comparison_by_score.csv`
- `results/exp_01_run_info.json`
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cadenza.interchange import read_score
from cadenza.learning import (
    MeasureEvaluationRecord,
    evaluate_pair,
)
from cadenza.validation import ValidationEngine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.experiments.common import (  # noqa: E402
    DEFAULT_SEED,
    METHODOLOGICAL_LIMITATIONS,
    RESULTS_DIR,
    sample_size_justification,
    write_run_info,
)

DATA_DIR = REPO_ROOT / "data"


@dataclass(frozen=True, slots=True)
class ScoreEffortSummary:
    score_id: str
    total_measures: int
    clean_measures: int
    error_measures: int
    assisted_inspections: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    effort_reduction_ratio: float
    missed_errors_count: int

    def to_row(self) -> dict[str, Any]:
        return {
            "score_id": self.score_id,
            "total_measures": self.total_measures,
            "clean_measures": self.clean_measures,
            "error_measures": self.error_measures,
            "assisted_inspections": self.assisted_inspections,
            "tp_detected": self.true_positives,
            "fp_alarm": self.false_positives,
            "fn_missed": self.false_negatives,
            "tn_clean": self.true_negatives,
            "effort_reduction_percent": round(self.effort_reduction_ratio * 100, 2),
            "missed_errors_count": self.missed_errors_count,
        }


def _missed_errors_interpretation(
    *,
    missed_operations: dict[str, int],
    fn_missed: int,
    measures_with_real_errors: int,
    baseline_inspections: int,
    assisted_inspections: int,
) -> str:
    """Resume los errores que escapan al validador solo con lo medido (CLAUDE.md §8.1, #139)."""
    if baseline_inspections == 0:
        return "No se evaluó ningún compás: no hay esfuerzo ni errores que resumir."
    reduction = 1.0 - assisted_inspections / baseline_inspections
    if measures_with_real_errors == 0:
        return (
            f"Ningún compás tiene error real en esta muestra, así que la tasa de errores sin "
            f"revisar no está definida. El validador ahorra el {reduction * 100:.2f}% de las "
            f"inspecciones ({baseline_inspections} manuales frente a {assisted_inspections} "
            "asistidas)."
        )
    missed_rate = fn_missed / measures_with_real_errors
    text = (
        f"El {missed_rate * 100:.2f}% de los compases con error real escapan al validador "
        f"({fn_missed} de {measures_with_real_errors})."
    )
    total_ops = sum(missed_operations.values())
    if total_ops:
        ranked = sorted(missed_operations.items(), key=lambda item: (-item[1], item[0]))
        shares = ", ".join(f"{op} {count} ({count / total_ops * 100:.2f}%)" for op, count in ranked)
        text += f" Operaciones de corrección en esos compases: {shares}."
    text += (
        f" El validador ahorra el {reduction * 100:.2f}% de las inspecciones "
        f"({baseline_inspections} manuales frente a {assisted_inspections} asistidas)."
    )
    if fn_missed:
        text += " Los compases que no señala solo se corrigen con inspección humana (HITL)."
    else:
        text += " En esta muestra señala todos los compases con error real."
    return text


def _run_real_primus(
    manifest_path: Path,
    predictions_dir: Path | None = None,
    limit: int | None = None,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Ejecuta el experimento sobre las transcripciones reales de HOMR en PrIMuS."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    corpus_name = str(manifest.get("corpus", "corpus"))

    if predictions_dir is None:
        predictions_dir = root / corpus_name / "predictions"

    validator = ValidationEngine()
    entries = list(manifest.get("entries", []))
    if limit is not None:
        entries = entries[:limit]

    all_records: list[MeasureEvaluationRecord] = []
    score_summaries: list[ScoreEffortSummary] = []
    skipped_no_pred: list[str] = []

    for entry in entries:
        eid = entry["id"]
        pred_file = predictions_dir / f"{eid}.musicxml"
        gt_file = root / entry["ground_truth"]

        if not pred_file.is_file() or not gt_file.is_file():
            skipped_no_pred.append(eid)
            continue

        try:
            score_pred = read_score(pred_file)
            score_gt = read_score(gt_file)
        except Exception:
            skipped_no_pred.append(eid)
            continue

        records = evaluate_pair(eid, score_pred, score_gt, validator)
        all_records.extend(records)

        # Resumen por obra
        s_total = len(records)
        s_errors = sum(1 for r in records if r.has_real_error)
        s_clean = s_total - s_errors
        s_flagged = sum(1 for r in records if r.flagged_global)
        s_tp = sum(1 for r in records if r.has_real_error and r.flagged_global)
        s_fp = sum(1 for r in records if not r.has_real_error and r.flagged_global)
        s_fn = sum(1 for r in records if r.has_real_error and not r.flagged_global)
        s_tn = sum(1 for r in records if not r.has_real_error and not r.flagged_global)
        s_reduction = 0.0 if s_total == 0 else 1.0 - (s_flagged / s_total)

        score_summaries.append(
            ScoreEffortSummary(
                score_id=eid,
                total_measures=s_total,
                clean_measures=s_clean,
                error_measures=s_errors,
                assisted_inspections=s_flagged,
                true_positives=s_tp,
                false_positives=s_fp,
                false_negatives=s_fn,
                true_negatives=s_tn,
                effort_reduction_ratio=s_reduction,
                missed_errors_count=s_fn,
            )
        )

    if not score_summaries:
        # Sin predicciones no hay medición: nada de resultados con ceros (CLAUDE.md §8.1).
        raise ValueError(
            f"exp_01 no encontró ninguna predicción utilizable en {predictions_dir} para las "
            f"{len(entries)} entradas de {manifest_path}: ejecuta antes `exp_04` "
            "(transcripción con HOMR) o indica `--predictions`."
        )

    # Agregados globales
    total_measures = len(all_records)
    measures_with_real_errors = sum(1 for r in all_records if r.has_real_error)
    clean_measures = total_measures - measures_with_real_errors

    baseline_inspections = total_measures
    assisted_inspections = sum(1 for r in all_records if r.flagged_global)
    effort_reduction_ratio = (
        0.0 if baseline_inspections == 0 else 1.0 - (assisted_inspections / baseline_inspections)
    )

    tp_detected = sum(1 for r in all_records if r.has_real_error and r.flagged_global)
    fp_alarms = sum(1 for r in all_records if not r.has_real_error and r.flagged_global)
    fn_missed = sum(1 for r in all_records if r.has_real_error and not r.flagged_global)
    tn_clean = sum(1 for r in all_records if not r.has_real_error and not r.flagged_global)

    missed_error_rate = (
        0.0 if measures_with_real_errors == 0 else fn_missed / measures_with_real_errors
    )
    error_coverage_recall = (
        0.0 if measures_with_real_errors == 0 else tp_detected / measures_with_real_errors
    )
    precision = 0.0 if assisted_inspections == 0 else tp_detected / assisted_inspections

    # Desglose de los errores reales que quedarían sin revisar (FN)
    missed_operations: dict[str, int] = {}
    missed_categories: dict[str, int] = {}
    for r in all_records:
        if r.has_real_error and not r.flagged_global:
            for op in r.error_operations:
                missed_operations[op] = missed_operations.get(op, 0) + 1
            for cat in r.error_categories:
                missed_categories[cat] = missed_categories.get(cat, 0) + 1

    # Escritura de CSV por obra
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "effort_comparison_by_score.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "score_id",
            "total_measures",
            "clean_measures",
            "error_measures",
            "assisted_inspections",
            "tp_detected",
            "fp_alarm",
            "fn_missed",
            "tn_clean",
            "effort_reduction_percent",
            "missed_errors_count",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for summary in score_summaries:
            writer.writerow(summary.to_row())

    run_info = write_run_info("exp_01", seed=seed, manifest_path=manifest_path)

    result_payload: dict[str, Any] = {
        "experiment": "exp_01_effort",
        "mode": f"real_data_{corpus_name}",
        "corpus": corpus_name,
        "seed": seed,
        "transcribed_scores": len(score_summaries),
        "skipped_scores": len(skipped_no_pred),
        "inspection_effort": {
            "total_measures": total_measures,
            "baseline_inspections_manual": baseline_inspections,
            "assisted_inspections_validator": assisted_inspections,
            "effort_reduction_ratio": round(effort_reduction_ratio, 4),
            "effort_reduction_percent": round(effort_reduction_ratio * 100, 2),
            "measures_saved": baseline_inspections - assisted_inspections,
        },
        "error_detection_and_tradeoff": {
            "measures_with_real_errors": measures_with_real_errors,
            "clean_measures": clean_measures,
            "true_positives_detected": tp_detected,
            "false_positives_alarms": fp_alarms,
            "false_negatives_missed": fn_missed,
            "true_negatives_passed": tn_clean,
            "precision": round(precision, 4),
            "recall_coverage": round(error_coverage_recall, 4),
            "missed_errors_rate": round(missed_error_rate, 4),
            "missed_errors_percent": round(missed_error_rate * 100, 2),
        },
        "missed_errors_breakdown": {
            "by_operation": missed_operations,
            "by_category": missed_categories,
            "scientific_interpretation": _missed_errors_interpretation(
                missed_operations=missed_operations,
                fn_missed=fn_missed,
                measures_with_real_errors=measures_with_real_errors,
                baseline_inspections=baseline_inspections,
                assisted_inspections=assisted_inspections,
            ),
        },
        "sample_size_justification": sample_size_justification(
            corpus_name,
            counts={
                "entries_considered": len(entries),
                "transcribed_scores": len(score_summaries),
                "skipped_scores": len(skipped_no_pred),
                "total_measures": total_measures,
                "measures_with_errors": measures_with_real_errors,
            },
            proportions={
                "measures_with_real_errors": (measures_with_real_errors, total_measures),
                "assisted_inspections": (assisted_inspections, total_measures),
                "missed_errors": (fn_missed, measures_with_real_errors),
            },
        ),
        "methodological_limitations": METHODOLOGICAL_LIMITATIONS,
        "run_info": run_info,
        "csv_by_score": str(csv_path),
    }

    return result_payload


def run(
    manifest_path: Path | None = None,
    predictions_dir: Path | None = None,
    limit: int | None = None,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Punto de entrada de exp_01."""
    manifest = manifest_path or (DATA_DIR / "manifest.json")
    if not manifest.is_file():
        # Sin corpus no hay resultado: nada de valores de reserva (CLAUDE.md §8.1).
        raise FileNotFoundError(
            f"exp_01 requiere el corpus PrIMuS descargado y su manifiesto ({manifest}). "
            "Genéralo con `ml/experiments/corpus.py fetch` y `manifest` (ver ml/README.md)."
        )
    return _run_real_primus(manifest, predictions_dir=predictions_dir, limit=limit, seed=seed)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Experimento 1: Reducción de esfuerzo de inspección sobre datos reales"
    )
    parser.add_argument("--manifest", type=Path, default=DATA_DIR / "manifest.json")
    parser.add_argument("--predictions", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    result = run(
        manifest_path=args.manifest,
        predictions_dir=args.predictions,
        limit=args.limit,
        seed=args.seed,
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = RESULTS_DIR / "effort_comparison.json"
    out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    effort = result["inspection_effort"]
    tradeoff = result["error_detection_and_tradeoff"]
    print(
        f"[exp_01] Modo={result['mode']} "
        f"Compases={effort['total_measures']} "
        f"Manual={effort['baseline_inspections_manual']} "
        f"Asistido={effort['assisted_inspections_validator']} "
        f"Reducción={effort['effort_reduction_percent']}%"
    )
    print(
        f"[exp_01] Errores reales={tradeoff['measures_with_real_errors']} "
        f"Detectados={tradeoff['true_positives_detected']} "
        f"Sin revisar={tradeoff['false_negatives_missed']} "
        f"Tasa sin revisar={tradeoff['missed_errors_percent']}%"
    )
    print(f"[exp_01] Escrito: {out_file}")


if __name__ == "__main__":
    main()
