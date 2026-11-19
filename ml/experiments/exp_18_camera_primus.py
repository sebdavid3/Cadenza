"""Experimento 18: corpus de correcciones con una muestra de Camera-PrIMuS (#421).

Camera-PrIMuS (Calvo-Zaragoza y Rizo, 2018) trae los 87 678 incipits de PrIMuS con la imagen
distorsionada para que parezca una foto (`<id>_distorted.jpg`), con el mismo MEI y el mismo
`.semantic`: más cerca de lo que se sube a Cadenza que la imagen limpia de `exp_12`. El alcance
lo decidió el responsable el 2026-11-19: una muestra de Camera-PrIMuS, no todo PrIMuS.

Reutiliza las fases de `exp_12` (#255) sin cambiarlo: la transcripción reanudable de
`external_corpus` (#102), la altura que suena del `.semantic`, la derivación del corrector
ideal y su verificación (`external_corpus.measure_pair`) y el análisis de la armadura, el
compás y la clave de `exp_12`.

Fases (subcomandos):
1. `prepare`: ordena al azar con la semilla los incipits completos (imagen distorsionada, MEI y
   `.semantic`) que no están en `exp_03` y toma los primeros: una muestra mayor con la misma
   semilla empieza por la menor, así que ampliarla no repite lo ya leído. Escribe
   `data/camera_primus/exp_18/manifest.json` con los sha256.
2. `transcribe`: HOMR sin preprocesado, con una predicción por incipit en `predictions/` y los
   fallos del motor en `failures.json`. Se reanuda sin repetir; un error que no es del motor
   detiene la ejecución.
3. `build`: deriva y verifica las correcciones y escribe el corpus por nota, la partición y el
   análisis.

En el corpus, cada incipit es `camera-primus:<id de PrIMuS>` y `source` es `camera-primus`: los
mismos incipits de `exp_12` no se confunden con los suyos en `ml export-tables`. La obra
(`work_id`) es el registro RISM, como en #255, y la partición usa la semilla y la fracción de
`exp_12`: comprueba contra `correction_corpus_split.json` que cada obra queda del mismo lado.

Sin el manifiesto de `exp_03`, sin la partición de `exp_12`, sin la muestra o con alguna entrada
sin predicción ni fallo registrado, el experimento falla: no hay valores de reserva (CLAUDE.md
§8).

Salidas (`results/`, sin versionar; archivos nuevos, los de `exp_12` no se tocan):
- `camera_primus_correction_corpus.jsonl`: un registro por evento leído, inserción y compás.
- `camera_primus_correction_corpus_incipits.csv`: una fila por incipit de la muestra.
- `camera_primus_correction_corpus_split.json`: la partición por incipit.
- `camera_primus_correction_corpus_summary.json`: verificación, distribución y análisis.
- `exp_18_run_info.json`
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from cadenza.interchange import read_score
from cadenza.learning import (
    DEFAULT_TEST_FRACTION,
    SemanticMismatch,
    assign_split,
    primus_work_id,
    semantic_note_pitches,
    with_sounding_pitches,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.experiments import external_corpus  # noqa: E402
from ml.experiments.common import (  # noqa: E402
    DATA_DIR,
    DEFAULT_SEED,
    RESULTS_DIR,
    get_run_info,
    sample_size_justification,
    sha256_of_file,
)
from ml.experiments.exp_12_correction_corpus import (  # noqa: E402
    LIMITATIONS as EXP_12_LIMITATIONS,
)
from ml.experiments.exp_12_correction_corpus import (  # noqa: E402
    _context_analysis,
    _incipit_analysis,
    _measure_count,
)

EXPERIMENT = "exp_18"
SOURCE = "camera-primus"
CORPUS_DIR = "camera_primus"
SAMPLE_SIZE = 10_000
OPS = external_corpus.OPS
OUTPUT_PREFIX = "camera_primus_correction_corpus"
EXP_12_SPLIT = "correction_corpus_split.json"
CSV_FIELDS = [
    "id",
    "primus_id",
    "work_id",
    "split",
    "status",
    "error",
    "pred_measures",
    "gt_measures",
    "verified",
    *OPS,
    "Total",
    "key_read",
    "key_true",
    "key_misread",
    "time_read",
    "time_true",
    "time_misread",
    "clef_misread",
    "mei_pitch_not_sounding",
    "ser",
    "omr_ned",
    "omr_ned_error",
]

LIMITATIONS: dict[str, str] = {
    **EXP_12_LIMITATIONS,
    "synthetic_camera_distortion": (
        "Las distorsiones de Camera-PrIMuS son sintéticas: imitan una foto (deformación, giro, "
        "desenfoque, luz), pero no son fotos de partituras reales hechas con un móvil."
    ),
    "same_incipits_as_primus": (
        "Son los mismos incipits que PrIMuS: los de exp_12 que salgan en la muestra aparecen en "
        "los dos corpus, con otra imagen. Quedan del mismo lado de la partición porque la obra y "
        "la semilla son las de #255."
    ),
}


def corpus_id(incipit: str) -> str:
    """El identificador de un incipit en el corpus: lleva la fuente, como `cadenza:<sesión>`."""
    return f"{SOURCE}:{incipit}"


def _manifest_path(data_dir: Path) -> Path:
    return data_dir / CORPUS_DIR / EXPERIMENT / "manifest.json"


# --- 1. Muestra --------------------------------------------------------------------------


def _complete_incipits(corpus_dir: Path) -> list[str]:
    """Incipits con imagen distorsionada, MEI y `.semantic`, ordenados."""
    found: list[str] = []
    with os.scandir(corpus_dir) as folders:
        for folder in folders:
            if not folder.is_dir():
                continue
            with os.scandir(folder.path) as children:
                names = {child.name for child in children}
            incipit = folder.name
            wanted = (f"{incipit}_distorted.jpg", f"{incipit}.mei", f"{incipit}.semantic")
            if all(name in names for name in wanted):
                found.append(folder.name)
    return sorted(found)


def select_sample(
    data_dir: Path = DATA_DIR,
    *,
    size: int = SAMPLE_SIZE,
    seed: int = DEFAULT_SEED,
    force: bool = False,
) -> dict[str, Any]:
    """Los `size` primeros incipits completos de una ordenación al azar con `seed`, sin los de
    `exp_03`.

    No sustituye una muestra que ya existe salvo con `force`. Al sustituirla, las predicciones se
    conservan si una muestra empieza por la otra (se amplió o se redujo con la misma semilla) y,
    si no, se apartan sin borrarlas (`external_corpus.set_aside_predictions`). La semilla ha de
    ser la de `exp_12` (la de por defecto) para que `build` acepte la partición.
    """
    if size < 1:
        raise ValueError(f"exp_18 necesita una muestra de al menos un incipit, no {size}")
    target = _manifest_path(data_dir)
    if target.is_file() and not force:
        raise FileExistsError(
            f"Ya hay una muestra en {target}; sus predicciones son de ella. Repite con "
            "--force para sustituirla o ampliarla."
        )
    exp_03_manifest = data_dir / "manifest.json"
    if not exp_03_manifest.is_file():
        raise FileNotFoundError(
            f"exp_18 necesita el manifiesto de exp_03 ({exp_03_manifest}) para no solaparse "
            "con sus incipits."
        )
    excluded = {
        entry["id"] for entry in json.loads(exp_03_manifest.read_text(encoding="utf-8"))["entries"]
    }
    corpus_dir = data_dir / CORPUS_DIR / "Corpus"
    pool = [incipit for incipit in _complete_incipits(corpus_dir) if incipit not in excluded]
    if len(pool) < size:
        raise ValueError(
            f"exp_18 pide {size} incipits y solo hay {len(pool)} incipits completos (imagen "
            f"distorsionada, MEI y .semantic) fuera de exp_03 en {corpus_dir}."
        )
    order = list(pool)
    random.Random(seed).shuffle(order)
    chosen = order[:size]

    def relative(path: Path) -> str:
        return path.relative_to(data_dir).as_posix()

    entries = []
    for incipit in chosen:
        folder = corpus_dir / incipit
        files = {
            "image": folder / f"{incipit}_distorted.jpg",
            "ground_truth": folder / f"{incipit}.mei",
            "semantic": folder / f"{incipit}.semantic",
        }
        entry: dict[str, Any] = {"id": incipit}
        for key, path in files.items():
            entry[key] = relative(path)
            entry[f"{key}_sha256"] = sha256_of_file(path)
        entries.append(entry)

    previous = json.loads(target.read_text(encoding="utf-8")) if target.is_file() else None
    manifest: dict[str, Any] = {
        "corpus": CORPUS_DIR,
        "source": SOURCE,
        "experiment": EXPERIMENT,
        "issue": 421,
        "seed": seed,
        "selection": {
            "rule": (
                "random.Random(seed).shuffle de los incipits completos (imagen distorsionada, MEI "
                "y .semantic) fuera de exp_03, ordenados, y los `count` primeros"
            ),
            "candidates": len(pool),
            "candidates_sha256": hashlib.sha256("\n".join(pool).encode("utf-8")).hexdigest(),
            "excluded_exp_03": len(excluded),
            "exp_03_manifest_sha256": sha256_of_file(exp_03_manifest),
        },
        "count": len(entries),
        "entries": entries,
    }
    if previous is not None and not _same_order(previous, manifest):
        external_corpus.set_aside_predictions(target)
    external_corpus.write_json(target, manifest)
    return manifest


def _same_order(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    """Si una muestra empieza por la otra (se amplió o se redujo con la misma semilla y los
    mismos candidatos): las predicciones de la anterior siguen siendo de sus incipits."""
    old = previous.get("entries") or []
    shared = min(len(old), len(current["entries"]))
    return bool(
        previous.get("seed") == current["seed"]
        and previous.get("selection") == current["selection"]
        and current["entries"][:shared] == old[:shared]
    )


# --- 2. Transcripción --------------------------------------------------------------------


def transcribe(
    manifest_path: Path,
    *,
    use_gpu: bool = True,
    force: bool = False,
    retry_failures: bool = False,
    limit: int | None = None,
    engine: external_corpus.Transcriber | None = None,
) -> dict[str, int]:
    """La fase `transcribe` de `exp_12`, sobre la muestra de Camera-PrIMuS, en la GPU por
    defecto, como en producción (ADR-0066)."""
    return external_corpus.transcribe(
        manifest_path,
        label=EXPERIMENT,
        use_gpu=use_gpu,
        force=force,
        retry_failures=retry_failures,
        limit=limit,
        engine=engine,
    )


# --- 3. Corpus y análisis ----------------------------------------------------------------


def _measure(
    entry: dict[str, Any],
    failure: str | None,
    *,
    root: Path,
    predictions: Path,
    seed: int,
    test_fraction: float,
    with_omr_ned: bool,
) -> dict[str, Any]:
    """Mide un incipit: su fila del CSV, sus registros del corpus y su análisis.

    Lo que el dominio no lee, un `.semantic` que no casa con el MEI o una derivación que falla
    se registran en la fila y no detienen el cálculo, como en `exp_12`.
    """
    incipit = entry["id"]
    item = corpus_id(incipit)
    work = primus_work_id(incipit)
    split = assign_split(work, seed=seed, test_fraction=test_fraction)
    row: dict[str, Any] = dict.fromkeys(CSV_FIELDS, "")
    row.update({"id": item, "primus_id": incipit, "work_id": work, "split": split})
    out: dict[str, Any] = {"row": row, "records": [], "analysis": None, "counts": None}
    if failure is not None:
        row.update({"status": "failure", "error": failure})
        return out

    pred_file = predictions / f"{incipit}.musicxml"
    gt_file = root / entry["ground_truth"]
    try:
        predicted = read_score(pred_file)
    except ValueError as exc:
        row.update({"status": "prediction_unreadable", "error": f"{type(exc).__name__}: {exc}"})
        return out
    try:
        mei = read_score(gt_file)
    except ValueError as exc:
        row.update({"status": "gt_unreadable", "error": f"{type(exc).__name__}: {exc}"})
        return out
    try:
        sounding = with_sounding_pitches(
            mei,
            semantic_note_pitches((root / entry["semantic"]).read_text(encoding="utf-8")),
        )
    except SemanticMismatch as exc:
        row.update({"status": "gt_mismatch", "error": str(exc)})
        return out
    try:
        measured = external_corpus.measure_pair(
            predicted,
            sounding,
            item=item,
            split=split,
            source=SOURCE,
            work=work,
            pred_file=pred_file,
            truth_file=gt_file if with_omr_ned else None,
        )
    except (ValueError, IndexError) as exc:
        row.update({"status": "derive_error", "error": f"{type(exc).__name__}: {exc}"})
        return out

    analysis = _incipit_analysis(item, predicted, sounding, mei, measured.records)
    row.update(measured.row())
    row.update(
        {
            "pred_measures": _measure_count(predicted),
            "gt_measures": _measure_count(sounding),
            "key_read": analysis["key_read"],
            "key_true": analysis["key_true"],
            "key_misread": analysis["key_misread"],
            "time_read": analysis["time_read"],
            "time_true": analysis["time_true"],
            "time_misread": analysis["time_misread"],
            "clef_misread": measured.counts["SetClef"] > 0,
            "mei_pitch_not_sounding": analysis["mei_pitch_not_sounding"],
        }
    )
    out.update(
        {
            "records": measured.records,
            "analysis": analysis,
            "counts": measured.counts,
            "ser": measured.ser,
            "omr_ned": measured.omr_ned,
        }
    )
    return out


def _disable_power_throttling() -> None:
    """Sin EcoQoS: Windows frena un cálculo largo en segundo plano (#255)."""
    from cadenza.omr import disable_power_throttling

    disable_power_throttling()
    # converter21 avisa de cada <multiRest> del MEI; el aviso no cambia la medición.
    logging.getLogger("converter21").setLevel(logging.ERROR)


def _exp_12_split(split_path: Path, *, seed: int, test_fraction: float) -> dict[str, Any]:
    """La partición de `exp_12`, si usa la semilla y la fracción de esta muestra."""
    if not split_path.is_file():
        raise FileNotFoundError(
            f"exp_18 necesita la partición de exp_12 ({split_path}) para comprobar que cada obra "
            "queda del mismo lado que en #255."
        )
    theirs: dict[str, Any] = json.loads(split_path.read_text(encoding="utf-8"))
    if theirs.get("seed") != seed:
        raise ValueError(
            f"La partición de exp_12 usa la semilla {theirs.get('seed')} y la muestra de exp_18, "
            f"{seed}: las obras no caerían del mismo lado."
        )
    if theirs.get("test_fraction") != test_fraction:
        raise ValueError(
            f"La partición de exp_12 usa la fracción de prueba {theirs.get('test_fraction')} y "
            f"exp_18, {test_fraction}: las obras no caerían del mismo lado."
        )
    return theirs


def _exp_12_compatibility(
    split_path: Path, theirs: dict[str, Any], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Comprueba que cada obra que la muestra comparte con `exp_12` queda del mismo lado."""
    their_side: dict[str, str] = {}
    for side in ("train", "test"):
        for incipit in theirs.get(side, []):
            their_side[primus_work_id(str(incipit))] = side
    ours: dict[str, str] = {row["work_id"]: row["split"] for row in rows}
    shared = sorted(set(ours) & set(their_side))
    disagreements = [work for work in shared if ours[work] != their_side[work]]
    if disagreements:
        raise ValueError(
            f"{len(disagreements)} obras caen en otro lado que en exp_12 (p. ej. "
            f"{disagreements[:3]}): la partición no es la de #255."
        )
    their_ids = {str(i) for side in ("train", "test") for i in theirs.get(side, [])}
    return {
        "exp_12_split_sha256": sha256_of_file(split_path),
        "seed": theirs["seed"],
        "test_fraction": theirs["test_fraction"],
        "shared_incipits": sum(1 for row in rows if row["primus_id"] in their_ids),
        "shared_works": len(shared),
        "disagreements": 0,
    }


def build(
    manifest_path: Path,
    *,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    with_omr_ned: bool = True,
    limit: int | None = None,
    results_dir: Path | None = None,
    exp_12_split: Path | None = None,
) -> dict[str, Any]:
    """Deriva y verifica las correcciones, escribe el corpus y analiza los errores.

    La semilla de la partición es la de la muestra, y ha de ser la de `exp_12`. Con `limit`,
    solo las primeras entradas de la muestra. `results_dir` es `results/` por defecto, y la
    partición de `exp_12` se lee de él si no se da `exp_12_split`.
    """
    results = RESULTS_DIR if results_dir is None else results_dir
    split_path = results / EXP_12_SPLIT if exp_12_split is None else exp_12_split
    manifest = external_corpus.load_manifest(manifest_path, label=EXPERIMENT)
    sample_seed = manifest.get("seed")
    if sample_seed is None:
        raise ValueError(f"La muestra {manifest_path} no dice con qué semilla se eligió")
    seed = int(sample_seed)
    entries: list[dict[str, Any]] = manifest["entries"][:limit]
    root = external_corpus.data_root(manifest_path)
    predictions, failures, homr_info = external_corpus.check_complete(
        manifest_path, entries, label=EXPERIMENT
    )
    # Antes de medir: sin la partición de exp_12 no se puede comprobar la de #255.
    theirs = _exp_12_split(split_path, seed=seed, test_fraction=test_fraction)

    rows: list[dict[str, Any]] = []
    corpus: list[dict[str, Any]] = []
    key_rows: list[dict[str, Any]] = []
    ops_all: Counter[str] = Counter()
    ops_verified_by_split: dict[str, Counter[str]] = {"train": Counter(), "test": Counter()}
    unverified: list[str] = []
    unverified_measure_mismatch: list[str] = []
    ser_values: list[float] = []
    ned_values: list[float] = []
    started = time.monotonic()
    for position, entry in enumerate(entries, start=1):
        result = _measure(
            entry,
            failures.get(entry["id"]),
            root=root,
            predictions=predictions,
            seed=seed,
            test_fraction=test_fraction,
            with_omr_ned=with_omr_ned,
        )
        row = result["row"]
        rows.append(row)
        if position % 200 == 0:
            print(
                f"[{EXPERIMENT}] {position}/{len(entries)} incipits "
                f"({time.monotonic() - started:.0f} s)",
                flush=True,
            )
        if row["status"] != "derived":
            continue
        corpus.extend(result["records"])
        counts = result["counts"]
        ops_all.update({op: counts[op] for op in OPS})
        ser_values.append(result["ser"])
        if result["omr_ned"] is not None:
            ned_values.append(result["omr_ned"])
        if row["verified"]:
            ops_verified_by_split[row["split"]].update({op: counts[op] for op in OPS})
            key_rows.append(result["analysis"])
        else:
            unverified.append(row["primus_id"])
            if row["pred_measures"] != row["gt_measures"]:
                unverified_measure_mismatch.append(row["primus_id"])

    compatibility = _exp_12_compatibility(split_path, theirs, rows)

    def by_status(status: str) -> dict[str, str]:
        return {row["primus_id"]: row["error"] for row in rows if row["status"] == status}

    derived = [row for row in rows if row["status"] == "derived"]
    verified_rows = [row for row in derived if row["verified"]]
    verified_ids = {row["id"] for row in verified_rows}
    verified_records = [r for r in corpus if r["incipit_id"] in verified_ids]
    ops_verified = ops_verified_by_split["train"] + ops_verified_by_split["test"]
    sampled = len(entries)
    failure_errors = by_status("failure")
    pred_unreadable = by_status("prediction_unreadable")
    unreadable = by_status("gt_unreadable")
    mismatches = by_status("gt_mismatch")
    derive_errors = by_status("derive_error")
    ned_errors = {row["primus_id"]: row["omr_ned_error"] for row in derived if row["omr_ned_error"]}

    split_payload = {
        "seed": seed,
        "test_fraction": test_fraction,
        "rule": (
            "test si int.from_bytes(sha256(f'{seed}:{obra}')[:8], 'big') / 2**64 < "
            "test_fraction (cadenza.learning.assign_split), con la obra el registro RISM del "
            "incipit de PrIMuS (cadenza.learning.primus_work_id): la de #255, con su semilla y su "
            "fracción, así que cada obra queda del mismo lado que en exp_12"
        ),
        "train": sorted(row["id"] for row in rows if row["split"] == "train"),
        "test": sorted(row["id"] for row in rows if row["split"] == "test"),
    }
    summary: dict[str, Any] = {
        "experiment": "exp_18_camera_primus",
        "issue": 421,
        "corpus": CORPUS_DIR,
        "source": SOURCE,
        "simulated": False,
        "seed": seed,
        "sample": {
            "size": sampled,
            "manifest_count": len(manifest["entries"]),
            "limit": limit,
            "partial": sampled < len(manifest["entries"]),
            "selection": manifest.get("selection"),
        },
        "ids": (
            "Las listas de este resumen usan el identificador de PrIMuS; el corpus, la partición "
            "y la columna `id` del CSV, `camera-primus:<id>` (`primus_id`, el de PrIMuS)."
        ),
        "transcription": {
            **homr_info,
            "transcribed": sampled - len(failure_errors),
            "failures_count": len(failure_errors),
            "failure_rate": round(len(failure_errors) / sampled, 4),
            "failures_by_error": dict(Counter(failure_errors.values())),
            "prediction_unreadable_count": len(pred_unreadable),
            "prediction_unreadable": dict(sorted(pred_unreadable.items())),
        },
        "ground_truth": {
            "source": "MEI de Camera-PrIMuS (el de PrIMuS) con la altura que suena del .semantic",
            "semantic_mismatch_count": len(mismatches),
            "semantic_mismatch_ids": sorted(mismatches),
            "unreadable_count": len(unreadable),
            "unreadable": dict(sorted(unreadable.items())),
            "mei_without_key_accidentals": {
                "incipits_affected": sum(1 for row in derived if row["mei_pitch_not_sounding"]),
                "notes_whose_mei_pitch_is_not_the_sounding_one": sum(
                    row["mei_pitch_not_sounding"] for row in derived
                ),
                "scope": "todos los incipits derivados, verificados o no",
            },
        },
        "verification": {
            "derived_count": len(derived),
            "verified_count": len(verified_rows),
            "rate": round(len(verified_rows) / len(derived), 4) if derived else None,
            "by_split": {
                split: external_corpus.rate(
                    sum(1 for row in verified_rows if row["split"] == split),
                    sum(1 for row in derived if row["split"] == split),
                )
                for split in ("train", "test")
            },
            "unverified_ids": unverified,
            "unverified_with_measure_count_mismatch": unverified_measure_mismatch,
            "derive_errors_count": len(derive_errors),
            "derive_errors": dict(sorted(derive_errors.items())),
        },
        "edit_distribution": {
            "verified": external_corpus.distribution(ops_verified),
            "verified_by_split": {
                split: external_corpus.distribution(counter)
                for split, counter in ops_verified_by_split.items()
            },
            "all_derived": external_corpus.distribution(ops_all),
            "average_edits_per_verified_incipit": (
                round(sum(ops_verified.values()) / len(verified_rows), 2) if verified_rows else None
            ),
        },
        "context_analysis": _context_analysis(verified_records, key_rows),
        "time_signature": {
            "incipits_with_time_misread": external_corpus.rate(
                sum(1 for row in derived if row["time_misread"]), len(derived)
            ),
            "scope": "todos los incipits derivados",
        },
        "ser": external_corpus.stats(ser_values),
        "omr_ned": external_corpus.stats(ned_values),
        "omr_ned_errors": dict(sorted(ned_errors.items())),
        "exp_12_compatibility": compatibility,
        "correction_corpus": {
            "records": len(corpus),
            "records_of_verified_incipits": len(verified_records),
            "by_kind": dict(Counter(r["record"] for r in corpus)),
            "by_split_verified": dict(Counter(r["split"] for r in verified_records)),
            "events_with_correction_verified": sum(
                1 for r in verified_records if r["record"] == "event" and r["correction"]
            ),
            "format": (
                "JSONL con el formato de exp_12 (cadenza.learning.correction_corpus), más "
                "`source: camera-primus` y `work_id` (el registro RISM). `incipit_id` es "
                "`camera-primus:<id de PrIMuS>`. Solo los de `verified` son etiquetas de confianza."
            ),
        },
        "sample_size_justification": sample_size_justification(
            CORPUS_DIR,
            counts={
                "sampled_incipits": sampled,
                "derived_incipits": len(derived),
                "verified_incipits": len(verified_rows),
                "verified_corrections": sum(ops_verified.values()),
            },
            proportions={
                "failure_rate": (len(failure_errors), sampled),
                "verification_rate": (len(verified_rows), len(derived)),
            },
            worst_case={"verified_corrections": sum(ops_verified.values())},
        ),
        "methodological_limitations": LIMITATIONS,
    }

    # Todo se escribe al final, con todo medido: un fallo a medias no deja salidas.
    results.mkdir(parents=True, exist_ok=True)
    corpus_path = results / f"{OUTPUT_PREFIX}.jsonl"
    external_corpus.write_jsonl(corpus_path, corpus)
    with (results / f"{OUTPUT_PREFIX}_incipits.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    split_file = results / f"{OUTPUT_PREFIX}_split.json"
    external_corpus.write_json(split_file, split_payload)
    run_info = {
        **get_run_info(EXPERIMENT, seed=seed, manifest_path=manifest_path),
        "manifest_path": _data_relative(manifest_path, root),
        "manifest_sha256": sha256_of_file(manifest_path),
        "simulated": False,
        "homr": homr_info,
        "test_fraction": test_fraction,
        "omr_ned": with_omr_ned,
        "limit": limit,
        "manifest_count": len(manifest["entries"]),
        "partial": sampled < len(manifest["entries"]),
        "corpus_sha256": sha256_of_file(corpus_path),
        "split_sha256": sha256_of_file(split_file),
        "exp_12_split_sha256": compatibility["exp_12_split_sha256"],
    }
    summary["run_info"] = run_info
    external_corpus.write_json(results / f"{OUTPUT_PREFIX}_summary.json", summary)
    external_corpus.write_json(results / f"{EXPERIMENT}_run_info.json", run_info)
    return summary


def _data_relative(path: Path, root: Path) -> str:
    """La ruta bajo `data/`, sin la carpeta del equipo en que se ejecutó."""
    return f"data/{path.resolve().relative_to(root.resolve()).as_posix()}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Corpus de correcciones con una muestra de Camera-PrIMuS (#421)"
    )
    parser.add_argument("--data", type=Path, default=DATA_DIR)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="Elige la muestra")
    prepare.add_argument("--size", type=int, default=SAMPLE_SIZE)
    prepare.add_argument("--force", action="store_true", help="Sustituir o ampliar la muestra")
    transcribe_parser = sub.add_parser("transcribe", help="Transcribe la muestra con HOMR")
    transcribe_parser.add_argument("--cpu", action="store_true", help="En la CPU, no en la GPU")
    transcribe_parser.add_argument("--force", action="store_true")
    transcribe_parser.add_argument("--retry-failures", action="store_true")
    transcribe_parser.add_argument("--limit", type=int, default=None)
    build_parser = sub.add_parser("build", help="Deriva, verifica y analiza")
    build_parser.add_argument("--test-fraction", type=float, default=DEFAULT_TEST_FRACTION)
    build_parser.add_argument("--no-omr-ned", action="store_true")
    build_parser.add_argument("--limit", type=int, default=None)
    build_parser.add_argument(
        "--results-dir", type=Path, default=None, help="Por defecto, results/ del repositorio"
    )
    build_parser.add_argument(
        "--exp-12-split",
        type=Path,
        default=None,
        help="La partición de exp_12 (por defecto, correction_corpus_split.json de --results-dir)",
    )
    args = parser.parse_args()

    _disable_power_throttling()
    manifest_path = _manifest_path(args.data)
    if args.command == "prepare":
        # La semilla es siempre la de exp_12: con otra, build rechazaría la partición.
        manifest = select_sample(args.data, size=args.size, force=args.force)
        print(f"[{EXPERIMENT}] muestra de {manifest['count']} incipits -> {manifest_path}")
    elif args.command == "transcribe":
        result = transcribe(
            manifest_path,
            use_gpu=not args.cpu,
            force=args.force,
            retry_failures=args.retry_failures,
            limit=args.limit,
        )
        print(f"[{EXPERIMENT}] transcripción: {result}")
    else:
        summary = build(
            manifest_path,
            test_fraction=args.test_fraction,
            with_omr_ned=not args.no_omr_ned,
            limit=args.limit,
            results_dir=args.results_dir,
            exp_12_split=args.exp_12_split,
        )
        verification = summary["verification"]
        print(
            f"[{EXPERIMENT}] verificados {verification['verified_count']}/"
            f"{verification['derived_count']}; correcciones verificadas: "
            f"{summary['edit_distribution']['verified']['counts']}"
        )


if __name__ == "__main__":
    main()
