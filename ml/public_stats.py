"""Las cifras públicas de los errores de HOMR, en vivo (#423, ADR-0073).

El servicio `stats` del compose de producción ejecuta `python -m ml.public_stats --every 300`:
cada 5 minutos lee la base en solo lectura, calcula con el código del informe local
(`database_tables`, `aggregate`) las cifras de conjunto de las correcciones y las guarda en
`public_stats`, de donde las sirve `GET /stats/homr-errors`. La API no importa nada de aquí.

Solo se guardan agregados musicales (`PUBLISHED` y el nombre y el símbolo de cada figura): nada
de fotos, ejemplos, filas por sesión, cuentas ni títulos. Un grupo de Cadenza se publica con al
menos `MIN_SESSIONS` sesiones. Cada `<grupo>.jsonl` de `--corpus-dir` (el corpus de PrIMuS de
`exp_12`, y los que vengan) se calcula una vez y solo se repite si cambia el archivo.

Sin `--every`, calcula una vez y termina.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import os
import re
import signal
import sys
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Final

from cadenza.application import PUBLIC_STATS_FORMAT_VERSION, PublicStatsGroup
from cadenza.learning.suggestions import file_sha256, read_corpus
from cadenza.learning.tables import TABLES, cell, corpus_tables, database_tables
from cadenza.persistence import (
    SessionFactory,
    SqlAlchemyEditEventRepository,
    SqlAlchemyPublicStatsRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
    create_engine_for_url,
    create_session_factory,
    session_scope,
)
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from ml.tables_report import REAL_TESTS, aggregate, figure_name, figure_symbol, reordered_chords

logger = logging.getLogger("ml.public_stats")

Row = dict[str, str]

MIN_SESSIONS: Final = 5
"""Sesiones que necesita un grupo de Cadenza para publicarse (ADR-0073 §5)."""
EVERY_SECONDS: Final = 300
"""Cada cuánto recalcula el servicio (`CADENZA_STATS_EVERY_SECONDS` en el compose)."""
RETRY_SECONDS: Final = 60
"""Tras un cálculo fallido (la base aún sin migrar, por ejemplo), se reintenta antes."""
LIVE: Final = "cadenza"
"""El grupo de todas las sesiones que cuentan, y el `source` de los grupos en vivo."""
CORPUS: Final = "corpus"
PUBLISHED: Final[tuple[str, ...]] = (
    "scores",
    "clean_scores",
    "read",
    "outcome",
    "missing",
    "reordered",
    "ops",
    "steps",
    "durations",
    "by_vs_key",
    "by_clef",
    "by_duration",
)
"""Lo que se publica de `aggregate`: sin `examples`, `example_keys` ni `per_score`."""
_CORPUS_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


def as_csv_rows(tables: dict[str, list[dict[str, Any]]]) -> dict[str, list[Row]]:
    """Las tablas con sus valores como en los CSV de `ml export-tables` (`cell`), que es lo que
    lee el informe: así las cifras son las mismas."""
    return {
        name: [{column: cell(row.get(column)) for column in TABLES[name]} for row in rows]
        for name, rows in tables.items()
    }


def group_stats(
    tables: dict[str, list[Row]], only: set[str] | None, reordered: set[int]
) -> dict[str, Any]:
    """Las cifras publicables de unas partituras (`incipit_id`; todas con None), sin contar los
    acordes solo reordenados, y el nombre y el símbolo de cada figura que sale en ellas."""
    data = aggregate(tables, only, True, reordered)
    stats = {key: data[key] for key in PUBLISHED}
    beats = {d["read"] for d in data["durations"]} | {d["fix"] for d in data["durations"]}
    beats |= {str(r["key"]).split(":", 1)[1] for r in data["by_duration"]}
    stats["figures"] = {
        value: {"name": figure_name(value), "symbol": figure_symbol(value)}
        for value in sorted(beats - {"", "—"})
    }
    return stats


def read_only(db: DbSession) -> None:
    """La transacción en curso, de solo lectura en PostgreSQL (ADR-0073 §1)."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET TRANSACTION READ ONLY"))


def cadenza_tables(factory: SessionFactory) -> dict[str, list[Row]]:
    """Las tablas de las sesiones que cuentan (#422): las finalizadas del equipo y las de las
    cuentas del registro con el permiso de uso de los datos vigente. La partición no se usa."""
    with session_scope(factory) as db:
        read_only(db)
        tables, _ = database_tables(
            session_repository=SqlAlchemySessionRepository(db),
            edit_repository=SqlAlchemyEditEventRepository(db),
            user_repository=SqlAlchemyUserRepository(db),
            split_seed=0,
            test_fraction=0.2,
            include_self_registered=True,
        )
    return as_csv_rows(tables)


def cadenza_groups(
    tables: dict[str, list[Row]], computed_at: datetime.datetime
) -> list[PublicStatsGroup]:
    """`cadenza` (todas las sesiones que cuentan) y `pruebas` (las de las cuentas del
    registro), cada uno con sus cifras solo si llega a `MIN_SESSIONS` sesiones."""
    reordered = reordered_chords(tables["notas"])
    partituras = tables["partituras"]
    members = {
        LIVE: {r["incipit_id"] for r in partituras},
        REAL_TESTS: {r["incipit_id"] for r in partituras if r["origen"] == "registro"},
    }
    return [
        PublicStatsGroup(
            id=group_id,
            source=LIVE,
            computed_at=computed_at,
            format_version=PUBLIC_STATS_FORMAT_VERSION,
            min_sessions=MIN_SESSIONS,
            sessions=len(ids),
            stats=group_stats(tables, ids, reordered) if len(ids) >= MIN_SESSIONS else None,
        )
        for group_id, ids in members.items()
    ]


def _corpus_group(path: Path, sha256: str, computed_at: datetime.datetime) -> PublicStatsGroup:
    tables = as_csv_rows(corpus_tables(read_corpus(path)))
    stats = group_stats(tables, None, reordered_chords(tables["notas"]))
    return PublicStatsGroup(
        id=path.stem,
        source=CORPUS,
        computed_at=computed_at,
        format_version=PUBLIC_STATS_FORMAT_VERSION,
        min_sessions=0,
        sessions=len(tables["partituras"]),
        stats=stats,
        source_sha256=sha256,
    )


def corpus_groups(
    corpus_dir: Path,
    stored: Sequence[PublicStatsGroup],
    computed_at: datetime.datetime,
) -> list[PublicStatsGroup]:
    """Un grupo por cada `<grupo>.jsonl` de la carpeta. El que ya está guardado con el mismo
    sha256 y formato se conserva tal cual; uno que no se puede leer se salta con un aviso."""
    previous = {g.id: g for g in stored if g.source == CORPUS}
    groups: list[PublicStatsGroup] = []
    for path in sorted(corpus_dir.glob("*.jsonl")):
        if not _CORPUS_NAME.fullmatch(path.stem) or path.stem in (LIVE, REAL_TESTS):
            logger.warning("public_stats_corpus_skipped file=%s reason=name", path.name)
            continue
        sha256 = file_sha256(path)
        old = previous.get(path.stem)
        if (
            old is not None
            and old.source_sha256 == sha256
            and old.format_version == PUBLIC_STATS_FORMAT_VERSION
        ):
            groups.append(old)
            continue
        try:
            groups.append(_corpus_group(path, sha256, computed_at))
        except Exception as exc:  # un corpus roto no para las cifras en vivo
            logger.warning(
                "public_stats_corpus_skipped file=%s reason=%s: %s",
                path.name,
                type(exc).__name__,
                exc,
            )
    return groups


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def compute_once(
    factory: SessionFactory,
    corpus_dir: Path | None,
    *,
    now: Callable[[], datetime.datetime] = _now,
) -> list[PublicStatsGroup]:
    """Un cálculo: lee (en solo lectura), calcula y guarda. Sin `corpus_dir`, los grupos de
    corpus guardados no se tocan; con él, quedan los de sus archivos."""
    computed_at = now()
    live = cadenza_groups(cadenza_tables(factory), computed_at)
    corpus: list[PublicStatsGroup] | None = None
    if corpus_dir is not None:
        with session_scope(factory) as db:
            stored = SqlAlchemyPublicStatsRepository(db).list()
        corpus = corpus_groups(corpus_dir, stored, computed_at) if corpus_dir.is_dir() else []
    with session_scope(factory) as db:
        repository = SqlAlchemyPublicStatsRepository(db)
        repository.replace(LIVE, live)
        if corpus is not None:
            repository.replace(CORPUS, corpus)
    groups = live + (corpus or [])
    logger.info(
        "public_stats_computed %s",
        " ".join(f"{g.id}={g.sessions}{'' if g.published else '(sin publicar)'}" for g in groups),
    )
    return groups


def run_forever(compute: Callable[[], None], *, every: float, stop: threading.Event) -> None:
    """Calcula cada `every` segundos hasta que se pida parar. Un cálculo que falla se anota y
    se reintenta a los `RETRY_SECONDS` (o antes, si `every` es menor)."""
    while not stop.is_set():
        try:
            compute()
        except Exception:
            logger.exception("public_stats_failed")
            stop.wait(min(every, RETRY_SECONDS))
            continue
        stop.wait(every)


def _configure_logging() -> None:
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def public_stats_command(args: argparse.Namespace) -> int:
    db_url = args.db_url or os.environ.get("CADENZA_DATABASE_URL")
    if not db_url:
        print("Error: falta la base: da --db-url o CADENZA_DATABASE_URL", file=sys.stderr)
        return 1
    corpus_dir = Path(args.corpus_dir) if args.corpus_dir else None
    factory = create_session_factory(create_engine_for_url(db_url))
    if args.every is None:
        groups = compute_once(factory, corpus_dir)
        print("[public-stats] Cifras guardadas en public_stats.")
        for group in groups:
            state = f"{group.sessions} sesiones" if group.published else "sin publicar"
            print(f"  {group.id:<10}: {state}")
        return 0
    if args.every < 1:
        print("Error: --every es un número de segundos, 1 o más", file=sys.stderr)
        return 1
    _configure_logging()
    stop = threading.Event()
    # Como PID 1 del contenedor, SIGTERM no tiene acción por defecto: `docker stop` esperaría.
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    logger.info("public_stats_started every=%s corpus_dir=%s", args.every, corpus_dir)

    def compute() -> None:
        compute_once(factory, corpus_dir)

    run_forever(compute, every=args.every, stop=stop)
    return 0


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--db-url", default=None, help="URL de la base (por defecto CADENZA_DATABASE_URL)."
    )
    parser.add_argument(
        "--corpus-dir",
        default=None,
        help=(
            "Carpeta con un <grupo>.jsonl por corpus (primus.jsonl…); sin ella, los grupos de"
            " corpus guardados no se tocan."
        ),
    )
    parser.add_argument(
        "--every",
        type=float,
        default=None,
        help="Recalcular cada tantos segundos hasta que se pare (sin él, una vez).",
    )


def add_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "public-stats",
        help="Calcula las cifras públicas de los errores de HOMR y las guarda (ADR-0073).",
    )
    add_arguments(parser)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ml.public_stats",
        description="Calcula las cifras públicas de los errores de HOMR (#423, ADR-0073).",
    )
    add_arguments(parser)
    return public_stats_command(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
