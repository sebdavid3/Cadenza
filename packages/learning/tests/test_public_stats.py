"""Las cifras públicas de los errores de HOMR, en vivo (`ml/public_stats.py`, #423, ADR-0073).

La base tiene cuatro sesiones finalizadas del equipo y dos de cuentas del registro con el permiso
vigente, que cuentan, y otras que no: una sin terminar, una del registro sin permiso y otra con
el permiso de un texto anterior. Las cifras son las del informe local (`aggregate`) con esas
sesiones, y solo salen agregados: ni cuentas, ni sesiones, ni títulos, ni fotos.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from cadenza.api.schemas import HomrErrorStatsRead, HomrErrorStatsValuesRead
from cadenza.application import DATA_CONSENT_VERSION, PublicStatsGroup
from cadenza.learning import derive_edit_events
from cadenza.learning.suggestions import file_sha256
from cadenza.persistence import (
    SessionFactory,
    SqlAlchemyEditEventRepository,
    SqlAlchemyPublicStatsRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
    create_engine_for_url,
    create_schema,
    create_session_factory,
    session_scope,
)
from sqlalchemy.orm import Session as DbSession

from ml import public_stats, tables_report
from ml.cli import main as ml_main

from .suggestions_support import SPLIT_SEED, write_corpus
from .test_export_tables import _as_stored, _read_and_final, _session, _user

WHEN = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 11, 19, 12, 5, tzinfo=UTC)
TEAM = [f"s-equipo-{i}" for i in range(4)]
REGISTRY = ["s-visita-1", "s-visita-2"]


def _factory(db_url: str) -> SessionFactory:
    return create_session_factory(create_engine_for_url(db_url))


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = f"sqlite:///{(tmp_path / 'cadenza.db').as_posix()}"
    engine = create_engine_for_url(url)
    create_schema(engine)
    read, final = _read_and_final()
    consent = datetime(2026, 11, 19, tzinfo=UTC)
    with session_scope(create_session_factory(engine)) as db:
        users = SqlAlchemyUserRepository(db)
        users.add(_user("ana"))
        for name in ("visita-1", "visita-2"):
            users.add(
                replace(
                    _user(name, self_registered=True),
                    data_consent_at=consent,
                    data_consent_version=DATA_CONSENT_VERSION,
                )
            )
        users.add(_user("anonima", self_registered=True))
        users.add(
            replace(
                _user("antigua", self_registered=True),
                data_consent_at=consent,
                data_consent_version="2026-11-09",
            )
        )
        sessions = SqlAlchemySessionRepository(db)
        edits = SqlAlchemyEditEventRepository(db)
        owned = [(s, "ana", {"test_score_id": "TS-01"}) for s in TEAM]
        owned += [
            ("s-visita-1", "visita-1", {"image": "c1" * 32}),
            ("s-visita-2", "visita-2", {"image": "c2" * 32}),
            ("s-sin-permiso", "anonima", {"image": "c3" * 32}),
            ("s-permiso-antiguo", "antigua", {"image": "c4" * 32}),
        ]
        for session_id, owner, fields in owned:
            sessions.add(_session(session_id, owner, read, status="finalized", **fields), [])
            for edit in derive_edit_events(
                read, final, document_id=f"doc-{session_id}", author=owner
            ):
                edits.append(session_id, _as_stored(edit))
        sessions.add(_session("s-abierta", "ana", read, test_score_id="TS-02"), [])
    return url


def _compute(
    db_url: str, corpus_dir: Path | None = None, when: datetime = WHEN
) -> dict[str, PublicStatsGroup]:
    groups = public_stats.compute_once(_factory(db_url), corpus_dir, now=lambda: when)
    return {g.id: g for g in groups}


def _stored(db_url: str) -> dict[str, PublicStatsGroup]:
    with session_scope(_factory(db_url)) as db:
        return {g.id: g for g in SqlAlchemyPublicStatsRepository(db).list()}


def test_the_sessions_that_count_are_those_of_422_and_the_group_needs_five(db_url: str) -> None:
    _compute(db_url)
    groups = _stored(db_url)

    assert set(groups) == {"cadenza", "pruebas"}
    cadenza, pruebas = groups["cadenza"], groups["pruebas"]
    # Las del equipo y las del registro con el permiso vigente; nunca sin él ni sin terminar.
    assert cadenza.sessions == len(TEAM) + len(REGISTRY)
    assert cadenza.published and cadenza.stats is not None
    assert cadenza.stats["scores"] == len(TEAM) + len(REGISTRY)
    assert cadenza.computed_at == WHEN
    assert cadenza.min_sessions == public_stats.MIN_SESSIONS == 5
    # Las pruebas reales son dos sesiones: no llegan al mínimo y no se publican.
    assert pruebas.sessions == len(REGISTRY)
    assert not pruebas.published and pruebas.stats is None


def test_the_stats_are_those_of_the_local_report_with_the_same_sessions(
    db_url: str, tmp_path: Path
) -> None:
    output = tmp_path / "tablas"
    exported = ml_main(
        [
            "export-tables",
            "--output-dir",
            str(output),
            "--db-url",
            db_url,
            "--split-seed",
            str(SPLIT_SEED),
            "--include-self-registered",
        ]
    )
    assert exported == 0
    report = tables_report.report_data(output)["variants"]["todas|1"]

    _compute(db_url)
    stats = _stored(db_url)["cadenza"].stats
    assert stats is not None

    assert set(stats) == {*public_stats.PUBLISHED, "figures"}
    for key in public_stats.PUBLISHED:
        assert stats[key] == report[key], key
    assert stats["ops"]["SetPitch"] > 0
    assert stats["durations"]
    beats = {d["read"] for d in stats["durations"]} | {d["fix"] for d in stats["durations"]}
    for value in beats:
        assert stats["figures"][value] == {
            "name": tables_report.figure_name(value),
            "symbol": tables_report.figure_symbol(value),
        }


def test_nothing_that_identifies_a_session_or_an_account_is_published(db_url: str) -> None:
    _compute(db_url)
    text = json.dumps([g.stats for g in _stored(db_url).values()], ensure_ascii=False)

    for forbidden in (
        "P-ana",
        "P-visita",
        "s-equipo",
        "s-visita",
        "TS-01",
        "doc-",
        "Nombre Apellido",
        "c1" * 32,
        "recorte",
        "img",
        "examples",
        "per_score",
        "2026-11-09",
    ):
        assert forbidden not in text, forbidden


def test_a_withdrawn_consent_leaves_on_the_next_computation(db_url: str) -> None:
    _compute(db_url)
    with session_scope(_factory(db_url)) as db:
        users = SqlAlchemyUserRepository(db)
        visita = users.get_by_username("P-visita-1")
        assert visita is not None
        users.update(replace(visita, data_consent_at=None, data_consent_version=None))

    _compute(db_url, when=LATER)

    cadenza = _stored(db_url)["cadenza"]
    assert cadenza.sessions == len(TEAM) + len(REGISTRY) - 1
    assert cadenza.computed_at == LATER


def test_a_corpus_is_computed_once_and_again_only_when_it_changes(
    db_url: str, tmp_path: Path
) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    primus = write_corpus(corpus_dir / "primus.jsonl", works=3)

    _compute(db_url, corpus_dir)
    first = _stored(db_url)["primus"]
    assert first.source == "corpus"
    assert first.published and first.stats is not None
    assert first.source_sha256 == file_sha256(primus)
    assert first.sessions == first.stats["scores"] > 0
    assert first.stats["read"] > 0

    _compute(db_url, corpus_dir, when=LATER)
    kept = _stored(db_url)
    assert kept["primus"].computed_at == WHEN  # precalculado: el mismo archivo no se repite
    assert kept["cadenza"].computed_at == LATER

    write_corpus(primus, works=4)
    _compute(db_url, corpus_dir, when=LATER)
    changed = _stored(db_url)["primus"]
    assert changed.computed_at == LATER
    assert changed.sessions > first.sessions

    primus.unlink()
    _compute(db_url, corpus_dir, when=LATER)
    assert set(_stored(db_url)) == {"cadenza", "pruebas"}


def test_a_bad_corpus_does_not_stop_the_live_stats(
    db_url: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "roto.jsonl").write_text("{no es json\n", encoding="utf-8")
    write_corpus(corpus_dir / "Mal Nombre.jsonl", works=2)
    write_corpus(corpus_dir / "cadenza.jsonl", works=2)  # no puede tapar al grupo en vivo

    with caplog.at_level(logging.WARNING, logger="ml.public_stats"):
        _compute(db_url, corpus_dir)

    groups = _stored(db_url)
    assert set(groups) == {"cadenza", "pruebas"}
    assert groups["cadenza"].source == "cadenza"
    assert "roto.jsonl" in caplog.text
    assert "Mal Nombre.jsonl" in caplog.text


def test_without_a_corpus_folder_the_stored_corpus_groups_stay(db_url: str, tmp_path: Path) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    write_corpus(corpus_dir / "primus.jsonl", works=2)
    _compute(db_url, corpus_dir)

    _compute(db_url, None, when=LATER)

    assert _stored(db_url)["primus"].computed_at == WHEN


def test_the_reading_is_read_only_in_postgresql() -> None:
    executed: list[str] = []

    class _Dialect:
        name = "postgresql"

    class _Bind:
        dialect = _Dialect()

    class _Db:
        def get_bind(self) -> _Bind:
            return _Bind()

        def execute(self, statement: Any) -> None:
            executed.append(str(statement))

    public_stats.read_only(cast(DbSession, _Db()))  # un doble mínimo de la sesión

    assert executed == ["SET TRANSACTION READ ONLY"]


def test_the_loop_survives_a_failed_computation_and_stops_when_asked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stop = threading.Event()
    calls: list[int] = []

    def compute() -> None:
        calls.append(len(calls))
        if len(calls) == 1:
            raise RuntimeError("la base no responde")
        stop.set()

    with caplog.at_level(logging.ERROR, logger="ml.public_stats"):
        public_stats.run_forever(compute, every=0, stop=stop)

    assert calls == [0, 1]
    assert "la base no responde" in caplog.text


@pytest.mark.parametrize(
    "run",
    [
        lambda url: public_stats.main(["--db-url", url]),
        lambda url: ml_main(["public-stats", "--db-url", url]),
    ],
    ids=["python -m ml.public_stats", "ml public-stats"],
)
def test_the_command_computes_once_without_every(
    db_url: str, run: Callable[[str], int], capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(db_url) == 0
    assert _stored(db_url)["cadenza"].published
    assert "cadenza" in capsys.readouterr().out


def test_the_command_needs_a_database(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CADENZA_DATABASE_URL", raising=False)
    assert public_stats.main([]) == 1
    assert "CADENZA_DATABASE_URL" in capsys.readouterr().err


def test_the_api_schema_publishes_every_computed_value(db_url: str, tmp_path: Path) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    write_corpus(corpus_dir / "primus.jsonl", works=3)
    _compute(db_url, corpus_dir)

    for group in _stored(db_url).values():
        if group.stats is None:
            continue
        values = HomrErrorStatsValuesRead.model_validate(group.stats)
        # Nada calculado se queda fuera del esquema, y el esquema no pide nada que no se calcule.
        assert values.model_dump(mode="json") == json.loads(json.dumps(group.stats))
    assert "groups" in HomrErrorStatsRead.model_fields
