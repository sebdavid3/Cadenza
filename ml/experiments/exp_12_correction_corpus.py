"""Experimento 12: corpus de correcciones a escala y errores de HOMR (#255).

Construye el corpus con que aprende la capa de sugerencias (#256): HOMR transcribe unos
2 000 incipits de PrIMuS elegidos al azar con semilla, sin solaparse con los 100 de
`exp_03`, y de cada transcripción se derivan las correcciones del «corrector ideal»
(`derive_edit_events`), verificadas con `materialize(predicho, ediciones) == verdad`.

La verdad es la altura que suena. El MEI de PrIMuS no codifica la alteración que impone la
armadura (una nota en la línea de Si con tres bemoles es `pname="b"` sin `accid.ges`), así
que su lectura da `B4` donde suena `Bb4`. Las alturas salen del `.semantic` del mismo
incipit (`cadenza.learning.with_sounding_pitches`), comprobando que coinciden el número de
notas, la letra y la octava; si no coinciden, el incipit se registra y no se usa. El
experimento mide además cuántas correcciones de alteración aparecían contra el MEI tal cual.

Fases (subcomandos):
1. `sample`: elige la muestra y escribe `data/primus/exp_12/manifest.json` con los sha256.
2. `transcribe`: HOMR en CPU y sin preprocesado, como en producción, con una predicción por
   incipit en `data/primus/exp_12/predictions/` y los fallos del motor en `failures.json`.
   Se reanuda sin repetir; un error que no es del motor detiene la ejecución.
3. `build`: deriva y verifica las correcciones, escribe el corpus por nota, la partición
   fija de entrenamiento y prueba y el análisis por operación y por contexto.

Sin el manifiesto de `exp_03`, sin la muestra o con alguna entrada sin predicción ni fallo
registrado, el experimento falla: no hay valores de reserva (CLAUDE.md §8).

Salidas (`results/`, sin versionar):
- `correction_corpus.jsonl`: un registro por evento leído, inserción y compás corregido.
- `correction_corpus_incipits.csv`: una fila por incipit de la muestra.
- `correction_corpus_split.json`: la partición fija por incipit.
- `correction_corpus_summary.json`: verificación, distribución y análisis.
- `exp_12_run_info.json`
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import random
import statistics
import sys
import time
from collections import Counter
from collections.abc import Iterable, Mapping
from fractions import Fraction
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Protocol

from cadenza.domain import EventKind, KeySignature, ScoreIR, TimeSignature, materialize
from cadenza.interchange import read_score
from cadenza.learning import (
    DEFAULT_TEST_FRACTION,
    SemanticMismatch,
    assign_split,
    build_correction_records,
    count_edits_by_op,
    derive_edit_events,
    is_structurally_equal,
    key_accidental,
    omr_ned_pair,
    semantic_note_pitches,
    split_pitch,
    with_sounding_pitches,
)
from cadenza.omr import OMRTranscriptionError

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

SAMPLE_SIZE = 2000
OPS = (
    "SetPitch",
    "SetDuration",
    "SetAccidental",
    "InsertEvent",
    "DeleteEvent",
    "SetClef",
    "SetKey",
)
CSV_FIELDS = [
    "id",
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
    "omr_ned",
]

LIMITATIONS: dict[str, str] = {
    **METHODOLOGICAL_LIMITATIONS,
    "ideal_corrector": (
        "Las correcciones son las del corrector ideal: la alineación de coste mínimo entre "
        "lo que leyó HOMR y la verdad, no las que haría una persona. Una persona puede "
        "corregir lo mismo con otras operaciones o en otro orden."
    ),
    "sounding_pitch_from_semantic": (
        "La altura que suena sale del `.semantic` de PrIMuS porque el MEI no codifica la "
        "alteración de la armadura. Los incipits en que el `.semantic` y el MEI no describen "
        "las mismas notas, o cuyo MEI no admite el dominio (un compás 2/3), se registran y "
        "no entran en el corpus."
    ),
    "time_signature_not_corrected": (
        "La derivación no corrige la signatura de compás (no hay operación para ello) y la "
        "verificación no la compara: un compás mal leído solo se mide aparte."
    ),
}


class Transcriber(Protocol):
    @property
    def engine_id(self) -> str: ...

    @property
    def device(self) -> str: ...

    def transcribe_musicxml(self, image_path: Path) -> str: ...


def _data_root(manifest_path: Path) -> Path:
    """La muestra vive en `<data>/primus/exp_12/` y sus rutas son relativas a `<data>`."""
    return manifest_path.parents[2]


def _engine_version() -> str:
    try:
        return version("homr")
    except PackageNotFoundError:
        return "unknown"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


# --- 1. Muestra --------------------------------------------------------------------------


def _complete_incipits(primus_dir: Path) -> dict[str, Path]:
    """Incipits con imagen, MEI y `.semantic`, por identificador."""
    found: dict[str, Path] = {}
    for package in sorted(primus_dir.glob("package_*")):
        for folder in sorted(package.iterdir()):
            if not folder.is_dir():
                continue
            names = {child.name for child in folder.iterdir()}
            if all(f"{folder.name}{suffix}" in names for suffix in (".png", ".mei", ".semantic")):
                found.setdefault(folder.name, folder)
    return found


def select_sample(
    data_dir: Path = DATA_DIR, *, size: int = SAMPLE_SIZE, seed: int = DEFAULT_SEED
) -> dict[str, Any]:
    """Elige `size` incipits completos al azar con `seed`, fuera de los de `exp_03`."""
    exp_03_manifest = data_dir / "manifest.json"
    if not exp_03_manifest.is_file():
        raise FileNotFoundError(
            f"exp_12 necesita el manifiesto de exp_03 ({exp_03_manifest}) para no solaparse "
            "con sus incipits."
        )
    excluded = {
        entry["id"] for entry in json.loads(exp_03_manifest.read_text(encoding="utf-8"))["entries"]
    }
    complete = _complete_incipits(data_dir / "primus")
    pool = sorted(incipit for incipit in complete if incipit not in excluded)
    if len(pool) < size:
        raise ValueError(
            f"exp_12 pide {size} incipits y solo hay {len(pool)} incipits completos (imagen, "
            f"MEI y .semantic) fuera de exp_03 en {data_dir / 'primus'}."
        )
    chosen = sorted(random.Random(seed).sample(pool, size))

    def relative(path: Path) -> str:
        return path.relative_to(data_dir).as_posix()

    entries = []
    for incipit in chosen:
        folder = complete[incipit]
        image = folder / f"{incipit}.png"
        mei = folder / f"{incipit}.mei"
        semantic = folder / f"{incipit}.semantic"
        entries.append(
            {
                "id": incipit,
                "image": relative(image),
                "image_sha256": sha256_of_file(image),
                "ground_truth": relative(mei),
                "ground_truth_sha256": sha256_of_file(mei),
                "semantic": relative(semantic),
                "semantic_sha256": sha256_of_file(semantic),
            }
        )
    manifest: dict[str, Any] = {
        "corpus": "primus",
        "experiment": "exp_12",
        "seed": seed,
        "selection": {
            "rule": "random.Random(seed).sample de los incipits completos fuera de exp_03",
            "candidates": len(pool),
            "candidates_sha256": _sha256_text("\n".join(pool)),
            "excluded_exp_03": len(excluded),
            "exp_03_manifest_sha256": sha256_of_file(exp_03_manifest),
        },
        "count": len(entries),
        "entries": entries,
    }
    _write_json(data_dir / "primus" / "exp_12" / "manifest.json", manifest)
    return manifest


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"exp_12 necesita su muestra ({manifest_path}): créala con `select_sample` "
            "(subcomando `sample`) y transcríbela con `transcribe`."
        )
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("entries"):
        raise ValueError(f"La muestra {manifest_path} no tiene entradas")
    return manifest


# --- 2. Transcripción --------------------------------------------------------------------


def transcribe(
    manifest_path: Path,
    *,
    use_gpu: bool = False,
    force: bool = False,
    retry_failures: bool = False,
    limit: int | None = None,
    engine: Transcriber | None = None,
) -> dict[str, int]:
    """Transcribe la muestra con HOMR y registra los fallos del motor.

    Reutiliza lo ya transcrito salvo con `force`; con `retry_failures` repite solo los
    fallos registrados. Se niega a mezclar predicciones de otro motor o dispositivo.
    """
    manifest = _load_manifest(manifest_path)
    entries = manifest["entries"][:limit]
    root = _data_root(manifest_path)
    out_dir = manifest_path.parent / "predictions"
    out_dir.mkdir(parents=True, exist_ok=True)
    failures_file = out_dir / "failures.json"
    info_file = out_dir / "run_info.json"

    if engine is None:
        from cadenza.omr import HOMREngine

        # Sin preprocesado y en CPU por defecto: es la configuración de producción.
        engine = HOMREngine(use_gpu=use_gpu)
    config = {
        "engine": engine.engine_id,
        "engine_version": _engine_version(),
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
    _write_json(info_file, config)

    failures: dict[str, str] = {}
    if failures_file.is_file() and not force:
        failures = {
            item["id"]: item["error"]
            for item in json.loads(failures_file.read_text(encoding="utf-8"))
        }
    retry = set(failures) if retry_failures else set()

    written = reused = 0
    started = time.monotonic()
    for position, entry in enumerate(entries, start=1):
        incipit = entry["id"]
        target = out_dir / f"{incipit}.musicxml"
        if not force and incipit not in retry and (target.is_file() or incipit in failures):
            reused += 1
            continue
        try:
            xml_text = engine.transcribe_musicxml(root / entry["image"])
        except OMRTranscriptionError as exc:
            # Un fallo del motor es un resultado del experimento, no un error del script.
            cause = f" [{type(exc.__cause__).__name__}]" if exc.__cause__ is not None else ""
            failures[incipit] = f"{type(exc).__name__}{cause}: {exc}"
            target.unlink(missing_ok=True)
        else:
            failures.pop(incipit, None)
            target.write_text(xml_text, encoding="utf-8")
            written += 1
        _write_json(
            failures_file,
            [{"id": key, "error": value} for key, value in sorted(failures.items())],
        )
        if position % 50 == 0:
            elapsed = time.monotonic() - started
            print(
                f"[exp_12] {position}/{len(entries)} ({written} nuevas, {len(failures)} "
                f"fallos, {elapsed / max(written, 1):.2f} s por incipit)",
                flush=True,
            )
    if not failures_file.is_file():
        _write_json(failures_file, [])
    in_scope = sum(1 for entry in entries if entry["id"] in failures)
    return {"written": written, "reused": reused, "failures": in_scope}


# --- 3. Corpus y análisis ----------------------------------------------------------------


def _effective(score: ScoreIR) -> list[tuple[int, TimeSignature | None]]:
    """Armadura (en quintas) y compás vigentes de cada compás del primer pentagrama."""
    out: list[tuple[int, TimeSignature | None]] = []
    if not score.parts or not score.parts[0].staves:
        return out
    key = KeySignature(fifths=0)
    time_signature: TimeSignature | None = None
    for measure in score.parts[0].staves[0].measures:
        key = measure.key_signature or key
        time_signature = measure.time_signature or time_signature
        out.append((key.fifths, time_signature))
    return out


def _notes(score: ScoreIR) -> list[str | None]:
    return [
        event.pitch
        for part in score.parts
        for staff in part.staves
        for measure in staff.measures
        for event in measure.events
        if event.kind is EventKind.NOTE
    ]


def _measure_count(score: ScoreIR) -> int:
    return len(score.parts[0].staves[0].measures) if score.parts and score.parts[0].staves else 0


def _ops_of(records: Iterable[Mapping[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for record in records:
        for op in (record["correction"] or {}).get("ops", ()):
            counts[op] += 1
    return counts


def _distribution(counts: Mapping[str, int]) -> dict[str, Any]:
    total = sum(counts.get(op, 0) for op in OPS)
    return {
        "counts": {**{op: counts.get(op, 0) for op in OPS}, "Total": total},
        "proportions": {op: round(counts.get(op, 0) / total, 4) if total else None for op in OPS},
    }


def _rate(cases: int, n: int) -> dict[str, Any]:
    return {"cases": cases, "n": n, "rate": round(cases / n, 4) if n else None}


def _balance_group(balance: str | None) -> str:
    if balance is None:
        return "sin_compas"
    value = Fraction(balance)
    return "le_falta" if value < 0 else "le_sobra" if value > 0 else "exacto"


def _diatonic_distance(before: str | None, after: str | None) -> int | None:
    b_letter, _, b_octave = split_pitch(before)
    a_letter, _, a_octave = split_pitch(after)
    if not (b_letter and a_letter):
        return None
    order = "CDEFGAB"
    return (order.index(a_letter) + 7 * int(a_octave)) - (order.index(b_letter) + 7 * int(b_octave))


def _context_analysis(
    records: list[dict[str, Any]], key_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Dónde se concentran los errores, sobre los registros de incipits verificados."""
    events = [r for r in records if r["record"] == "event" and r["aligned"]]
    notes = [r for r in events if r["read"]["kind"] == "note"]

    def has(record: Mapping[str, Any], op: str) -> bool:
        return op in (record["correction"] or {}).get("ops", ())

    by_key_relation: dict[str, Any] = {}
    for relation in ("in_key", "against_key"):
        group = [r for r in notes if r["context"]["accidental_vs_key"] == relation]
        by_key_relation[relation] = _rate(sum(has(r, "SetAccidental") for r in group), len(group))

    by_balance: dict[str, Any] = {}
    for group_name in ("le_falta", "exacto", "le_sobra", "sin_compas"):
        group = [
            r for r in events if _balance_group(r["context"]["measure_balance_beats"]) == group_name
        ]
        insertions = sum(
            1
            for r in records
            if r["record"] == "insertion"
            and _balance_group(r["context"]["measure_balance_beats"]) == group_name
        )
        by_balance[group_name] = {
            "events": len(group),
            "SetDuration": _rate(sum(has(r, "SetDuration") for r in group), len(group)),
            "DeleteEvent": _rate(sum(has(r, "DeleteEvent") for r in group), len(group)),
            "InsertEvent_per_event": _rate(insertions, len(group)),
        }

    by_duration: dict[str, Any] = {}
    for duration in sorted({r["read"]["duration_beats"] for r in events} - {None}, key=Fraction):
        group = [r for r in events if r["read"]["duration_beats"] == duration]
        by_duration[duration] = _rate(sum(has(r, "SetDuration") for r in group), len(group))

    duration_confusions = Counter(
        f"{r['read']['duration_beats']} -> {r['correction']['duration_beats']}"
        for r in events
        if has(r, "SetDuration")
    )
    accidental_confusions = Counter(
        f"'{r['correction']['accidental']['before']}' -> '{r['correction']['accidental']['after']}'"
        for r in events
        if has(r, "SetAccidental")
    )
    pitch_distances = Counter(
        str(_diatonic_distance(r["read"]["pitch"], r["correction"]["pitch"]))
        for r in events
        if has(r, "SetPitch")
    )
    inserted = Counter(
        r["correction"]["event"]["kind"] for r in records if r["record"] == "insertion"
    )
    deleted = Counter(r["read"]["kind"] for r in events if has(r, "DeleteEvent"))

    misread = [row for row in key_rows if row["key_misread"]]
    well_read = [row for row in key_rows if not row["key_misread"]]
    accidentals_total = sum(row["set_accidental"] for row in key_rows)
    in_misread = sum(row["set_accidental"] for row in misread)
    explained = sum(row["set_accidental_explained"] for row in key_rows)
    return {
        "scope": "registros de los incipits verificados",
        "key_signature": {
            "incipits": len(key_rows),
            "incipits_with_key_misread": len(misread),
            "set_accidental_total": accidentals_total,
            "set_accidental_in_key_misread_incipits": in_misread,
            "share_of_set_accidental_in_key_misread_incipits": (
                round(in_misread / accidentals_total, 4) if accidentals_total else None
            ),
            "set_accidental_explained_by_key_misread": explained,
            "explained_definition": (
                "Corrección de alteración de una nota cuya letra altera de distinta forma la "
                "armadura leída y la verdadera en ese compás."
            ),
            "set_accidental_per_note_key_misread": _rate(
                in_misread, sum(row["notes"] for row in misread)
            ),
            "set_accidental_per_note_key_well_read": _rate(
                accidentals_total - in_misread, sum(row["notes"] for row in well_read)
            ),
        },
        "set_accidental_by_read_accidental_vs_key": by_key_relation,
        "by_measure_balance_read": by_balance,
        "set_duration_by_read_duration": by_duration,
        "set_duration_confusions": dict(duration_confusions.most_common(15)),
        "set_accidental_confusions": dict(accidental_confusions.most_common()),
        "set_pitch_diatonic_distance": dict(pitch_distances.most_common()),
        "inserted_by_kind": dict(inserted),
        "deleted_by_kind": dict(deleted),
    }


def _incipit_analysis(
    incipit: str,
    predicted: ScoreIR,
    sounding: ScoreIR,
    mei: ScoreIR,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Armadura, compás y clave leídos frente a la verdad, y el efecto del MEI sin armadura."""
    read = _effective(predicted)
    truth = _effective(sounding)
    aligned = list(zip(read, truth, strict=False))
    key_misread = any(r[0] != t[0] for r, t in aligned)
    time_misread = any(r[1] != t[1] for r, t in aligned)
    explained = 0
    for record in records:
        if record["record"] != "event" or "SetAccidental" not in (record["correction"] or {}).get(
            "ops", ()
        ):
            continue
        index = record["context"]["measure_index"]
        letter = split_pitch(record["read"]["pitch"])[0]
        true_key = truth[index][0] if index < len(truth) else record["context"]["key_fifths"]
        if key_accidental(letter, record["context"]["key_fifths"]) != key_accidental(
            letter, true_key
        ):
            explained += 1
    first_read = read[0] if read else (0, None)
    first_true = truth[0] if truth else (0, None)
    return {
        "id": incipit,
        "key_read": first_read[0],
        "key_true": first_true[0],
        "key_misread": key_misread,
        "time_read": str(first_read[1]) if first_read[1] else "",
        "time_true": str(first_true[1]) if first_true[1] else "",
        "time_misread": time_misread,
        "notes": sum(1 for r in records if r["record"] == "event" and r["read"]["kind"] == "note"),
        "set_accidental": _ops_of(records)["SetAccidental"],
        "set_accidental_explained": explained,
        "mei_pitch_not_sounding": sum(
            1 for a, b in zip(_notes(mei), _notes(sounding), strict=True) if a != b
        ),
    }


def build(
    manifest_path: Path,
    *,
    seed: int = DEFAULT_SEED,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    with_omr_ned: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    """Deriva y verifica las correcciones, escribe el corpus y analiza los errores.

    Con `limit`, solo las primeras entradas de la muestra, en el orden en que se transcriben.
    """
    manifest = _load_manifest(manifest_path)
    entries: list[dict[str, Any]] = manifest["entries"][:limit]
    root = _data_root(manifest_path)
    predictions = manifest_path.parent / "predictions"
    failures_file = predictions / "failures.json"
    failures: dict[str, str] = {}
    if failures_file.is_file():
        failures = {
            item["id"]: item["error"]
            for item in json.loads(failures_file.read_text(encoding="utf-8"))
        }

    untraced = [
        e["id"]
        for e in entries
        if e["id"] not in failures and not (predictions / f"{e['id']}.musicxml").is_file()
    ]
    transcribed = [e for e in entries if (predictions / f"{e['id']}.musicxml").is_file()]
    if not transcribed:
        raise ValueError(
            f"exp_12 no encontró ninguna predicción en {predictions} para las {len(entries)} "
            "entradas de la muestra: ejecuta antes `transcribe`."
        )
    if untraced:
        raise ValueError(
            f"exp_12: {len(untraced)} de {len(entries)} entradas sin predicción ni fallo "
            f"registrado en {predictions} (p. ej. {untraced[:3]}): termina `transcribe`."
        )
    homr_info_file = predictions / "run_info.json"
    if not homr_info_file.is_file():
        raise ValueError(f"Faltan el motor y el dispositivo de las predicciones ({homr_info_file})")
    homr_info = json.loads(homr_info_file.read_text(encoding="utf-8"))

    rows: list[dict[str, Any]] = []
    corpus: list[dict[str, Any]] = []
    key_rows: list[dict[str, Any]] = []
    mismatches: dict[str, str] = {}
    unreadable: dict[str, str] = {}
    ops_sounding: Counter[str] = Counter()
    ops_mei: Counter[str] = Counter()
    ops_verified_by_split: dict[str, Counter[str]] = {"train": Counter(), "test": Counter()}
    unverified: list[str] = []
    unverified_measure_mismatch: list[str] = []
    ned_values: list[float] = []
    started = time.monotonic()

    for position, entry in enumerate(entries, start=1):
        incipit = entry["id"]
        split = assign_split(incipit, seed=seed, test_fraction=test_fraction)
        row: dict[str, Any] = dict.fromkeys(CSV_FIELDS, "")
        row.update({"id": incipit, "split": split})
        pred_file = predictions / f"{incipit}.musicxml"
        if incipit in failures:
            row.update({"status": "failure", "error": failures[incipit]})
            rows.append(row)
            continue

        gt_file = root / entry["ground_truth"]
        predicted = read_score(pred_file)
        try:
            mei = read_score(gt_file)
        except ValueError as exc:
            # Una verdad que el dominio no admite (p. ej. un compás 2/3) no se usa y se
            # registra: no hay con qué comparar lo que leyó HOMR.
            unreadable[incipit] = f"{type(exc).__name__}: {exc}"
            row.update({"status": "gt_unreadable", "error": unreadable[incipit]})
            rows.append(row)
            continue
        try:
            sounding = with_sounding_pitches(
                mei,
                semantic_note_pitches((root / entry["semantic"]).read_text(encoding="utf-8")),
            )
        except SemanticMismatch as exc:
            mismatches[incipit] = str(exc)
            row.update({"status": "gt_mismatch", "error": str(exc)})
            rows.append(row)
            continue

        edits = derive_edit_events(predicted, sounding, document_id=incipit)
        verified = is_structurally_equal(materialize(predicted, edits), sounding)
        records = build_correction_records(
            predicted, sounding, incipit_id=incipit, split=split, verified=verified
        )
        corpus.extend(records)
        counts = count_edits_by_op(edits).to_dict()
        ops_sounding.update({op: counts[op] for op in OPS})
        mei_counts = count_edits_by_op(derive_edit_events(predicted, mei)).to_dict()
        ops_mei.update({op: mei_counts[op] for op in OPS})
        analysis = _incipit_analysis(incipit, predicted, sounding, mei, records)
        if verified:
            ops_verified_by_split[split].update({op: counts[op] for op in OPS})
            key_rows.append(analysis)
        else:
            unverified.append(incipit)
            if _measure_count(predicted) != _measure_count(sounding):
                unverified_measure_mismatch.append(incipit)

        ned: float | None = None
        if with_omr_ned:
            ned = omr_ned_pair(pred_file, gt_file).omr_ned
            ned_values.append(ned)
        row.update(
            {
                "status": "derived",
                "pred_measures": _measure_count(predicted),
                "gt_measures": _measure_count(sounding),
                "verified": verified,
                **counts,
                "key_read": analysis["key_read"],
                "key_true": analysis["key_true"],
                "key_misread": analysis["key_misread"],
                "time_read": analysis["time_read"],
                "time_true": analysis["time_true"],
                "time_misread": analysis["time_misread"],
                "clef_misread": counts["SetClef"] > 0,
                "mei_pitch_not_sounding": analysis["mei_pitch_not_sounding"],
                "omr_ned": "" if ned is None else round(ned, 4),
            }
        )
        rows.append(row)
        if position % 100 == 0:
            print(
                f"[exp_12] {position}/{len(entries)} incipits "
                f"({time.monotonic() - started:.0f} s)",
                flush=True,
            )

    derived = [row for row in rows if row["status"] == "derived"]
    verified_rows = [row for row in derived if row["verified"]]
    verified_ids = {row["id"] for row in verified_rows}
    verified_records = [r for r in corpus if r["incipit_id"] in verified_ids]
    ops_verified = ops_verified_by_split["train"] + ops_verified_by_split["test"]
    sampled = len(entries)
    failure_count = sum(1 for row in rows if row["status"] == "failure")

    split_payload = {
        "seed": seed,
        "test_fraction": test_fraction,
        "rule": (
            "test si int.from_bytes(sha256(f'{seed}:{id}')[:8], 'big') / 2**64 < "
            "test_fraction (cadenza.learning.assign_split); no depende del resto de la muestra"
        ),
        "train": sorted(row["id"] for row in rows if row["split"] == "train"),
        "test": sorted(row["id"] for row in rows if row["split"] == "test"),
    }

    summary: dict[str, Any] = {
        "experiment": "exp_12_correction_corpus",
        "issue": 255,
        "corpus": "primus",
        "seed": seed,
        "sample": {
            "size": sampled,
            "selection": manifest.get("selection"),
        },
        "transcription": {
            **homr_info,
            "transcribed": len(transcribed),
            "failures_count": failure_count,
            "failure_rate": round(failure_count / sampled, 4),
            "failures_by_error": dict(
                Counter(failures[e["id"]] for e in entries if e["id"] in failures)
            ),
        },
        "ground_truth": {
            "source": "MEI de PrIMuS con la altura que suena del .semantic",
            "semantic_mismatch_count": len(mismatches),
            "semantic_mismatch_ids": sorted(mismatches),
            "unreadable_count": len(unreadable),
            "unreadable": dict(sorted(unreadable.items())),
            "mei_without_key_accidentals": {
                "incipits_affected": sum(1 for row in derived if row["mei_pitch_not_sounding"]),
                "notes_whose_mei_pitch_is_not_the_sounding_one": sum(
                    row["mei_pitch_not_sounding"] for row in derived
                ),
                "edit_distribution_against_mei": _distribution(ops_mei)["counts"],
                "edit_distribution_against_sounding": _distribution(ops_sounding)["counts"],
                "scope": "todos los incipits derivados, verificados o no",
            },
        },
        "verification": {
            "derived_count": len(derived),
            "verified_count": len(verified_rows),
            "rate": round(len(verified_rows) / len(derived), 4) if derived else None,
            "by_split": {
                split: _rate(
                    sum(1 for row in verified_rows if row["split"] == split),
                    sum(1 for row in derived if row["split"] == split),
                )
                for split in ("train", "test")
            },
            "unverified_ids": unverified,
            "unverified_with_measure_count_mismatch": unverified_measure_mismatch,
        },
        "edit_distribution": {
            "verified": _distribution(ops_verified),
            "verified_by_split": {
                split: _distribution(counter) for split, counter in ops_verified_by_split.items()
            },
            "all_derived": _distribution(ops_sounding),
            "average_edits_per_verified_incipit": (
                round(sum(ops_verified.values()) / len(verified_rows), 2) if verified_rows else None
            ),
        },
        "context_analysis": _context_analysis(verified_records, key_rows),
        "time_signature": {
            "incipits_with_time_misread": _rate(
                sum(1 for row in derived if row["time_misread"]), len(derived)
            ),
            "scope": "todos los incipits derivados",
        },
        "omr_ned": (
            {
                "count": len(ned_values),
                "mean": round(statistics.fmean(ned_values), 4),
                "median": round(statistics.median(ned_values), 4),
            }
            if ned_values
            else None
        ),
        "correction_corpus": {
            "records": len(corpus),
            "records_of_verified_incipits": len(verified_records),
            "by_kind": dict(Counter(r["record"] for r in corpus)),
            "by_split_verified": dict(Counter(r["split"] for r in verified_records)),
            "events_with_correction_verified": sum(
                1 for r in verified_records if r["record"] == "event" and r["correction"]
            ),
            "format": (
                "JSONL, un registro por evento leído (`event`), evento que falta (`insertion`) "
                "o compás con la clave o la armadura mal leídas (`measure`): lo leído, la "
                "corrección o ninguna, y el contexto leído. Solo los de `verified` son etiquetas "
                "de confianza (cadenza.learning.correction_corpus)."
            ),
        },
        "sample_size_justification": sample_size_justification(
            "primus",
            counts={
                "sampled_incipits": sampled,
                "transcribed_incipits": len(transcribed),
                "derived_incipits": len(derived),
                "verified_incipits": len(verified_rows),
                "verified_corrections": sum(ops_verified.values()),
            },
            proportions={
                "failure_rate": (failure_count, sampled),
                "verification_rate": (len(verified_rows), len(derived)),
            },
            worst_case={"verified_corrections": sum(ops_verified.values())},
        ),
        "methodological_limitations": LIMITATIONS,
    }

    # Todo se escribe al final, con todo medido: un fallo a medias no deja salidas.
    results = RESULTS_DIR
    results.mkdir(parents=True, exist_ok=True)
    corpus_path = results / "correction_corpus.jsonl"
    with corpus_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in corpus:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    with (results / "correction_corpus_incipits.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    split_path = results / "correction_corpus_split.json"
    _write_json(split_path, split_payload)
    run_info = {
        **get_run_info("exp_12", seed=seed, manifest_path=manifest_path),
        "homr": homr_info,
        "test_fraction": test_fraction,
        "omr_ned": with_omr_ned,
        "corpus_sha256": sha256_of_file(corpus_path),
        "split_sha256": sha256_of_file(split_path),
    }
    summary["run_info"] = run_info
    _write_json(results / "correction_corpus_summary.json", summary)
    _write_json(results / "exp_12_run_info.json", run_info)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Corpus de correcciones a escala y errores de HOMR (#255)"
    )
    parser.add_argument("--data", type=Path, default=DATA_DIR)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    sub = parser.add_subparsers(dest="command", required=True)
    sample_parser = sub.add_parser("sample", help="Elige la muestra")
    sample_parser.add_argument("--size", type=int, default=SAMPLE_SIZE)
    transcribe_parser = sub.add_parser("transcribe", help="Transcribe la muestra con HOMR")
    transcribe_parser.add_argument("--gpu", action="store_true", help="Usar la GPU")
    transcribe_parser.add_argument("--force", action="store_true")
    transcribe_parser.add_argument("--retry-failures", action="store_true")
    transcribe_parser.add_argument("--limit", type=int, default=None)
    build_parser = sub.add_parser("build", help="Deriva, verifica y analiza")
    build_parser.add_argument("--test-fraction", type=float, default=DEFAULT_TEST_FRACTION)
    build_parser.add_argument("--no-omr-ned", action="store_true")
    build_parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    # converter21 avisa de cada <multiRest> del MEI; el aviso no cambia la medición.
    logging.getLogger("converter21").setLevel(logging.ERROR)
    manifest_path = args.data / "primus" / "exp_12" / "manifest.json"
    if args.command == "sample":
        manifest = select_sample(args.data, size=args.size, seed=args.seed)
        print(f"[exp_12] muestra de {manifest['count']} incipits -> {manifest_path}")
    elif args.command == "transcribe":
        result = transcribe(
            manifest_path,
            use_gpu=args.gpu,
            force=args.force,
            retry_failures=args.retry_failures,
            limit=args.limit,
        )
        print(f"[exp_12] transcripción: {result}")
    else:
        summary = build(
            manifest_path,
            seed=args.seed,
            test_fraction=args.test_fraction,
            with_omr_ned=not args.no_omr_ned,
            limit=args.limit,
        )
        verification = summary["verification"]
        print(
            f"[exp_12] verificados {verification['verified_count']}/"
            f"{verification['derived_count']}; correcciones verificadas: "
            f"{summary['edit_distribution']['verified']['counts']}"
        )


if __name__ == "__main__":
    main()
