"""`ml export-tables`: los datos para reconocer los errores de HOMR, en CSV planos.

Escribe en `--output-dir` un CSV por tabla (`partituras`, `notas`, `faltantes`,
`clave_armadura`, `compases`, `sugerencias`, `avisos`) y un `run_info.json` con el commit, la
fecha, los filtros, las sesiones que quedan fuera con su motivo, los recuentos y el sha256 de
cada CSV. El análisis se hace fuera de la plataforma (pandas, R, hojas de cálculo); el
diccionario de columnas está en `docs/experimentos/diccionario_tablas.md`.

Dos orígenes, que pueden ir juntos en las mismas tablas (la columna `source` los distingue):

- una base de datos de Cadenza (`--db-url`, o `CADENZA_DATABASE_URL` si no se da `--corpus`);
- un corpus JSONL (`--corpus`): el de PrIMuS de `exp_12` o el de `ml suggestions build-dataset`.

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
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from cadenza.learning.suggestions import SuggestionTrainingError, file_sha256, read_corpus
from cadenza.learning.tables import TABLES, cell, corpus_tables, database_tables, merge_tables
from cadenza.persistence import (
    SqlAlchemyEditEventRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
    create_engine_for_url,
    create_session_factory,
    session_scope,
)
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

TABLES_FORMAT_VERSION = 1


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


def export_tables_command(args: argparse.Namespace) -> int:
    corpus_path = Path(args.corpus) if args.corpus else None
    db_url = args.db_url or (None if corpus_path else os.environ.get("CADENZA_DATABASE_URL"))
    if corpus_path is None and db_url is None:
        return _fail("falta el origen: da --db-url (o CADENZA_DATABASE_URL) o --corpus")
    if db_url is not None and args.split_seed is None:
        return _fail(
            "la base necesita --split-seed (la semilla de correction_corpus_split.json de #255)"
        )

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
    if db_url is not None:
        factory = create_session_factory(create_engine_for_url(db_url))
        with session_scope(factory) as db:
            tables, left_out = database_tables(
                session_repository=SqlAlchemySessionRepository(db),
                edit_repository=SqlAlchemyEditEventRepository(db),
                user_repository=SqlAlchemyUserRepository(db),
                split_seed=args.split_seed,
                test_fraction=args.test_fraction,
                include_self_registered=args.include_self_registered,
                include_unfinished=args.include_unfinished,
            )
        parts.append(tables)
        origins["database"] = {
            "url": _safe_url(db_url),
            "sessions": len(tables["partituras"]),
        }
    merged = merge_tables(*parts)

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
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
    (output / "run_info.json").write_text(
        json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print("[export-tables] Tablas escritas.")
    for name, data in summary.items():
        print(f"  {name:<15}: {data['rows']} filas {data['by_source']}")
    print(f"  fuera          : {len(left_out)}")
    for session_id, reason in sorted(left_out.items()):
        print(f"    {session_id}: {reason}")
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
        "--include-self-registered",
        action="store_true",
        help="Incluir las sesiones de cuentas del registro público (fuera por defecto).",
    )
    parser.add_argument(
        "--include-unfinished",
        action="store_true",
        help="Incluir las sesiones sin finalizar (fuera por defecto).",
    )
