"""Experimento 3: calidad OMR con la métrica oficial OMR-NED (Fase 6).

Compara las predicciones de HOMR contra el ground truth del corpus usando
`musicdiff`. Si no hay corpus descargado (`data/manifest.json`), corre en modo
*smoke* con el fixture de MusicXML del propio repositorio, para verificar el
pipeline de medición de extremo a extremo.

Salida: `results/omr_baseline.csv` y `results/omr_baseline_summary.json`.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cadenza.learning import OmrNedResult, omr_ned_pair

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RESULTS_DIR = REPO_ROOT / "results"
SMOKE_FIXTURE = REPO_ROOT / "packages" / "interchange" / "tests" / "fixtures" / "simple.musicxml"
CSV_FIELDS = [
    "id",
    "predicted",
    "ground_truth",
    "predicted_symbols",
    "ground_truth_symbols",
    "edit_distance",
    "omr_ned",
]


@dataclass(frozen=True, slots=True)
class Pair:
    identifier: str
    predicted: Path
    ground_truth: Path


def _smoke_pair(tmp_path: Path) -> list[Pair]:
    """Par de humo: fixture como ground truth y copia alterada como predicción."""

    if not SMOKE_FIXTURE.is_file():
        return []
    altered = tmp_path / "smoke_prediction.musicxml"
    altered.write_text(
        SMOKE_FIXTURE.read_text(encoding="utf-8").replace("<step>C</step>", "<step>E</step>"),
        encoding="utf-8",
    )
    return [Pair("smoke", altered, SMOKE_FIXTURE)]


def _manifest_pairs(manifest_path: Path, predictions_dir: Path) -> tuple[str, list[Pair]]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    pairs = [
        Pair(entry["id"], predictions_dir / f"{entry['id']}.musicxml", root / entry["ground_truth"])
        for entry in data.get("entries", [])
        if (predictions_dir / f"{entry['id']}.musicxml").is_file()
    ]
    return str(data.get("corpus", "corpus")), pairs


def _measure(pairs: list[Pair], *, mode: str, corpus: str) -> dict[str, object]:
    results: list[OmrNedResult] = [
        omr_ned_pair(pair.predicted, pair.ground_truth) for pair in pairs
    ]
    rows = [
        {"id": pair.identifier, **result.to_primitive()}
        for pair, result in zip(pairs, results, strict=True)
    ]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "omr_baseline.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    values = [result.omr_ned for result in results]
    summary = {
        "experiment": "exp_03_omr_quality",
        "mode": mode,
        "corpus": corpus,
        "count": len(rows),
        "mean_omr_ned": round(statistics.fmean(values), 4) if values else None,
        "median_omr_ned": round(statistics.median(values), 4) if values else None,
        "csv": str(csv_path),
    }
    (RESULTS_DIR / "omr_baseline_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


def run(manifest: Path, predictions: Path | None, limit: int | None) -> dict[str, object]:
    if predictions is None:
        corpus_name = str(json.loads(manifest.read_text(encoding="utf-8")).get("corpus", "corpus"))
        predictions = manifest.parent / corpus_name / "predictions"
    corpus, pairs = _manifest_pairs(manifest, predictions)
    if limit is not None:
        pairs = pairs[:limit]
    return _measure(pairs, mode="corpus", corpus=corpus)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calidad OMR (OMR-NED) — Fase 6")
    parser.add_argument("--manifest", type=Path, default=DATA_DIR / "manifest.json")
    parser.add_argument("--predictions", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if args.manifest.is_file():
        summary = run(args.manifest, args.predictions, args.limit)
    else:
        with tempfile.TemporaryDirectory(prefix="cadenza-exp03-") as tmp:
            pairs = _smoke_pair(Path(tmp))
            if not pairs:
                print("[exp_03] sin corpus y sin fixture de humo; nada que medir")
                return
            summary = _measure(pairs, mode="smoke", corpus="smoke")

    print(
        f"[exp_03] modo={summary['mode']} n={summary['count']} "
        f"OMR-NED medio={summary['mean_omr_ned']}"
    )
    print(f"[exp_03] escrito: {summary['csv']}")


if __name__ == "__main__":
    main()
