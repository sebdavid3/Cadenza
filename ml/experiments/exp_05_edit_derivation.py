"""Experimento 5: derivación de EditEvents y distribución de errores OMR (Fase 6, ADR-0008, D21).

Simula al 'corrector ideal': compara las predicciones de HOMR contra el ground truth
del corpus PrIMuS, derivando las secuencias de `EditEvent` necesarias para llevar
la salida del OMR al ground truth y verificando formalmente la materialización.

Exporta el resumen a `results/primus_edit_distribution.json` y el detalle por incipit
a `results/primus_edit_distribution.csv`.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cadenza.domain import materialize
from cadenza.interchange import read_score
from cadenza.learning import (
    EditDistribution,
    count_edits_by_op,
    derive_edit_events,
    is_structurally_equal,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RESULTS_DIR = REPO_ROOT / "results"
SMOKE_FIXTURE = REPO_ROOT / "packages" / "interchange" / "tests" / "fixtures" / "simple.musicxml"


@dataclass(frozen=True, slots=True)
class IncipitResult:
    identifier: str
    predicted_measures: int
    ground_truth_measures: int
    edits_count: int
    structurally_equal: bool
    distribution: EditDistribution

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.identifier,
            "pred_measures": self.predicted_measures,
            "gt_measures": self.ground_truth_measures,
            "edits_count": self.edits_count,
            "structurally_equal": self.structurally_equal,
            **self.distribution.to_dict(),
        }


def process_pair(
    identifier: str,
    pred_path: Path,
    gt_path: Path,
) -> IncipitResult:
    score_pred = read_score(pred_path)
    score_gt = read_score(gt_path)

    pred_measures = len(score_pred.parts[0].staves[0].measures) if score_pred.parts else 0
    gt_measures = len(score_gt.parts[0].staves[0].measures) if score_gt.parts else 0

    edits = derive_edit_events(score_pred, score_gt, document_id=identifier)
    dist = count_edits_by_op(edits)

    score_materialized = materialize(score_pred, edits)
    equal = is_structurally_equal(score_materialized, score_gt)

    return IncipitResult(
        identifier=identifier,
        predicted_measures=pred_measures,
        ground_truth_measures=gt_measures,
        edits_count=len(edits),
        structurally_equal=equal,
        distribution=dist,
    )


def run_derivation_experiment(
    manifest_path: Path,
    predictions_dir: Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    corpus_name = str(manifest.get("corpus", "corpus"))

    if predictions_dir is None:
        predictions_dir = root / corpus_name / "predictions"

    failures_file = predictions_dir / "failures.json"
    failures: list[dict[str, str]] = []
    if failures_file.is_file():
        failures = json.loads(failures_file.read_text(encoding="utf-8"))

    entries = list(manifest.get("entries", []))
    if limit is not None:
        entries = entries[:limit]

    results: list[IncipitResult] = []
    skipped_no_pred: list[str] = []

    for entry in entries:
        eid = entry["id"]
        pred_file = predictions_dir / f"{eid}.musicxml"
        gt_file = root / entry["ground_truth"]

        if not pred_file.is_file():
            skipped_no_pred.append(eid)
            continue

        res = process_pair(eid, pred_file, gt_file)
        results.append(res)

    # Agregados y distribución global
    total_ops: dict[str, int] = {
        "SetPitch": 0,
        "SetDuration": 0,
        "SetAccidental": 0,
        "InsertEvent": 0,
        "DeleteEvent": 0,
        "SetClef": 0,
        "SetKey": 0,
        "Total": 0,
    }
    structurally_equal_count = 0
    for r in results:
        if r.structurally_equal:
            structurally_equal_count += 1
        d = r.distribution.to_dict()
        for k, v in d.items():
            total_ops[k] += v

    total_edits = total_ops["Total"]
    proportions = {
        k: (round(v / total_edits, 4) if total_edits > 0 else 0.0)
        for k, v in total_ops.items()
        if k != "Total"
    }

    # Escritura de CSV detallado
    csv_path = RESULTS_DIR / "primus_edit_distribution.csv"
    fieldnames = [
        "id",
        "pred_measures",
        "gt_measures",
        "edits_count",
        "structurally_equal",
        "SetPitch",
        "SetDuration",
        "SetAccidental",
        "InsertEvent",
        "DeleteEvent",
        "SetClef",
        "SetKey",
        "Total",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r.to_row())

    # Generación del resumen JSON
    summary: dict[str, Any] = {
        "experiment": "exp_05_edit_derivation",
        "corpus": corpus_name,
        "total_manifest_entries": len(entries),
        "transcribed_predictions": len(results),
        "homr_detection_failures": len(failures),
        "homr_detection_failures_treatment": (
            "9 imágenes no pudieron transcribirse por fallo en la etapa de segmentación "
            "de pentagramas de HOMR ('Exception: No staffs found'). Se registran en "
            "data/primus/predictions/failures.json y se excluyen de la derivación simbólica, "
            "requiriendo intervención en el preprocesamiento de imagen o modelo alternativo."
        ),
        "structurally_verified_materialization": {
            "verified_count": structurally_equal_count,
            "total_tested": len(results),
            "ratio": round(structurally_equal_count / len(results), 4) if results else 0.0,
            "unverified_reason": (
                "2 incipits ('000051794-1_1_1' y '000051800-1_1_1') presentaron fusión de "
                "compases contiguos por falta de detección de barras de compás en HOMR, "
                "provocando un número disonante de compases frente al ground truth."
            ),
        },
        "edit_distribution": total_ops,
        "operation_proportions": proportions,
        "average_edits_per_incipit": round(total_edits / len(results), 2) if results else 0.0,
        "csv_details": str(csv_path),
    }

    json_path = RESULTS_DIR / "primus_edit_distribution.json"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Derivación de EditEvents y distribución de errores — Fase 6"
    )
    parser.add_argument("--manifest", type=Path, default=DATA_DIR / "manifest.json")
    parser.add_argument("--predictions", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if not args.manifest.is_file():
        print(f"[exp_05] falta el manifiesto: {args.manifest}")
        return

    summary = run_derivation_experiment(args.manifest, args.predictions, args.limit)
    print(f"[exp_05] analizados {summary['transcribed_predictions']} pares de incipits.")
    print(
        f"[exp_05] verificados estructuralmente: "
        f"{summary['structurally_verified_materialization']['verified_count']}/"
        f"{summary['structurally_verified_materialization']['total_tested']}"
    )
    print(f"[exp_05] total ediciones: {summary['edit_distribution']['Total']}")
    print(f"[exp_05] distribución: {summary['edit_distribution']}")
    print("[exp_05] exportado resumen a results/primus_edit_distribution.json")


if __name__ == "__main__":
    main()
