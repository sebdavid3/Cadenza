"""Experimento 17: HOMR sobre páginas reales escaneadas (Sheet Music Benchmark, #102).

SMB (`PRAIG/SMB` en Hugging Face, ISMIR 2025) son 685 páginas escaneadas de KernScores con
4 039 regiones (pentagramas o sistemas), cada una con su verdad en **kern, que
`packages/interchange` lee. Este experimento recorta cada región, la pasa por HOMR y mide la
tasa de fallos, el OMR-NED y la SER por textura (monodia, piano, cuarteto, otras), y saca un
corpus de correcciones con el formato del de `exp_12` y `source = smb`, para que
`ml export-tables --corpus` lo lea.

**Pendiente de ejecutar.** El conjunto tiene acceso restringido con aprobación manual: el
responsable tiene que pedirlo con su cuenta y bajar el parquet
(`data/test-00000-of-00001.parquet`, 366 854 135 bytes) a `data/smb/`. Leerlo necesita
`pyarrow`, que no es dependencia del proyecto mientras no haya datos (ver INV-0003).

La unidad es la región, como el incipit de `exp_12`: la página entera mezclaría la lectura de
cada sistema con la de su orden. El recorte es la caja de la región, sin margen (`--margin`
lo cambia): conviene un piloto con unas decenas de regiones antes de la ejecución completa.

Fases (subcomandos):
1. `prepare`: recorta las regiones con **kern, escribe su imagen y su verdad y el manifiesto
   `data/smb/exp_17/manifest.json` con los sha256.
2. `transcribe`: HOMR en la GPU por defecto (ADR-0066), sin preprocesado.
3. `build`: mide y escribe las salidas.

Salidas (`results/`, sin versionar):
- `smb_homr_regions.csv`: una fila por región.
- `smb_homr_summary.json`: fallos, métricas y correcciones por textura.
- `smb_correction_corpus.jsonl`: los registros de las regiones derivadas.
- `exp_17_run_info.json`
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from cadenza.interchange import read_score
from cadenza.learning import DEFAULT_TEST_FRACTION, assign_split

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.experiments.common import (  # noqa: E402
    DATA_DIR,
    DEFAULT_SEED,
    METHODOLOGICAL_LIMITATIONS,
    RESULTS_DIR,
    get_run_info,
    sample_size_justification,
    sha256_of_file,
)
from ml.experiments.external_corpus import (  # noqa: E402
    OPS,
    check_complete,
    data_root,
    distribution,
    load_manifest,
    measure_pair,
    rate,
    stats,
    transcribe,
    write_json,
    write_jsonl,
)

LABEL = "exp_17"
SOURCE = "smb"
CORPUS_DIR = "smb"
PARQUET = Path("smb") / "test-00000-of-00001.parquet"

CSV_FIELDS = [
    "id",
    "page_id",
    "region",
    "work",
    "texture",
    "split",
    "status",
    "error",
    "pred_measures",
    "gt_measures",
    "verified",
    *OPS,
    "Total",
    "ser",
    "omr_ned",
]

LIMITATIONS: dict[str, str] = {
    **METHODOLOGICAL_LIMITATIONS,
    "kernscores_and_grandstaff": (
        "Las obras de SMB salen de KernScores, como GrandStaff, con el que se entrenó el "
        "transformador de HOMR (renderizadas, no escaneadas): HOMR puede haber visto la música "
        "de algunas regiones, aunque no sus imágenes. Sus autores usan además SMB como banco "
        "de comparación al elegir modelos."
    ),
    "region_crops": (
        "Cada región se recorta con su caja; HOMR la lee como una imagen aparte. En producción "
        "lee la página entera."
    ),
    "ideal_corrector": (
        "Las correcciones son las del corrector ideal: la alineación de coste mínimo entre lo "
        "que leyó HOMR y la verdad, no las que haría una persona."
    ),
}


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_") or "page"


# --- 1. Preparación ----------------------------------------------------------------------


def read_parquet_pages(parquet: Path) -> Iterator[dict[str, Any]]:
    """Las páginas del parquet de SMB, con los bytes de su imagen."""
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Leer el parquet de SMB necesita pyarrow: `uv add --group dev pyarrow --no-sync` "
            "y después `uv sync --inexact` (nunca `uv sync` a secas, CLAUDE.md §7)."
        ) from exc
    table = pq.read_table(parquet)
    for row in table.to_pylist():
        image = row.get("image") or {}
        yield {**row, "image_bytes": image.get("bytes")}


def prepare_pages(
    pages: Iterable[Mapping[str, Any]],
    data_dir: Path,
    *,
    source: Mapping[str, Any],
    margin: float = 0.0,
    force: bool = False,
) -> dict[str, Any]:
    """Recorta las regiones con **kern y escribe su imagen, su verdad y el manifiesto."""
    import cv2
    import numpy as np

    target = data_dir / CORPUS_DIR / LABEL / "manifest.json"
    if target.is_file() and not force:
        raise FileExistsError(
            f"Ya hay un manifiesto en {target}; sus predicciones son de él. Repite con --force."
        )
    images_dir = target.parent / "images"
    kern_dir = target.parent / "kern"
    images_dir.mkdir(parents=True, exist_ok=True)
    kern_dir.mkdir(parents=True, exist_ok=True)

    def relative(path: Path) -> str:
        return path.relative_to(data_dir).as_posix()

    entries: list[dict[str, Any]] = []
    skipped = Counter[str]()
    page_count = 0
    seen: set[str] = set()
    for page in pages:
        page_count += 1
        page_id = _slug(str(page.get("id") or page_count))
        if page_id in seen:
            raise ValueError(f"Página repetida en SMB: {page_id}")
        seen.add(page_id)
        raw = page.get("image_bytes")
        if not raw:
            raise ValueError(f"La página {page_id} no trae imagen")
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError(f"No se puede decodificar la imagen de la página {page_id}")
        height, width = image.shape[:2]
        work = str(page.get("original_score") or page_id)
        for index, region in enumerate(page.get("regions") or []):
            kern = region.get("kern")
            if not kern or not str(kern).strip():
                skipped["without_kern"] += 1
                continue
            box = region["bbox"]
            # La caja va en porcentajes de la imagen.
            x0 = box["x"] / 100 * width
            y0 = box["y"] / 100 * height
            x1 = x0 + box["width"] / 100 * width
            y1 = y0 + box["height"] / 100 * height
            pad = margin * (y1 - y0)
            left, top = max(0, int(x0 - pad)), max(0, int(y0 - pad))
            right, bottom = min(width, round(x1 + pad)), min(height, round(y1 + pad))
            if right - left < 2 or bottom - top < 2:
                skipped["empty_box"] += 1
                continue
            item = f"{page_id}_r{index:02d}"
            image_path = images_dir / f"{item}.png"
            if not cv2.imwrite(str(image_path), image[top:bottom, left:right]):
                raise OSError(f"No se pudo escribir {image_path}")
            kern_path = kern_dir / f"{item}.krn"
            kern_path.write_text(str(kern).rstrip("\n") + "\n", encoding="utf-8")
            entries.append(
                {
                    "id": item,
                    "page_id": page_id,
                    "region": index,
                    "work": work,
                    "texture": str(page.get("page_texture") or "unknown"),
                    "image": relative(image_path),
                    "image_sha256": sha256_of_file(image_path),
                    "ground_truth": relative(kern_path),
                    "ground_truth_sha256": sha256_of_file(kern_path),
                    "box_pixels": [left, top, right, bottom],
                }
            )
    if not entries:
        raise ValueError("SMB no trae ninguna región con **kern")
    manifest: dict[str, Any] = {
        "corpus": "smb",
        "experiment": LABEL,
        "seed": DEFAULT_SEED,
        "source": dict(source),
        "selection": "todas las regiones con **kern de todas las páginas",
        "margin": margin,
        "pages": page_count,
        "skipped_regions": dict(skipped),
        "count": len(entries),
        "entries": entries,
    }
    write_json(target, manifest)
    return manifest


def prepare(
    data_dir: Path = DATA_DIR, *, margin: float = 0.0, force: bool = False
) -> dict[str, Any]:
    parquet = data_dir / PARQUET
    if not parquet.is_file():
        raise FileNotFoundError(
            f"exp_17 necesita el parquet de SMB en {parquet}: el acceso a PRAIG/SMB es "
            "restringido y lo pide el responsable (ver docs/investigaciones/INV-0003)."
        )
    source = {"file": parquet.name, "sha256": sha256_of_file(parquet)}
    return prepare_pages(
        read_parquet_pages(parquet), data_dir, source=source, margin=margin, force=force
    )


# --- 3. Medición -------------------------------------------------------------------------


def _measures(score: Any) -> int:
    return max((len(staff.measures) for part in score.parts for staff in part.staves), default=0)


def build(
    manifest_path: Path,
    *,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    with_omr_ned: bool = True,
) -> dict[str, Any]:
    """Mide y escribe las salidas. Todo se escribe al final, con todo medido."""
    manifest = load_manifest(manifest_path, label=LABEL)
    seed = int(manifest["seed"])
    entries: list[dict[str, Any]] = manifest["entries"]
    root = data_root(manifest_path)
    predictions, failures, homr_info = check_complete(manifest_path, entries, label=LABEL)

    rows: list[dict[str, Any]] = []
    corpus: list[dict[str, Any]] = []
    ops_by_texture: dict[str, Counter[str]] = {}
    pred_unreadable: dict[str, str] = {}
    gt_unreadable: dict[str, str] = {}
    derive_errors: dict[str, str] = {}

    for entry in entries:
        item, texture = entry["id"], entry["texture"]
        work = f"smb:{entry['work']}"
        split = assign_split(work, seed=seed, test_fraction=test_fraction)
        row: dict[str, Any] = dict.fromkeys(CSV_FIELDS, "")
        row.update(
            {
                "id": item,
                "page_id": entry["page_id"],
                "region": entry["region"],
                "work": entry["work"],
                "texture": texture,
                "split": split,
            }
        )
        rows.append(row)
        if item in failures:
            row.update({"status": "failure", "error": failures[item]})
            continue
        pred_file = predictions / f"{item}.musicxml"
        gt_file = root / entry["ground_truth"]
        try:
            predicted = read_score(pred_file)
        except ValueError as exc:
            pred_unreadable[item] = f"{type(exc).__name__}: {exc}"
            row.update({"status": "prediction_unreadable", "error": pred_unreadable[item]})
            continue
        try:
            truth = read_score(gt_file)
        except ValueError as exc:
            gt_unreadable[item] = f"{type(exc).__name__}: {exc}"
            row.update({"status": "gt_unreadable", "error": gt_unreadable[item]})
            continue
        row.update({"pred_measures": _measures(predicted), "gt_measures": _measures(truth)})
        try:
            measured = measure_pair(
                predicted,
                truth,
                item=item,
                split=split,
                source=SOURCE,
                work=work,
                pred_file=pred_file,
                truth_file=gt_file if with_omr_ned else None,
            )
        except (ValueError, IndexError) as exc:
            derive_errors[item] = f"{type(exc).__name__}: {exc}"
            row.update({"status": "derive_error", "error": derive_errors[item]})
            continue
        corpus.extend(measured.records)
        ops_by_texture.setdefault(texture, Counter()).update(
            {op: measured.counts[op] for op in OPS}
        )
        row.update(measured.row())

    def values(key: str, scope: list[dict[str, Any]]) -> list[float]:
        return [float(r[key]) for r in scope if r[key] != ""]

    def group(scope: list[dict[str, Any]]) -> dict[str, Any]:
        derived = [r for r in scope if r["status"] == "derived"]
        return {
            "regions": len(scope),
            "failures": rate(sum(1 for r in scope if r["status"] == "failure"), len(scope)),
            "derived": len(derived),
            "verification": rate(sum(1 for r in derived if r["verified"]), len(derived)),
            "ser": stats(values("ser", derived)),
            "omr_ned": stats(values("omr_ned", derived)),
        }

    textures = sorted({r["texture"] for r in rows})
    total_ops: Counter[str] = Counter()
    for counter in ops_by_texture.values():
        total_ops.update(counter)
    failures_count = sum(1 for r in rows if r["status"] == "failure")
    derived_rows = [r for r in rows if r["status"] == "derived"]
    summary: dict[str, Any] = {
        "experiment": "exp_17_smb_homr",
        "issue": 102,
        "corpus": "Sheet Music Benchmark (PRAIG/SMB), regiones con **kern",
        "seed": seed,
        "sample": {
            "regions": len(rows),
            "pages": manifest.get("pages"),
            "source": manifest.get("source"),
            "margin": manifest.get("margin"),
            "skipped_regions": manifest.get("skipped_regions"),
        },
        "transcription": {
            **homr_info,
            "failures": rate(failures_count, len(rows)),
            "failures_by_error": dict(
                Counter(r["error"] for r in rows if r["status"] == "failure")
            ),
            "prediction_unreadable": dict(sorted(pred_unreadable.items())),
        },
        "ground_truth": {
            "unreadable_count": len(gt_unreadable),
            "unreadable": dict(sorted(gt_unreadable.items())),
        },
        "all": group(rows),
        "by_texture": {t: group([r for r in rows if r["texture"] == t]) for t in textures},
        "edit_distribution": {
            "all_derived": distribution(total_ops),
            "by_texture": {t: distribution(c) for t, c in sorted(ops_by_texture.items())},
        },
        "derive_errors": dict(sorted(derive_errors.items())),
        "correction_corpus": {
            "records": len(corpus),
            "by_kind": dict(Counter(r["record"] for r in corpus)),
            "by_split": dict(Counter(r["split"] for r in corpus)),
            "records_of_verified_regions": sum(1 for r in corpus if r["verified"]),
            "source": SOURCE,
            "split_rule": (
                "assign_split(f'smb:{obra}', seed, test_fraction), con la obra el "
                "`original_score` de la página: las regiones de una obra caen del mismo lado"
            ),
            "test_fraction": test_fraction,
        },
        "sample_size_justification": sample_size_justification(
            "smb",
            counts={"regions": len(rows), "derived_regions": len(derived_rows)},
            proportions={"failure_rate": (failures_count, len(rows))},
            worst_case={"corrections": sum(total_ops.values())},
        ),
        "methodological_limitations": LIMITATIONS,
    }

    results = RESULTS_DIR
    results.mkdir(parents=True, exist_ok=True)
    corpus_path = results / "smb_correction_corpus.jsonl"
    write_jsonl(corpus_path, corpus)
    with (results / "smb_homr_regions.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    run_info = {
        **get_run_info(LABEL, seed=seed, manifest_path=manifest_path),
        "homr": homr_info,
        "test_fraction": test_fraction,
        "omr_ned": with_omr_ned,
        "corpus_sha256": sha256_of_file(corpus_path),
    }
    summary["run_info"] = run_info
    write_json(results / "smb_homr_summary.json", summary)
    write_json(results / "exp_17_run_info.json", run_info)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="HOMR sobre SMB (#102)")
    parser.add_argument("--data", type=Path, default=DATA_DIR)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare", help="Recorta las regiones y escribe la muestra")
    prepare_parser.add_argument("--margin", type=float, default=0.0)
    prepare_parser.add_argument("--force", action="store_true")
    transcribe_parser = sub.add_parser("transcribe", help="Transcribe la muestra con HOMR")
    transcribe_parser.add_argument("--cpu", action="store_true", help="Usar la CPU")
    transcribe_parser.add_argument("--force", action="store_true")
    transcribe_parser.add_argument("--retry-failures", action="store_true")
    transcribe_parser.add_argument("--limit", type=int, default=None)
    build_parser = sub.add_parser("build", help="Mide y escribe las salidas")
    build_parser.add_argument("--test-fraction", type=float, default=DEFAULT_TEST_FRACTION)
    build_parser.add_argument("--no-omr-ned", action="store_true")
    args = parser.parse_args()

    logging.getLogger("converter21").setLevel(logging.ERROR)
    manifest_path = args.data / CORPUS_DIR / LABEL / "manifest.json"
    if args.command == "prepare":
        manifest = prepare(args.data, margin=args.margin, force=args.force)
        print(f"[{LABEL}] {manifest['count']} regiones -> {manifest_path}")
    elif args.command == "transcribe":
        result = transcribe(
            manifest_path,
            label=LABEL,
            use_gpu=not args.cpu,
            force=args.force,
            retry_failures=args.retry_failures,
            limit=args.limit,
        )
        print(f"[{LABEL}] transcripción: {result}")
    else:
        summary = build(
            manifest_path, test_fraction=args.test_fraction, with_omr_ned=not args.no_omr_ned
        )
        print(f"[{LABEL}] {summary['all']}")


if __name__ == "__main__":
    main()
