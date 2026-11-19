"""`ml export-tables`: los datos para reconocer los errores de HOMR, en CSV planos.

Escribe en `--output-dir` un CSV por tabla (`partituras`, `notas`, `faltantes`, `barras`,
`clave_armadura`, `compases`, `sugerencias`, `avisos`) y un `run_info.json` con el commit, la
fecha, los filtros, las sesiones que quedan fuera con su motivo, los recuentos y el sha256 de
cada CSV. El análisis se hace fuera de la plataforma (pandas, R, hojas de cálculo); el
diccionario de columnas está en `docs/experimentos/diccionario_tablas.md`.

Dos orígenes, que pueden ir juntos en las mismas tablas (la columna `source` los distingue):

- una base de datos de Cadenza (`--db-url`, o `CADENZA_DATABASE_URL` si no se da `--corpus`);
- uno o varios corpus JSONL (`--corpus`, repetible): el de PrIMuS de `exp_12`, el de
  Camera-PrIMuS de `exp_18` (#421) o el de `ml suggestions build-dataset`. Un mismo incipit de la
  misma fuente en dos corpus es un error: saldría dos veces.

Con `--recortes` (#414, ADR-0068), en la misma carpeta y para las mismas sesiones, lo que escribe
`ml export-staves` (cada pentagrama de la foto con lo que leyó HOMR y lo corregido); `notas`,
`faltantes`, `barras` y `compases` dicen en `sistema` y `recorte` la tira de la foto de su
compás. Con `--primus-dir`, la imagen de cada incipit de PrIMuS va a `recortes/primus/`; con
`--camera-primus-dir`, la imagen distorsionada de cada incipit de Camera-PrIMuS, a
`recortes/camera-primus/`.

Con `--informe` (#415, ADR-0069), además `informe.html`: las cifras de los CSV y, de cada una,
ejemplos con la foto de su compás (`ml/tables_report.py`).

No tiene salida por defecto: la ruta se da siempre.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from cadenza.learning.consent import ConsentTally
from cadenza.learning.suggestions import SuggestionTrainingError, file_sha256, read_corpus
from cadenza.learning.tables import TABLES, cell, corpus_tables, database_tables, merge_tables
from cadenza.persistence import (
    FilesystemArtifactStore,
    SqlAlchemyEditEventRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
    create_engine_for_url,
    create_session_factory,
    session_scope,
)
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError

from ml.consent_cli import add_consent_options

TABLES_FORMAT_VERSION = 2


def _fail(message: str) -> int:
    print(f"Error: {message}", file=sys.stderr)
    return 1


def _commit() -> str | None:
    """El commit del código que exporta; None fuera de un repositorio git."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _csv_bytes(name: str, rows: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    columns = TABLES[name]
    writer.writerow(columns)
    for row in rows:
        writer.writerow([cell(row.get(column)) for column in columns])
    return buffer.getvalue().encode("utf-8")


def _safe_url(url: str) -> str:
    """Solo el dialecto y el nombre de la base: el run_info se comparte con los CSV, y la URL
    puede llevar usuario, host y contraseña (también en la query)."""
    try:
        parsed = make_url(url)
    except ArgumentError:  # una URL que SQLAlchemy no entiende no se escribe
        return "(no se pudo leer la URL)"
    return f"{parsed.get_backend_name()}:{Path(parsed.database or '').name}"


Row = dict[str, Any]
StripKey = tuple[str, int, int, int]
"""(sesión, parte, pentagrama, número de compás)."""


def _database_strips(
    tables: dict[str, list[Row]],
    sessions: Any,
    edits: Any,
    store: Any,
    output: Path,
    sheets: bool,
) -> tuple[list[Row], list[str], dict[str, str]]:
    """Los recortes de las sesiones que están en las tablas (las mismas, con el mismo filtro):
    sus filas de `pentagramas.csv`, las sesiones con recortes y las que no, con su motivo. Una
    sesión sin recortes sigue en las tablas."""

    from ml.export_staves_cli import export_session_strips

    rows: list[Row] = []
    exported: list[str] = []
    left_out: dict[str, str] = {}
    for score in tables["partituras"]:
        session_id = str(score["session_id"])
        session = sessions.get(session_id)
        if session is None:
            left_out[session_id] = "la sesión ya no está en la base"
            continue
        try:
            reason = export_session_strips(session, edits, store, output, sheets, rows)
        except SQLAlchemyError:
            # Con PostgreSQL, la transacción quedaría abortada para las que siguen.
            raise
        except Exception as exc:  # una sesión rara no para la exportación
            reason = f"no se pudo exportar ({type(exc).__name__}: {exc})"
        if reason is None:
            exported.append(session_id)
        else:
            left_out[session_id] = reason
    return rows, sorted(exported), dict(sorted(left_out.items()))


def _strip_index(rows: list[Row]) -> dict[StripKey, tuple[int, str]]:
    """El sistema y el recorte de cada compás de cada pentagrama de una tira."""
    index: dict[StripKey, tuple[int, str]] = {}
    for row in rows:
        strip = row["_strip"]
        for part, staff in strip.staves:
            for measure in strip.measures:
                index[(row["session_id"], part, staff, measure)] = (strip.system, row["recorte"])
    return index


def _primus_images(
    tables: dict[str, list[Row]], primus_dir: Path, output: Path
) -> tuple[dict[str, tuple[int, str]], list[str]]:
    """Copia la imagen de cada incipit de PrIMuS de las tablas
    (`<primus_dir>/<paquete>/<id>/<id>.png`) a `recortes/primus/`. Devuelve el sistema (1) y el
    recorte de cada incipit encontrado, y los que faltan."""

    wanted = sorted(
        {str(r["incipit_id"]) for r in tables["partituras"] if r.get("source") == "primus"}
    )
    pending = set(wanted)
    found: dict[str, Path] = {}
    for package in sorted(p for p in primus_dir.iterdir() if p.is_dir()):
        with os.scandir(package) as entries:
            for entry in entries:
                if entry.name in pending and entry.is_dir():
                    image = Path(entry.path) / f"{entry.name}.png"
                    if image.is_file():
                        found[entry.name] = image
                        pending.discard(entry.name)
    images: dict[str, tuple[int, str]] = {}
    target = output / "recortes" / "primus"
    for incipit_id, image in sorted(found.items()):
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(image, target / f"{incipit_id}.png")
        images[incipit_id] = (1, f"recortes/primus/{incipit_id}.png")
    return images, [incipit_id for incipit_id in wanted if incipit_id not in found]


CAMERA_PRIMUS = "camera-primus"
"""La fuente del corpus de Camera-PrIMuS (`exp_18`, #421): sus incipits son
`camera-primus:<id de PrIMuS>`."""


def _camera_primus_images(
    tables: dict[str, list[Row]], camera_dir: Path, output: Path
) -> tuple[dict[str, tuple[int, str]], list[str]]:
    """Copia la imagen distorsionada de cada incipit de Camera-PrIMuS de las tablas
    (`<camera_dir>/<id>/<id>_distorted.jpg`, con `camera_dir` la carpeta `Corpus` de la
    descarga) a `recortes/camera-primus/`. Devuelve el sistema (1) y el recorte de cada incipit
    encontrado, y los que faltan."""

    wanted = sorted(
        {str(r["incipit_id"]) for r in tables["partituras"] if r.get("source") == CAMERA_PRIMUS}
    )
    images: dict[str, tuple[int, str]] = {}
    missing: list[str] = []
    target = output / "recortes" / CAMERA_PRIMUS
    for incipit_id in wanted:
        raw = incipit_id.removeprefix(f"{CAMERA_PRIMUS}:")
        image = camera_dir / raw / f"{raw}_distorted.jpg"
        if not image.is_file():
            missing.append(incipit_id)
            continue
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(image, target / f"{raw}.jpg")
        images[incipit_id] = (1, f"recortes/{CAMERA_PRIMUS}/{raw}.jpg")
    return images, missing


def _repeated(records: list[dict[str, Any]], seen: set[tuple[str, str]]) -> list[str]:
    """Los incipits de un corpus que ya trajo otro (misma fuente y mismo identificador); añade
    los suyos a `seen`."""
    own = {(str(r.get("source") or "primus"), str(r["incipit_id"])) for r in records}
    repeated = sorted(f"{source} {incipit}" for source, incipit in own & seen)
    seen |= own
    return repeated


def _number(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _attach_strips(
    tables: dict[str, list[Row]],
    strips: dict[StripKey, tuple[int, str]],
    corpus_images: dict[str, tuple[int, str]],
) -> None:
    """Pone en `sistema` y `recorte` de cada fila de notas, faltantes, barras y compases su tira,
    o la imagen de su incipit si sale de un corpus (PrIMuS, Camera-PrIMuS)."""
    for name in ("notas", "faltantes", "barras", "compases"):
        for row in tables[name]:
            if row.get("source") == "cadenza":
                part, staff, measure = (
                    _number(row.get(key)) for key in ("part", "staff", "measure")
                )
                if part is None or staff is None or measure is None:
                    continue
                hit = strips.get((str(row.get("session_id")), part, staff, measure))
            else:
                hit = corpus_images.get(str(row.get("incipit_id")))
            if hit is not None:
                row["sistema"], row["recorte"] = hit


def export_tables_command(args: argparse.Namespace) -> int:
    corpus_paths = [Path(path) for path in args.corpus or ()]
    db_url = args.db_url or (None if corpus_paths else os.environ.get("CADENZA_DATABASE_URL"))
    if not corpus_paths and db_url is None:
        return _fail("falta el origen: da --db-url (o CADENZA_DATABASE_URL) o --corpus")
    if db_url is not None and args.split_seed is None:
        return _fail(
            "la base necesita --split-seed (la semilla de correction_corpus_split.json de #255)"
        )
    if db_url is None and args.exclude_self_registered:
        # Un corpus trae las sesiones que entraron al hacerlo: no se pueden volver a filtrar.
        return _fail("--exclude-self-registered va con la base (--db-url)")
    from ml.export_staves_cli import strips_csv, unsafe_output

    output = Path(args.output_dir).resolve()
    problem = unsafe_output(output)
    if problem is not None:
        return _fail(problem)
    artifacts = args.artifacts_dir or os.environ.get("CADENZA_ARTIFACTS_DIR")
    if (args.primus_dir or args.camera_primus_dir or args.laminas) and not args.recortes:
        return _fail("--primus-dir, --camera-primus-dir y --laminas van con --recortes")
    if args.recortes and db_url is not None and not artifacts:
        return _fail("los recortes necesitan las fotos: da --artifacts-dir o CADENZA_ARTIFACTS_DIR")
    if args.recortes and db_url is not None and not Path(str(artifacts)).is_dir():
        return _fail(f"no existe la carpeta de las fotos: {artifacts}")
    primus_dir = Path(args.primus_dir) if args.primus_dir else None
    if primus_dir is not None and not primus_dir.is_dir():
        return _fail(f"no existe la carpeta de PrIMuS: {primus_dir}")
    camera_dir = Path(args.camera_primus_dir) if args.camera_primus_dir else None
    if camera_dir is not None and not camera_dir.is_dir():
        return _fail(f"no existe la carpeta de Camera-PrIMuS: {camera_dir}")

    parts: list[dict[str, list[dict[str, Any]]]] = []
    origins: dict[str, Any] = {}
    corpora: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    left_out: dict[str, str] = {}
    consent = ConsentTally()
    for corpus_path in corpus_paths:
        try:
            records = read_corpus(corpus_path)
        except (SuggestionTrainingError, OSError, json.JSONDecodeError) as exc:
            return _fail(str(exc))
        origin: dict[str, Any] = {
            "file": corpus_path.name,
            "sha256": file_sha256(corpus_path),
            "records": len(records),
            "sources": dict(
                sorted(Counter(str(r.get("source") or "primus") for r in records).items())
            ),
        }
        if db_url is not None:
            # El corpus de build-dataset ya trae las sesiones de Cadenza: con la base, salen de
            # la base, que tiene más columnas; si no, cada sesión saldría dos veces.
            kept = [r for r in records if r.get("source", "primus") != "cadenza"]
            origin["cadenza_records_dropped"] = len(records) - len(kept)
            records = kept
        repeated = _repeated(records, seen)
        if repeated:
            return _fail(
                f"{corpus_path.name} repite {len(repeated)} incipits de otro --corpus (p. ej."
                f" {repeated[:3]}): saldrían dos veces en las tablas"
            )
        corpora.append(origin)
        parts.append(corpus_tables(records))
    if corpora:
        # Con un solo corpus, su origen como hasta ahora; con varios, uno por corpus en orden.
        origins["corpus"] = corpora[0] if len(corpora) == 1 else corpora
    strip_rows: list[Row] = []
    strip_sessions: list[str] = []
    strips_left_out: dict[str, str] = {}
    if db_url is not None:
        factory = create_session_factory(create_engine_for_url(db_url))
        with session_scope(factory) as db:
            sessions = SqlAlchemySessionRepository(db)
            edits = SqlAlchemyEditEventRepository(db)
            tables, left_out = database_tables(
                session_repository=sessions,
                edit_repository=edits,
                user_repository=SqlAlchemyUserRepository(db),
                split_seed=args.split_seed,
                test_fraction=args.test_fraction,
                exclude_self_registered=args.exclude_self_registered,
                include_unfinished=args.include_unfinished,
                consent=consent,
            )
            if args.recortes:
                store = FilesystemArtifactStore(Path(str(artifacts)), db)
                strip_rows, strip_sessions, strips_left_out = _database_strips(
                    tables, sessions, edits, store, output, args.laminas
                )
        parts.append(tables)
        origins["database"] = {
            "url": _safe_url(db_url),
            "sessions": len(tables["partituras"]),
        }
    merged = merge_tables(*parts)

    output.mkdir(parents=True, exist_ok=True)
    recortes: dict[str, Any] | None = None
    if args.recortes:
        primus_images: dict[str, tuple[int, str]] = {}
        primus_missing: list[str] = []
        if primus_dir is not None:
            primus_images, primus_missing = _primus_images(merged, primus_dir, output)
        camera_images: dict[str, tuple[int, str]] = {}
        camera_missing: list[str] = []
        if camera_dir is not None:
            camera_images, camera_missing = _camera_primus_images(merged, camera_dir, output)
        _attach_strips(merged, _strip_index(strip_rows), {**primus_images, **camera_images})
        recortes = {
            "sessions": strip_sessions,
            "left_out": strips_left_out,
            "strips": len(strip_rows),
            "strips_corrected": sum(1 for row in strip_rows if row["corregido"]),
            "pentagramas_sha256": None,
            "laminas": args.laminas,
            "artifacts_dir": Path(artifacts).name if artifacts and db_url else None,
            "primus_images": len(primus_images),
            "primus_missing": primus_missing,
            "camera_primus_images": len(camera_images),
            "camera_primus_missing": camera_missing,
        }
        if db_url is not None:
            content = strips_csv(strip_rows)
            (output / "pentagramas.csv").write_bytes(content)
            recortes["pentagramas_sha256"] = hashlib.sha256(content).hexdigest()
    summary: dict[str, Any] = {}
    for name in TABLES:
        content = _csv_bytes(name, merged[name])
        (output / f"{name}.csv").write_bytes(content)
        summary[name] = {
            "rows": len(merged[name]),
            "by_source": dict(sorted(Counter(r.get("source") for r in merged[name]).items())),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    info = {
        "format_version": TABLES_FORMAT_VERSION,
        "simulated": False,
        "commit": _commit(),
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "origins": origins,
        "filters": {
            "exclude_self_registered": args.exclude_self_registered,
            "include_unfinished": args.include_unfinished,
            "split_seed": args.split_seed,
            "test_fraction": args.test_fraction,
        },
        # Sin la base, nada que contar: el corpus trae lo que se exportó al hacerlo.
        "consent": consent.to_primitive() if db_url is not None else None,
        "left_out": dict(sorted(left_out.items())),
        "tables": summary,
        "dictionary": "docs/experimentos/diccionario_tablas.md",
    }
    if recortes is not None:
        info["recortes"] = recortes
    (output / "run_info.json").write_text(
        json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print("[export-tables] Tablas escritas.")
    for name, data in summary.items():
        print(f"  {name:<15}: {data['rows']} filas {data['by_source']}")
    print(
        f"  fuera          : {len(left_out)}, más {consent.without_current_consent} sin el"
        f" permiso vigente y {consent.excluded_by_option} con --exclude-self-registered"
    )
    for session_id, reason in sorted(left_out.items()):
        print(f"    {session_id}: {reason}")
    report = None
    if args.informe:
        from ml.tables_report import write_report

        report = write_report(output)
    if recortes is not None:
        print(
            f"  recortes       : {recortes['strips']} tiras de {len(strip_sessions)} sesiones"
            f" ({len(strips_left_out)} sin recortes), {recortes['primus_images']} imágenes"
            f" de PrIMuS, {recortes['camera_primus_images']} de Camera-PrIMuS"
        )
    if report is not None:
        print(f"  informe        : {report.name}")
    print(f"  salida         : {output}")
    return 0


def add_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "export-tables",
        help="Exporta a CSV los datos para reconocer los errores de HOMR (lectura y corrección).",
    )
    parser.add_argument("--output-dir", required=True, help="Directorio de los CSV y run_info.")
    parser.add_argument(
        "--db-url",
        default=None,
        help="URL de la base (por defecto CADENZA_DATABASE_URL, si no se da --corpus).",
    )
    parser.add_argument(
        "--corpus",
        action="append",
        default=None,
        help="Corpus JSONL (exp_12, exp_18 o build-dataset); se repite para varios.",
    )
    parser.add_argument(
        "--split-seed",
        type=int,
        default=None,
        help="Semilla de la partición de #255 (obligatoria con la base).",
    )
    parser.add_argument("--test-fraction", type=float, default=0.2)
    parser.add_argument(
        "--recortes",
        action="store_true",
        help=(
            "Escribir además los recortes de las fotos de las mismas sesiones (como"
            " export-staves) y unirlos a las tablas por compás."
        ),
    )
    parser.add_argument(
        "--artifacts-dir",
        default=None,
        help="Directorio de los artefactos, con las fotos (o CADENZA_ARTIFACTS_DIR).",
    )
    parser.add_argument(
        "--laminas",
        action="store_true",
        help="Con --recortes, una lámina por sesión: la foto con las cajas y cada tira.",
    )
    parser.add_argument(
        "--informe",
        action="store_true",
        help=(
            "Escribir además informe.html: las cifras de los errores de HOMR y sus ejemplos con"
            " su foto (con --recortes)."
        ),
    )
    parser.add_argument(
        "--primus-dir",
        default=None,
        help="Con --recortes, la carpeta de PrIMuS (data/primus): copia la imagen de cada incipit.",
    )
    parser.add_argument(
        "--camera-primus-dir",
        default=None,
        help=(
            "Con --recortes, la carpeta Corpus de Camera-PrIMuS (data/camera_primus/Corpus): copia"
            " la imagen distorsionada de cada incipit."
        ),
    )
    add_consent_options(parser)
    parser.add_argument(
        "--include-unfinished",
        action="store_true",
        help="Incluir las sesiones sin finalizar (fuera por defecto).",
    )
