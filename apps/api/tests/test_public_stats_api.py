"""`GET /stats/homr-errors`: las cifras de los errores de HOMR, sin cuenta (#423, ADR-0073).

La API no calcula nada: sirve lo que el servicio `stats` dejó en `public_stats`, solo con los
campos que declara su esquema, con caché en el proceso y en HTTP.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from cadenza.api import Settings, create_app
from cadenza.application import PUBLIC_STATS_FORMAT_VERSION, PublicStatsGroup
from cadenza.persistence import (
    SessionFactory,
    SqlAlchemyPublicStatsRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
    session_scope,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

SECRET = secrets.token_hex(32)
WHEN = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 11, 19, 12, 5, tzinfo=UTC)
PATH = "/stats/homr-errors"

STATS: dict[str, Any] = {
    "scores": 6,
    "clean_scores": 1,
    "read": 120,
    "outcome": {"bien": 100, "corregida": 15, "borrada": 5},
    "missing": 3,
    "reordered": 0,
    "ops": {"SetPitch": 8, "SetDuration": 7, "DeleteEvent": 5, "InsertEvent": 3},
    "steps": {"-1": 3, "1": 5},
    "durations": [{"read": "1/2", "fix": "1", "read_name": "corchea", "fix_name": "negra", "n": 7}],
    "by_vs_key": [
        {"key": "vs:in_key", "label": "según la armadura", "n": 90, "wrong": 9, "rate": 0.1}
    ],
    "by_clef": [{"key": "clef:G2", "label": "clave de sol", "n": 120, "wrong": 20, "rate": 1 / 6}],
    "by_duration": [{"key": "readdur:1", "label": "negra", "n": 60, "wrong": 6, "rate": 0.1}],
    "figures": {
        "1/2": {
            "name": "corchea",
            "symbol": [{"figure": "corchea", "dots": 0, "tuplet": 0, "grace": False}],
        },
        "1": {
            "name": "negra",
            "symbol": [{"figure": "negra", "dots": 0, "tuplet": 0, "grace": False}],
        },
    },
}


def _group(group_id: str, source: str = "cadenza", **fields: Any) -> PublicStatsGroup:
    group = PublicStatsGroup(
        id=group_id,
        source=source,
        computed_at=WHEN,
        format_version=PUBLIC_STATS_FORMAT_VERSION,
        min_sessions=5 if source == "cadenza" else 0,
        sessions=6,
        stats=STATS,
    )
    return replace(group, **fields)


def _app(cache_seconds: int = 0) -> tuple[FastAPI, SessionFactory]:
    engine = create_memory_engine()
    create_schema(engine)
    factory = create_session_factory(engine)
    settings = Settings(auth_secret_key=SECRET, stats_cache_seconds=cache_seconds)
    return create_app(factory, settings=settings), factory


def _store(factory: SessionFactory, source: str, groups: Sequence[PublicStatsGroup]) -> None:
    with session_scope(factory) as db:
        SqlAlchemyPublicStatsRepository(db).replace(source, groups)


def test_without_any_computation_it_answers_with_no_groups_and_no_time() -> None:
    app, _ = _app()

    response = TestClient(app).get(PATH)

    assert response.status_code == 200
    assert response.json() == {"computed_at": None, "groups": []}


def test_it_serves_the_stored_groups_without_an_account() -> None:
    app, factory = _app()
    _store(factory, "cadenza", [_group("cadenza"), _group("pruebas", stats=None, sessions=2)])
    _store(factory, "corpus", [_group("primus", "corpus", sessions=87, computed_at=LATER)])

    response = TestClient(app).get(PATH)

    assert response.status_code == 200
    body = response.json()
    # La hora del último cálculo es la de Cadenza, en vivo; el corpus va precalculado.
    assert body["computed_at"].startswith("2026-11-19T12:00:00")
    assert [g["id"] for g in body["groups"]] == ["cadenza", "pruebas", "primus"]
    cadenza, pruebas, primus = body["groups"]
    assert cadenza["published"] is True
    assert cadenza["sessions"] == 6
    assert cadenza["min_sessions"] == 5
    assert cadenza["stats"]["ops"]["SetPitch"] == 8
    assert cadenza["stats"]["figures"]["1/2"]["name"] == "corchea"
    # Un grupo por debajo del mínimo no dice ni cuántas sesiones tiene.
    assert pruebas == {
        "id": "pruebas",
        "source": "cadenza",
        "computed_at": pruebas["computed_at"],
        "min_sessions": 5,
        "published": False,
        "sessions": None,
        "stats": None,
    }
    assert primus["source"] == "corpus"
    assert primus["sessions"] == 87
    assert primus["computed_at"].startswith("2026-11-19T12:05:00")


def test_only_the_fields_of_the_schema_are_published() -> None:
    app, factory = _app()
    leaked = {
        **STATS,
        "examples": [{"img": "recortes/s-1/sistema-1.png", "score": "TS-01 · sesión abcd"}],
        "per_score": {"cadenza:s-1": [10, 2]},
    }
    _store(factory, "cadenza", [_group("cadenza", stats=leaked, source_sha256="ab" * 32)])

    text = TestClient(app).get(PATH).text

    for forbidden in ("examples", "recortes", "per_score", "TS-01", "cadenza:s-1", "ab" * 32):
        assert forbidden not in text


def test_a_group_of_another_format_or_that_does_not_validate_is_left_out(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app, factory = _app()
    broken = {key: value for key, value in STATS.items() if key != "ops"}
    _store(
        factory,
        "cadenza",
        [_group("cadenza"), _group("pruebas", stats=broken)],
    )
    _store(factory, "corpus", [_group("primus", "corpus", format_version=99)])

    with caplog.at_level(logging.WARNING, logger="cadenza.api"):
        body = TestClient(app).get(PATH).json()

    assert [g["id"] for g in body["groups"]] == ["cadenza"]
    assert "pruebas" in caplog.text
    assert "primus" in caplog.text


def test_a_live_group_under_the_minimum_is_not_published_even_if_stored_with_stats(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app, factory = _app()
    _store(factory, "cadenza", [_group("cadenza", sessions=4)])

    with caplog.at_level(logging.WARNING, logger="cadenza.api"):
        group = TestClient(app).get(PATH).json()["groups"][0]

    assert (group["published"], group["sessions"], group["stats"]) == (False, None, None)
    assert "min_sessions" in caplog.text


def test_it_can_be_cached_and_answers_304_to_the_same_etag() -> None:
    app, factory = _app()
    _store(factory, "cadenza", [_group("cadenza")])
    client = TestClient(app)

    first = client.get(PATH)
    etag = first.headers["ETag"]
    assert first.headers["Cache-Control"] == "public, max-age=60"
    again = client.get(PATH, headers={"If-None-Match": etag})

    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["ETag"] == etag
    _store(factory, "cadenza", [_group("cadenza", computed_at=LATER)])
    changed = client.get(PATH, headers={"If-None-Match": etag})
    assert changed.status_code == 200
    assert changed.headers["ETag"] != etag


def test_the_process_cache_spares_the_database_until_it_expires() -> None:
    app, factory = _app(cache_seconds=60)
    clock = [0.0]
    app.state.stats_monotonic = lambda: clock[0]
    _store(factory, "cadenza", [_group("cadenza")])
    client = TestClient(app)
    assert client.get(PATH).json()["groups"][0]["sessions"] == 6

    _store(factory, "cadenza", [_group("cadenza", sessions=7)])
    clock[0] = 59.0
    assert client.get(PATH).json()["groups"][0]["sessions"] == 6
    clock[0] = 61.0
    response = client.get(PATH)
    assert response.json()["groups"][0]["sessions"] == 7
    assert response.headers["Cache-Control"] == "public, max-age=60"


def test_the_contract_declares_the_endpoint_without_security() -> None:
    app, _ = _app()
    operation = app.openapi()["paths"][PATH]["get"]

    assert "security" not in operation
    assert "304" in operation["responses"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/HomrErrorStatsRead"}
