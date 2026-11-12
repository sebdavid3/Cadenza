"""`ml export-tables`: los datos para reconocer los errores de HOMR, en CSV planos.

Escribe en `--output-dir` un CSV por tabla (`partituras`, `notas`, `faltantes`,
`clave_armadura`, `compases`, `sugerencias`, `avisos`) y un `run_info.json` con el commit, la
fecha, los filtros, las sesiones que quedan fuera con su motivo, los recuentos y el sha256 de
cada CSV. El análisis se hace fuera de la plataforma (pandas, R, hojas de cálculo); el
diccionario de columnas está en `docs/experimentos/diccionario_tablas.md`.

Dos orígenes, que pueden ir juntos en las mismas tablas (la columna `source` los distingue):

- una base de datos de Cadenza (`--db-url`, o `CADENZA_DATABASE_URL` si no se da `--corpus`);
- un corpus JSONL (`--corpus`): el de PrIMuS de `exp_12` o el de `ml suggestions build-dataset`.

Con `--recortes` (#414, ADR-0068), en la misma carpeta y para las mismas sesiones, lo que escribe
`ml export-staves` (cada pentagrama de la foto con lo que leyó HOMR y lo corregido); `notas`,
`faltantes` y `compases` dicen en `sistema` y `recorte` la tira de la foto de su compás. Con
`--primus-dir`, la imagen de cada incipit de PrIMuS va a `recortes/primus/`.

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


def _number(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _attach_strips(
    tables: dict[str, list[Row]],
    strips: dict[StripKey, tuple[int, str]],
    primus: dict[str, tuple[int, str]],
) -> None:
    """Pone en `sistema` y `recorte` de cada fila de notas, faltantes y compases su tira."""
    for name in ("notas", "faltantes", "compases"):
        for row in tables[name]:
            if row.get("source") == "cadenza":
                part, staff, measure = (
                    _number(row.get(key)) for key in ("part", "staff", "measure")
                )
                if part is None or staff is None or measure is None:
                    continue
                hit = strips.get((str(row.get("session_id")), part, staff, measure))
            else:
                hit = primus.get(str(row.get("incipit_id")))
            if hit is not None:
                row["sistema"], row["recorte"] = hit


def export_tables_command(args: argparse.Namespace) -> int:
    corpus_path = Path(args.corpus) if args.corpus else None
    db_url = args.db_url or (None if corpus_path else os.environ.get("CADENZA_DATABASE_URL"))
    if corpus_path is None and db_url is None:
        return _fail("falta el origen: da --db-url (o CADENZA_DATABASE_URL) o --corpus")
    if db_url is not None and args.split_seed is None:
        return _fail(
            "la base necesita --split-seed (la semilla de correction_corpus_split.json de #255)"
        )
    from ml.export_staves_cli import strips_csv, unsafe_output

    output = Path(args.output_dir).resolve()
    problem = unsafe_output(output)
    if problem is not None:
        return _fail(problem)
    artifacts = args.artifacts_dir or os.environ.get("CADENZA_ARTIFACTS_DIR")
    if (args.primus_dir or args.laminas) and not args.recortes:
        return _fail("--primus-dir y --laminas van con --recortes")
    if args.recortes and db_url is not None and not artifacts:
        return _fail("los recortes necesitan las fotos: da --artifacts-dir o CADENZA_ARTIFACTS_DIR")
    if args.recortes and db_url is not None and not Path(str(artifacts)).is_dir():
        return _fail(f"no existe la carpeta de las fotos: {artifacts}")
    primus_dir = Path(args.primus_dir) if args.primus_dir else None
    if primus_dir is not None and not primus_dir.is_dir():
        return _fail(f"no existe la carpeta de PrIMuS: {primus_dir}")

    parts: list[dict[str, list[dict[str, Any]]]] = []
    origins: dict[str, Any] = {}
    left_out: dict[str, str] = {}
    if corpus_path is not None:
        try:
            records = read_corpus(corpus_path)
        except (SuggestionTrainingError, OSError, json.JSONDecodeError) as exc:
            return _fail(str(exc))
        origins["corpus"] = {
            "file": corpus_path.name,
            "sha256": file_sha256(corpus_path),
            "records": len(records),
        }
        if db_url is not None:
            # El corpus de build-dataset ya trae las sesiones de Cadenza: con la base, salen de
            # la base, que tiene más columnas; si no, cada sesión saldría dos veces.
            kept = [r for r in records if r.get("source", "primus") != "cadenza"]
            origins["corpus"]["cadenza_records_dropped"] = len(records) - len(kept)
            records = kept
        parts.append(corpus_tables(records))
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
                include_self_registered=args.include_self_registered,
                include_unfinished=args.include_unfinished,
            )
            if args.recortes:
                store = FilesystemArtifactStore(artifacts, db)
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
        _attach_strips(merged, _strip_index(strip_rows), primus_images)
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
            "include_self_registered": args.include_self_registered,
            "include_unfinished": args.include_unfinished,
            "split_seed": args.split_seed,
            "test_fraction": args.test_fraction,
        },
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
    print(f"  fuera          : {len(left_out)}")
    for session_id, reason in sorted(left_out.items()):
        print(f"    {session_id}: {reason}")
    if recortes is not None:
        print(
            f"  recortes       : {recortes['strips']} tiras de {len(strip_sessions)} sesiones"
            f" ({len(strips_left_out)} sin recortes), {recortes['primus_images']} imágenes"
            " de PrIMuS"
        )
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
    parser.add_argument("--corpus", default=None, help="Corpus JSONL (exp_12 o build-dataset).")
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
        "--primus-dir",
        default=None,
        help="Con --recortes, la carpeta de PrIMuS (data/primus): copia la imagen de cada incipit.",
    )
    parser.add_argument(
        "--include-self-registered",
        action="store_true",
        help=(
            "Incluir las sesiones de cuentas del registro público con el permiso de uso de los"
            " datos vigente (fuera por defecto)."
        ),
    )
    parser.add_argument(
        "--include-unfinished",
        action="store_true",
        help="Incluir las sesiones sin finalizar (fuera por defecto).",
    )
