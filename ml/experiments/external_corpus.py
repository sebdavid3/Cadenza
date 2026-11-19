"""Piezas comunes de los experimentos de HOMR con corpus externos (#102).

La transcripción reanudable es la fase `transcribe` de `exp_12`, sin cambiarla (`exp_12` no
se toca: sus resultados son los del corpus de #255), para los experimentos que leen otros
corpus: `exp_16` (MUSCIMA++) y `exp_17` (SMB). El manifiesto vive en
`<data>/<corpus>/<experimento>/manifest.json` y sus rutas son relativas a `<data>`; las
predicciones van a `predictions/`, junto al manifiesto, con los fallos del motor en
`failures.json` y el motor y el dispositivo en `run_info.json`.

Un fallo del motor (`OMRTranscriptionError`) es un resultado del experimento y se registra;
cualquier otro error detiene la ejecución. Se reanuda sin repetir lo ya transcrito y se niega
a mezclar predicciones de otro motor o dispositivo.

`measure_pair` deriva las correcciones de una predicción frente a su verdad, como `exp_12`, y
calcula la SER y, si se pide, el OMR-NED. No escribe en `results/`: cada experimento escribe
sus salidas en su propio `RESULTS_DIR`.
"""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Protocol

from cadenza.domain import ScoreIR, materialize
from cadenza.learning import (
    build_correction_records,
    count_edits_by_op,
    derive_edit_events,
    is_structurally_equal,
    omr_ned_pair,
    score_ser_pair,
)
from cadenza.omr import OMRTranscriptionError

OPS = (
    "SetPitch",
    "SetDuration",
    "SetAccidental",
    "InsertEvent",
    "DeleteEvent",
    "SetClef",
    "SetKey",
)


class Transcriber(Protocol):
    @property
    def engine_id(self) -> str: ...

    @property
    def device(self) -> str: ...

    def transcribe_musicxml(self, image_path: Path) -> str: ...


def data_root(manifest_path: Path) -> Path:
    """`<data>`: el manifiesto está en `<data>/<corpus>/<experimento>/manifest.json`."""
    return manifest_path.parents[2]


def engine_version() -> str:
    try:
        return version("homr")
    except PackageNotFoundError:
        return "unknown"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_manifest(manifest_path: Path, *, label: str) -> dict[str, Any]:
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"{label} necesita su muestra ({manifest_path}): créala con el subcomando "
            "`prepare` y transcríbela con `transcribe`."
        )
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("entries"):
        raise ValueError(f"La muestra {manifest_path} no tiene entradas")
    return manifest


def read_failures(predictions: Path) -> dict[str, str]:
    failures_file = predictions / "failures.json"
    if not failures_file.is_file():
        return {}
    return {
        item["id"]: item["error"] for item in json.loads(failures_file.read_text(encoding="utf-8"))
    }


def transcribe(
    manifest_path: Path,
    *,
    label: str,
    use_gpu: bool = False,
    force: bool = False,
    retry_failures: bool = False,
    limit: int | None = None,
    engine: Transcriber | None = None,
) -> dict[str, int]:
    """Transcribe la muestra con HOMR, sin preprocesado, y registra los fallos del motor."""
    manifest = load_manifest(manifest_path, label=label)
    entries = manifest["entries"][:limit]
    root = data_root(manifest_path)
    out_dir = manifest_path.parent / "predictions"
    out_dir.mkdir(parents=True, exist_ok=True)
    failures_file = out_dir / "failures.json"
    info_file = out_dir / "run_info.json"

    if engine is None:
        from cadenza.omr import HOMREngine

        engine = HOMREngine(use_gpu=use_gpu)
    config = {
        "engine": engine.engine_id,
        "engine_version": engine_version(),
        "device": engine.device,
        "preprocessing": None,
    }
    if info_file.is_file() and not force:
        previous = json.loads(info_file.read_text(encoding="utf-8"))
        if previous != config:
            raise ValueError(
                f"Las predicciones de {out_dir} se generaron con otro motor o dispositivo "
                f"({previous}, ahora {config}); repite la transcripción con --force."
            )
    write_json(info_file, config)

    failures = {} if force else read_failures(out_dir)
    retry = set(failures) if retry_failures else set()

    written = reused = 0
    started = time.monotonic()
    for position, entry in enumerate(entries, start=1):
        item = entry["id"]
        target = out_dir / f"{item}.musicxml"
        if not force and item not in retry and (target.is_file() or item in failures):
            reused += 1
            continue
        try:
            xml_text = engine.transcribe_musicxml(root / entry["image"])
        except OMRTranscriptionError as exc:
            cause = f" [{type(exc.__cause__).__name__}]" if exc.__cause__ is not None else ""
            failures[item] = f"{type(exc).__name__}{cause}: {exc}"
            target.unlink(missing_ok=True)
        else:
            failures.pop(item, None)
            # Se escribe aparte y se renombra: una interrupción no deja una predicción a medias
            # que la reanudación daría por hecha.
            partial = target.with_suffix(".musicxml.tmp")
            partial.write_text(xml_text, encoding="utf-8")
            partial.replace(target)
            written += 1
        write_json(
            failures_file,
            [{"id": key, "error": value} for key, value in sorted(failures.items())],
        )
        if position % 25 == 0:
            elapsed = time.monotonic() - started
            print(
                f"[{label}] {position}/{len(entries)} ({written} nuevas, {len(failures)} "
                f"fallos, {elapsed / max(written, 1):.2f} s por imagen)",
                flush=True,
            )
    if not failures_file.is_file():
        write_json(failures_file, [])
    in_scope = sum(1 for entry in entries if entry["id"] in failures)
    return {"written": written, "reused": reused, "failures": in_scope}


def check_complete(
    manifest_path: Path, entries: list[dict[str, Any]], *, label: str
) -> tuple[Path, dict[str, str], dict[str, Any]]:
    """Las predicciones, los fallos y el motor de una muestra transcrita por completo."""
    predictions = manifest_path.parent / "predictions"
    failures = read_failures(predictions)
    untraced = [
        e["id"]
        for e in entries
        if e["id"] not in failures and not (predictions / f"{e['id']}.musicxml").is_file()
    ]
    if len(untraced) == len(entries):
        raise ValueError(
            f"{label} no encontró ninguna predicción en {predictions} para las {len(entries)} "
            "entradas de la muestra: ejecuta antes `transcribe`."
        )
    if untraced:
        raise ValueError(
            f"{label}: {len(untraced)} de {len(entries)} entradas sin predicción ni fallo "
            f"registrado en {predictions} (p. ej. {untraced[:3]}): termina `transcribe`."
        )
    info_file = predictions / "run_info.json"
    if not info_file.is_file():
        raise ValueError(f"Faltan el motor y el dispositivo de las predicciones ({info_file})")
    return predictions, failures, json.loads(info_file.read_text(encoding="utf-8"))


# --- Medición -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PairMeasure:
    """Lo que se mide de una predicción frente a su verdad."""

    verified: bool
    counts: dict[str, int]
    records: list[dict[str, Any]]
    ser: float
    omr_ned: float | None

    def row(self) -> dict[str, Any]:
        return {
            "status": "derived",
            "verified": self.verified,
            **{op: self.counts[op] for op in OPS},
            "Total": self.counts["Total"],
            "ser": round(self.ser, 4),
            "omr_ned": "" if self.omr_ned is None else round(self.omr_ned, 4),
        }


def measure_pair(
    predicted: ScoreIR,
    truth: ScoreIR,
    *,
    item: str,
    split: str,
    source: str,
    work: str,
    pred_file: Path,
    truth_file: Path | None,
) -> PairMeasure:
    """Correcciones del corrector ideal, verificación, registros del corpus, SER y OMR-NED.

    Los registros llevan `source` y `work_id`, que leen `ml export-tables` y la capa de
    sugerencias. Sin `truth_file` no se calcula el OMR-NED. Un `ValueError` o un `IndexError`
    al derivar sube: el experimento lo registra como error de derivación.
    """
    edits = derive_edit_events(predicted, truth, document_id=item)
    verified = is_structurally_equal(materialize(predicted, edits), truth)
    records = build_correction_records(
        predicted, truth, incipit_id=item, split=split, verified=verified
    )
    for record in records:
        record["source"] = source
        record["work_id"] = work
    counts = count_edits_by_op(edits).to_dict()
    ned = None if truth_file is None else omr_ned_pair(pred_file, truth_file).omr_ned
    return PairMeasure(
        verified=verified,
        counts={**{op: counts[op] for op in OPS}, "Total": counts["Total"]},
        records=records,
        ser=score_ser_pair(truth, predicted).ser,
        omr_ned=ned,
    )


def stats(values: list[float]) -> dict[str, Any] | None:
    if not values:
        return None
    return {
        "count": len(values),
        "mean": round(statistics.fmean(values), 4),
        "median": round(statistics.median(values), 4),
    }


def rate(cases: int, n: int) -> dict[str, Any]:
    return {"cases": cases, "n": n, "rate": round(cases / n, 4) if n else None}


def distribution(counts: Mapping[str, int]) -> dict[str, Any]:
    total = sum(counts.get(op, 0) for op in OPS)
    return {
        "counts": {**{op: counts.get(op, 0) for op in OPS}, "Total": total},
        "proportions": {op: round(counts.get(op, 0) / total, 4) if total else None for op in OPS},
    }


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
