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
from cadenza.learning.tables import TABLES
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

from .suggestions_support import SPLIT_SEED, corpus_records, write_corpus
from .test_export_tables import _as_stored, _read_and_final, _session, _user

WHEN = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 11, 19, 12, 5, tzinfo=UTC)
LATEST = datetime(2026, 11, 19, 12, 10, tzinfo=UTC)
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
    db_url: str,
    corpus_dir: Path | None = None,
    when: datetime = WHEN,
    fresh: dict[str, str] | None = None,
) -> dict[str, PublicStatsGroup]:
    groups = public_stats.compute_once(_factory(db_url), corpus_dir, now=lambda: when, fresh=fresh)
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
    process: dict[str, str] = {}  # los cálculos de un mismo proceso del servicio

    _compute(db_url, corpus_dir, fresh=process)
    first = _stored(db_url)["primus"]
    assert first.source == "corpus"
    assert first.published and first.stats is not None
    assert first.source_sha256 == file_sha256(primus)
    assert first.sessions == first.stats["scores"] > 0
    assert first.stats["read"] > 0
    # Un corpus lleva sus ejemplos con el compás dibujado, como el informe local (#424).
    assert first.stats["examples"] and first.stats["example_keys"] and first.stats["bars"]

    _compute(db_url, corpus_dir, when=LATER, fresh=process)
    kept = _stored(db_url)
    assert kept["primus"].computed_at == WHEN  # precalculado: el mismo archivo no se repite
    assert kept["cadenza"].computed_at == LATER

    write_corpus(primus, works=4)
    _compute(db_url, corpus_dir, when=LATER, fresh=process)
    changed = _stored(db_url)["primus"]
    assert changed.computed_at == LATER
    assert changed.sessions > first.sessions

    # Otro proceso (un despliegue, quizá con otro código) lo recalcula una vez.
    restarted: dict[str, str] = {}
    _compute(db_url, corpus_dir, when=LATEST, fresh=restarted)
    assert _stored(db_url)["primus"].computed_at == LATEST
    assert restarted == {"primus": file_sha256(primus)}

    primus.unlink()
    _compute(db_url, corpus_dir, when=LATER, fresh=process)
    assert set(_stored(db_url)) == {"cadenza", "pruebas"}


def test_a_bad_corpus_does_not_stop_the_live_stats(
    db_url: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "roto.jsonl").write_text("{no es json\n", encoding="utf-8")
    write_corpus(corpus_dir / "Mal Nombre.jsonl", works=2)
    write_corpus(corpus_dir / "cadenza.jsonl", works=2)  # no puede tapar al grupo en vivo
    (corpus_dir / "carpeta.jsonl").mkdir()  # no se puede leer
    # Un corpus de build-dataset con sesiones de Cadenza saldría sin el mínimo de sesiones.
    records = [*corpus_records(2), {**corpus_records(1)[0], "source": "cadenza"}]
    (corpus_dir / "dataset.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
    )

    with caplog.at_level(logging.WARNING, logger="ml.public_stats"):
        _compute(db_url, corpus_dir)

    groups = _stored(db_url)
    assert set(groups) == {"cadenza", "pruebas"}
    assert groups["cadenza"].source == "cadenza"
    for name in ("roto.jsonl", "Mal Nombre.jsonl", "cadenza.jsonl", "carpeta.jsonl"):
        assert name in caplog.text
    assert "dataset.jsonl" in caplog.text and "sesiones de Cadenza" in caplog.text


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

    # Una sola foto de la base: una sesión finalizada a mitad no entra sin pasar el filtro.
    assert executed == ["SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"]


def _partitura(index: int, origin: str, account: str) -> dict[str, str]:
    return {
        **dict.fromkeys(TABLES["partituras"], ""),
        "source": "cadenza",
        "incipit_id": f"cadenza:s-{index}",
        "session_id": f"s-{index}",
        "origen": origin,
        "participante": account,
    }


def _published(*groups: tuple[int, str, int]) -> dict[str, bool]:
    """Qué grupos se publican con tantas sesiones de tal origen repartidas en tantas cuentas."""
    rows: list[dict[str, str]] = []
    for sessions, origin, accounts in groups:
        rows += [
            _partitura(len(rows) + i, origin, f"{origin}-{i % accounts}") for i in range(sessions)
        ]
    tables: dict[str, list[dict[str, str]]] = {name: [] for name in TABLES}
    tables["partituras"] = rows
    return {g.id: g.published for g in public_stats.cadenza_groups(tables, WHEN)}


def test_a_group_needs_five_sessions_of_three_accounts() -> None:
    assert _published((5, "registro", 3)) == {"cadenza": True, "pruebas": True}
    # Cinco sesiones de una o dos personas serían sus cifras, no unas de conjunto.
    assert _published((9, "registro", 2)) == {"cadenza": False, "pruebas": False}
    assert _published((4, "registro", 4)) == {"cadenza": False, "pruebas": False}


def test_the_registry_group_is_not_published_if_the_rest_would_show_by_subtraction() -> None:
    # cadenza menos pruebas daría las cifras de las dos sesiones del equipo.
    assert _published((6, "registro", 3), (2, "equipo", 1)) == {
        "cadenza": True,
        "pruebas": False,
    }
    assert _published((6, "registro", 3), (5, "equipo", 1)) == {
        "cadenza": True,
        "pruebas": True,
    }


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
        dumped = values.model_dump(mode="json", exclude_unset=True)
        assert dumped == json.loads(json.dumps(group.stats))
    assert "groups" in HomrErrorStatsRead.model_fields


def test_a_corpus_publishes_its_examples_with_the_drawn_bar_and_no_image(
    db_url: str, tmp_path: Path
) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    write_corpus(corpus_dir / "primus.jsonl", works=6)
    _compute(db_url, corpus_dir)
    stats = _stored(db_url)["primus"].stats
    assert stats is not None

    assert set(stats) == {*public_stats.PUBLISHED, "figures", *public_stats.EXAMPLES}
    examples, keys, bars = stats["examples"], stats["example_keys"], stats["bars"]
    # Ni el historial de cada partitura (`score:`) ni el recorte de la foto.
    assert keys and not any(key.startswith("score:") for key in keys)
    assert all(set(x) == set(public_stats._EXAMPLE_FIELDS) for x in examples)
    assert "img" not in json.dumps(stats)
    used = {i for indices in keys.values() for i in indices}
    assert used == set(range(len(examples)))
    # Cada ejemplo con compás lo encuentra en `bars`, y cada figura tiene su nombre y su símbolo.
    assert {x["bar"] for x in examples if x["bar"]} == set(bars)
    for bar in bars.values():
        assert {e["kind"] for e in [*bar["read"], *bar["fixed"]]} <= {"note", "rest"}
        for event in [*bar["read"], *bar["fixed"]]:
            assert event["beats"] in stats["figures"]
    for example in examples:
        for beats in (example["read_beats"], example["fix_beats"]):
            assert not beats or beats in stats["figures"]


def test_the_cadenza_groups_never_carry_examples_history_or_scores(db_url: str) -> None:
    _compute(db_url)
    cadenza = _stored(db_url)["cadenza"].stats
    assert cadenza is not None

    assert set(cadenza) == {*public_stats.PUBLISHED, "figures"}
    for key in (*public_stats.EXAMPLES, "per_score", "history", "sessions"):
        assert key not in cadenza
