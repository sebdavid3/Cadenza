"""Experimento 16: cuánto falla HOMR con música manuscrita (MUSCIMA++ v2.0, #102).

HOMR está hecho para música impresa. MUSCIMA++ v2.0 anota con MuNG 140 páginas manuscritas de
CVC-MUSCIMA: 20 páginas de música copiadas cada una por 7 de sus 50 copistas. Este experimento
pasa HOMR por las 140 y mide, con lo que dan las anotaciones:

- en todas: la tasa de fallos del motor y cuántas notas lee frente a las cabezas anotadas;
- en las que se pueden convertir a `ScoreIR` (un pentagrama por sistema y una voz,
  `cadenza.learning.muscima`): el OMR-NED, la SER, las correcciones del corrector ideal por
  operación y el corpus de correcciones (`source = muscima`), con el mismo formato que el de
  `exp_12`, para que `ml export-tables --corpus` lo lea.

La verdad convertida se valida con lo que no depende de HOMR: cuántos compases con compás
conocido suman lo que deben y cuánto se parecen las versiones de una misma página de copistas
distintos (SER entre pares). Las imágenes de CVC-MUSCIMA son blanco sobre negro: se invierten
a negro sobre blanco, que es lo que espera HOMR; no hay más preprocesado.

Fases (subcomandos):
1. `prepare`: invierte las imágenes y escribe `data/muscima/exp_16/manifest.json` con los
   sha256 de la imagen original, la invertida y la anotación.
2. `transcribe`: HOMR en la GPU por defecto, como en producción (ADR-0066), sin preprocesado.
3. `build`: mide y escribe las salidas.

Sin las anotaciones, las imágenes o alguna predicción, el experimento falla: no hay valores
de reserva ni modo simulado (CLAUDE.md §8).

Salidas (`results/`, sin versionar):
- `muscima_homr_images.csv`: una fila por imagen.
- `muscima_homr_summary.json`: fallos, recuentos, conversión, calidad de la verdad y métricas.
- `muscima_correction_corpus.jsonl`: los registros de las imágenes convertidas.
- `exp_16_run_info.json`
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Mapping
from itertools import combinations
from pathlib import Path
from typing import Any

from cadenza.domain import EventKind, ScoreIR
from cadenza.interchange import read_score, score_ir_to_musicxml
from cadenza.learning import (
    DEFAULT_TEST_FRACTION,
    MungConversionError,
    assign_split,
    mung_counts,
    mung_texture,
    mung_to_score,
    read_mung,
    score_ser_pair,
)
from cadenza.learning.muscima import measure_length, usual_length

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
    clear_predictions,
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

LABEL = "exp_16"
SOURCE = "muscima"
CORPUS_DIR = "muscima"
ANNOTATIONS = Path("muscima") / "muscima-pp" / "v2.0" / "data" / "annotations"
IMAGES = Path("muscima") / "images" / "fulls"
_NAME = re.compile(r"^CVC-MUSCIMA_W-(?P<writer>\d+)_N-(?P<page>\d+)_D-ideal$")

CSV_FIELDS = [
    "id",
    "page",
    "writer",
    "texture",
    "split",
    "status",
    "error",
    "noteheads",
    "grace_noteheads",
    "rests",
    "staves",
    "notes_read",
    "rests_read",
    "parts_read",
    "staves_read",
    "measures_read",
    "truth",
    "truth_reason",
    "gt_measures",
    "gt_notes",
    "measures_with_capacity",
    "measures_filled",
    "measures_with_usual_length",
    "measures_filled_usual",
    "verified",
    *OPS,
    "Total",
    "ser",
    "omr_ned",
    "omr_ned_error",
]

LIMITATIONS: dict[str, str] = {
    **METHODOLOGICAL_LIMITATIONS,
    "handwritten_vs_printed": (
        "HOMR está entrenado con música impresa o renderizada; aquí se mide cuánto falla con "
        "música manuscrita, no se ajusta nada para ella."
    ),
    "twenty_pieces": (
        "Las 140 imágenes son 20 páginas de música copiadas por 7 copistas cada una: la "
        "variedad musical es la de 20 páginas, no la de 140. La partición agrupa por página."
    ),
    "truth_is_inferred": (
        "MUSCIMA++ no trae la partitura sino un grafo de símbolos; la altura y la duración se "
        "infieren de él (cadenza.learning.muscima, con la regla de la inferencia de "
        "referencia de `mung`). Su calidad se mide aparte: compases que suman lo que deben y "
        "parecido entre copistas de una misma página."
    ),
    "convertible_subset": (
        "Solo se convierten las páginas de un pentagrama por sistema y una voz, sin compases "
        "abreviados. Las demás se miden solo con los recuentos y la tasa de fallos."
    ),
    "grace_notes": (
        "Las notas de adorno no entran en la verdad (el dominio no las tiene) y se cuentan "
        "aparte; las notas que lea HOMR sí cuentan."
    ),
    "inverted_images": (
        "Las imágenes de CVC-MUSCIMA son blanco sobre negro y se invierten antes de HOMR; no "
        "se aplica ningún otro preprocesado."
    ),
    "ideal_corrector": (
        "Las correcciones son las del corrector ideal: la alineación de coste mínimo entre lo "
        "que leyó HOMR y la verdad, no las que haría una persona."
    ),
    "measure_alignment": (
        "La derivación empareja los compases por su posición y no corrige cuántos hay: si HOMR "
        "lee otro número de compases, las correcciones de los compases desplazados son de "
        "alineación, no de lectura, y las de los compases que sobran o faltan no se cuentan. "
        "Por eso la distribución de correcciones solo se da para las imágenes con el mismo "
        "número de compases; la SER y el OMR-NED no dependen de alinear compases."
    ),
}


def work_of(page: str) -> str:
    """La obra de una imagen: su página de música, la misma para los 7 copistas."""
    return f"muscima-N-{page}"


# --- 1. Preparación ----------------------------------------------------------------------


def prepare(data_dir: Path = DATA_DIR, *, force: bool = False) -> dict[str, Any]:
    """Invierte las imágenes anotadas y escribe el manifiesto con los sha256."""
    import cv2

    target = data_dir / CORPUS_DIR / LABEL / "manifest.json"
    if target.is_file() and not force:
        raise FileExistsError(
            f"Ya hay un manifiesto en {target}; sus predicciones son de él. Repite con --force "
            "(borra las predicciones)."
        )
    annotations = data_dir / ANNOTATIONS
    images = data_dir / IMAGES
    if not annotations.is_dir() or not images.is_dir():
        raise FileNotFoundError(
            f"exp_16 necesita las anotaciones de MUSCIMA++ v2.0 ({annotations}) y las imágenes "
            f"de CVC-MUSCIMA ({images}); ver docs/investigaciones/INV-0003."
        )
    annotated = {path.stem: path for path in sorted(annotations.glob("CVC-MUSCIMA_*.xml"))}
    pictured = {path.stem: path for path in sorted(images.glob("CVC-MUSCIMA_*.png"))}
    if not annotated:
        raise FileNotFoundError(f"No hay anotaciones MuNG en {annotations}")
    if set(annotated) != set(pictured):
        missing = sorted(set(annotated) ^ set(pictured))
        raise ValueError(
            f"Las anotaciones y las imágenes no coinciden ({len(missing)} sin pareja, p. ej. "
            f"{missing[:3]})"
        )
    if clear_predictions(target):
        print(f"[{LABEL}] borradas las predicciones de la muestra anterior", flush=True)
    out_dir = target.parent / "images"
    out_dir.mkdir(parents=True, exist_ok=True)

    def relative(path: Path) -> str:
        return path.relative_to(data_dir).as_posix()

    entries = []
    for name, annotation in annotated.items():
        match = _NAME.match(name)
        if match is None:
            raise ValueError(f"Nombre de imagen inesperado: {name}")
        source = pictured[name]
        image = cv2.imread(str(source), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError(f"No se puede leer la imagen {source}")
        inverted = bool(image.mean() < 128)
        prepared = out_dir / f"{name}.png"
        if not cv2.imwrite(str(prepared), 255 - image if inverted else image):
            raise OSError(f"No se pudo escribir {prepared}")
        entries.append(
            {
                "id": name,
                "page": match["page"],
                "writer": match["writer"],
                "image": relative(prepared),
                "image_sha256": sha256_of_file(prepared),
                "inverted": inverted,
                "source_image": relative(source),
                "source_image_sha256": sha256_of_file(source),
                "annotation": relative(annotation),
                "annotation_sha256": sha256_of_file(annotation),
            }
        )
    manifest: dict[str, Any] = {
        "corpus": "muscima++ v2.0",
        "experiment": LABEL,
        "seed": DEFAULT_SEED,
        "selection": "todas las imágenes anotadas de MUSCIMA++ v2.0",
        "count": len(entries),
        "entries": entries,
    }
    write_json(target, manifest)
    return manifest


# --- 3. Medición -------------------------------------------------------------------------


def _score_counts(score: ScoreIR) -> dict[str, int]:
    events = [
        event
        for part in score.parts
        for staff in part.staves
        for measure in staff.measures
        for event in measure.events
    ]
    return {
        "notes_read": sum(1 for e in events if e.kind is EventKind.NOTE),
        "rests_read": sum(1 for e in events if e.kind is EventKind.REST),
        "parts_read": len(score.parts),
        "staves_read": sum(len(part.staves) for part in score.parts),
        "measures_read": max(
            (len(staff.measures) for part in score.parts for staff in part.staves), default=0
        ),
    }


def _measure_fill(score: ScoreIR) -> dict[str, int]:
    """Cuántos compases suman lo que deben: con compás anotado, lo que pide; sin él, lo que
    suman más a menudo los compases de la página (una comprobación más débil, aparte)."""
    measures = score.parts[0].staves[0].measures
    usual = usual_length(measures)
    time_signature = None
    counts = dict.fromkeys(
        (
            "measures_with_capacity",
            "measures_filled",
            "measures_with_usual_length",
            "measures_filled_usual",
        ),
        0,
    )
    for measure in measures:
        time_signature = measure.time_signature or time_signature
        if time_signature is not None:
            counts["measures_with_capacity"] += 1
            counts["measures_filled"] += int(
                measure_length(measure) == time_signature.quarter_length
            )
        elif usual is not None:
            counts["measures_with_usual_length"] += 1
            counts["measures_filled_usual"] += int(measure_length(measure) == usual)
    return counts


def _reason(error: str) -> str:
    """El motivo de no convertir, sin los identificadores de los nodos."""
    if "varios pentagramas" in error:
        return "multi_staff"
    if "polifonía" in error:
        return "polyphony"
    if "abrevia compases" in error:
        return "measure_shorthand"
    if "clave de do" in error:
        return "ambiguous_c_clef"
    return "other"


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
    truth_dir = manifest_path.parent / "ground_truth"
    truth_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    corpus: list[dict[str, Any]] = []
    truths: dict[str, dict[str, ScoreIR]] = defaultdict(dict)
    unreadable: dict[str, str] = {}
    derive_errors: dict[str, str] = {}
    started = time.monotonic()

    for position, entry in enumerate(entries, start=1):
        item, page = entry["id"], entry["page"]
        nodes = read_mung(root / entry["annotation"])
        texture = mung_texture(nodes)
        work = work_of(page)
        split = assign_split(work, seed=seed, test_fraction=test_fraction)
        row: dict[str, Any] = dict.fromkeys(CSV_FIELDS, "")
        row.update(
            {
                "id": item,
                "page": page,
                "writer": entry["writer"],
                "texture": texture,
                "split": split,
                **{
                    k: v
                    for k, v in mung_counts(nodes).items()
                    if k in ("noteheads", "grace_noteheads", "rests", "staves")
                },
            }
        )
        truth: ScoreIR | None = None
        try:
            truth = mung_to_score(nodes, score_id=item)
        except MungConversionError as exc:
            row.update({"truth": "not_convertible", "truth_reason": _reason(str(exc))})
        else:
            truths[page][item] = truth
            row.update(
                {
                    "truth": "converted",
                    "gt_measures": len(truth.parts[0].staves[0].measures),
                    "gt_notes": _score_counts(truth)["notes_read"],
                    **_measure_fill(truth),
                }
            )

        if item in failures:
            row.update({"status": "failure", "error": failures[item]})
            rows.append(row)
            continue
        pred_file = predictions / f"{item}.musicxml"
        try:
            predicted = read_score(pred_file)
        except ValueError as exc:
            unreadable[item] = f"{type(exc).__name__}: {exc}"
            row.update({"status": "prediction_unreadable", "error": unreadable[item]})
            rows.append(row)
            continue
        row.update({"status": "read", **_score_counts(predicted)})

        if truth is not None:
            truth_file: Path | None = None
            if with_omr_ned:
                # El OMR-NED compara archivos: la verdad convertida se escribe en MusicXML.
                truth_file = truth_dir / f"{item}.musicxml"
                truth_file.write_text(score_ir_to_musicxml(truth, stable=True), encoding="utf-8")
            try:
                measured = measure_pair(
                    predicted,
                    truth,
                    item=item,
                    split=split,
                    source=SOURCE,
                    work=work,
                    pred_file=pred_file,
                    truth_file=truth_file,
                )
            except (ValueError, IndexError) as exc:
                derive_errors[item] = f"{type(exc).__name__}: {exc}"
                row.update({"status": "derive_error", "error": derive_errors[item]})
                rows.append(row)
                continue
            corpus.extend(measured.records)
            row.update(measured.row())
        rows.append(row)
        if position % 20 == 0:
            print(
                f"[{LABEL}] {position}/{len(entries)} imágenes "
                f"({time.monotonic() - started:.0f} s)",
                flush=True,
            )

    summary = _summary(
        manifest,
        rows,
        corpus,
        truths,
        homr_info=homr_info,
        unreadable=unreadable,
        derive_errors=derive_errors,
        seed=seed,
        test_fraction=test_fraction,
    )

    results = RESULTS_DIR
    results.mkdir(parents=True, exist_ok=True)
    corpus_path = results / "muscima_correction_corpus.jsonl"
    write_jsonl(corpus_path, corpus)
    with (results / "muscima_homr_images.csv").open("w", encoding="utf-8", newline="") as handle:
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
    write_json(results / "muscima_homr_summary.json", summary)
    write_json(results / "exp_16_run_info.json", run_info)
    return summary


def _writer_agreement(truths: Mapping[str, Mapping[str, ScoreIR]]) -> dict[str, Any]:
    """SER entre las verdades convertidas de dos copistas de la misma página."""
    by_page: dict[str, Any] = {}
    values: list[float] = []
    for page, scores in sorted(truths.items()):
        pairs = [
            score_ser_pair(a, b).ser for (_, a), (_, b) in combinations(sorted(scores.items()), 2)
        ]
        values.extend(pairs)
        by_page[page] = {"versions": len(scores), "pairs": len(pairs), **(stats(pairs) or {})}
    return {
        "definition": (
            "SER entre las verdades convertidas de dos copistas de una misma página (cada par "
            "una vez). Mide a la vez las diferencias de copia, los errores de anotación y los "
            "de la conversión: 0 es que las dos versiones coinciden símbolo a símbolo."
        ),
        "pairs": stats(values),
        "by_page": by_page,
    }


def _summary(
    manifest: Mapping[str, Any],
    rows: list[dict[str, Any]],
    corpus: list[dict[str, Any]],
    truths: Mapping[str, Mapping[str, ScoreIR]],
    *,
    homr_info: Mapping[str, Any],
    unreadable: Mapping[str, str],
    derive_errors: Mapping[str, str],
    seed: int,
    test_fraction: float,
) -> dict[str, Any]:
    total = len(rows)
    failures = [r for r in rows if r["status"] == "failure"]
    read = [r for r in rows if r["status"] in ("read", "derived")]
    converted = [r for r in rows if r["truth"] == "converted"]
    derived = [r for r in rows if r["status"] == "derived"]
    verified = [r for r in derived if r["verified"]]
    aligned = [r for r in derived if r["measures_read"] == r["gt_measures"]]
    unusable = [r for r in converted if r["status"] in ("failure", "prediction_unreadable")]

    def ops(scope: list[dict[str, Any]]) -> Counter[str]:
        return Counter({op: sum(int(r[op]) for r in scope) for op in OPS})

    def per_note(scope: list[dict[str, Any]]) -> dict[str, Any]:
        return rate(sum(ops(scope).values()), sum(int(r["gt_notes"]) for r in scope))

    by_texture: dict[str, Any] = {}
    for texture in sorted({r["texture"] for r in rows}):
        group = [r for r in rows if r["texture"] == texture]
        group_read = [r for r in group if r["status"] in ("read", "derived")]
        heads = sum(int(r["noteheads"]) for r in group_read)
        notes = sum(int(r["notes_read"]) for r in group_read)
        by_texture[texture] = {
            "images": len(group),
            "failures": rate(sum(1 for r in group if r["status"] == "failure"), len(group)),
            "noteheads_annotated": heads,
            "notes_read": notes,
            "notes_read_per_notehead": round(notes / heads, 4) if heads else None,
        }

    def values(key: str, scope: list[dict[str, Any]]) -> list[float]:
        return [float(r[key]) for r in scope if r[key] != ""]

    def total_of(key: str) -> int:
        return sum(int(r[key]) for r in converted)

    converted_pages = sorted({r["page"] for r in converted})
    return {
        "experiment": "exp_16_muscima_homr",
        "issue": 102,
        "corpus": "MUSCIMA++ v2.0 (anotaciones MuNG) sobre imágenes de CVC-MUSCIMA",
        "seed": seed,
        "sample": {
            "images": total,
            "pages": len({r["page"] for r in rows}),
            "writers": len({r["writer"] for r in rows}),
            "selection": manifest.get("selection"),
            "inverted_images": sum(1 for e in manifest["entries"] if e.get("inverted")),
        },
        "transcription": {
            **homr_info,
            "failures": rate(len(failures), total),
            "failures_by_error": dict(Counter(r["error"] for r in failures)),
            "prediction_unreadable_count": len(unreadable),
            # Lo que Cadenza no puede usar: un fallo del motor o un MusicXML que no lee.
            "unusable": rate(len(failures) + len(unreadable), total),
            "prediction_unreadable": dict(sorted(unreadable.items())),
        },
        "counts": {
            "scope": "imágenes leídas por HOMR, por textura de la página anotada",
            "definition": (
                "Notas que lee HOMR (cada nota de un acorde cuenta) frente a cabezas anotadas "
                "sin las de adorno. Es un recuento, no un acierto: dice cuánto lee, no si lo "
                "lee bien."
            ),
            "by_texture": by_texture,
            "images_read": len(read),
        },
        "conversion": {
            "converted": rate(len(converted), total),
            "not_convertible_by_reason": dict(
                Counter(r["truth_reason"] for r in rows if r["truth"] == "not_convertible")
            ),
            "converted_pages": converted_pages,
            "converted_by_page": dict(Counter(r["page"] for r in converted)),
        },
        "truth_quality": {
            "measures_with_known_time_signature": total_of("measures_with_capacity"),
            "measures_filled_exactly": rate(
                total_of("measures_filled"), total_of("measures_with_capacity")
            ),
            "without_time_signature": {
                "definition": (
                    "Compases sin compás anotado frente a lo que suman más a menudo los de su "
                    "página: una comprobación más débil, que no ve un error repetido."
                ),
                "measures_filled_usual": rate(
                    total_of("measures_filled_usual"), total_of("measures_with_usual_length")
                ),
            },
            "writer_agreement": _writer_agreement(truths),
        },
        "converted_subset": {
            "scope": "imágenes con verdad convertida",
            "images": len(converted),
            "failures": rate(sum(1 for r in converted if r["status"] == "failure"), len(converted)),
            "derived": len(derived),
            "verification": rate(len(verified), len(derived)),
            "measure_count_match": rate(
                sum(1 for r in derived if r["measures_read"] == r["gt_measures"]), len(derived)
            ),
            "ser": stats(values("ser", derived)),
            "omr_ned": stats(values("omr_ned", derived)),
            # Como exp_03: cada imagen que no se puede usar cuenta con la distancia máxima.
            "ser_penalized": stats(values("ser", derived) + [1.0] * len(unusable)),
            "omr_ned_penalized": (
                stats(values("omr_ned", derived) + [1.0] * len(unusable))
                if values("omr_ned", derived)
                else None
            ),
            "unusable": rate(len(unusable), len(converted)),
            "edit_distribution": {
                "scope": (
                    "Solo las imágenes en que HOMR lee tantos compases como la verdad: en las "
                    "demás la derivación empareja compases desplazados (ver measure_alignment)."
                ),
                "same_measure_count": distribution(ops(aligned)),
                "edits_per_truth_note_same_measure_count": per_note(aligned),
                "verified": distribution(ops(verified)),
                "all_derived_misaligned": {
                    "note": (
                        "Todas las imágenes derivadas, compases desplazados incluidos: no "
                        "describe errores de lectura y no se cita como tal."
                    ),
                    **distribution(ops(derived)),
                },
            },
            "omr_ned_errors": {
                r["id"]: r["omr_ned_error"] for r in derived if r.get("omr_ned_error")
            },
            "derive_errors": dict(sorted(derive_errors.items())),
        },
        "correction_corpus": {
            "records": len(corpus),
            "by_kind": dict(Counter(r["record"] for r in corpus)),
            "by_split": dict(Counter(r["split"] for r in corpus)),
            "records_of_verified_images": sum(1 for r in corpus if r["verified"]),
            "source": SOURCE,
            "split_rule": (
                "assign_split(f'muscima-N-{página}', seed, test_fraction): las 7 versiones de "
                "una página caen del mismo lado"
            ),
            "test_fraction": test_fraction,
        },
        "sample_size_justification": sample_size_justification(
            "muscima",
            counts={
                "images": total,
                "images_read": len(read),
                "converted_images": len(converted),
                "derived_images": len(derived),
            },
            proportions={
                "failure_rate": (len(failures), total),
                "verification_rate": (len(verified), len(derived)),
            },
            worst_case={"corrections_same_measure_count": sum(ops(aligned).values())},
        ),
        "methodological_limitations": LIMITATIONS,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HOMR sobre música manuscrita: MUSCIMA++ v2.0 (#102)"
    )
    parser.add_argument("--data", type=Path, default=DATA_DIR)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare", help="Invierte las imágenes y escribe la muestra")
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
        manifest = prepare(args.data, force=args.force)
        print(f"[{LABEL}] {manifest['count']} imágenes -> {manifest_path}")
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
        subset = summary["converted_subset"]
        print(
            f"[{LABEL}] fallos {summary['transcription']['failures']}; convertidas "
            f"{summary['conversion']['converted']}; SER {subset['ser']}; OMR-NED "
            f"{subset['omr_ned']}"
        )


if __name__ == "__main__":
    main()
