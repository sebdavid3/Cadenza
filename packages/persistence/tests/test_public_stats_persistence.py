"""El adaptador SQLAlchemy de las cifras públicas de los errores de HOMR (#423, ADR-0073)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from cadenza.application import PublicStatsGroup
from cadenza.persistence import (
    SqlAlchemyPublicStatsRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
    session_scope,
)

WHEN = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


def _group(group_id: str, source: str = "cadenza", **fields: Any) -> PublicStatsGroup:
    group = PublicStatsGroup(
        id=group_id,
        source=source,
        computed_at=WHEN,
        format_version=1,
        min_sessions=5,
        sessions=7,
        stats={"read": 10, "ops": {"SetPitch": 2}},
    )
    return replace(group, **fields)


def test_replace_keeps_the_other_source_and_lists_cadenza_first() -> None:
    factory = create_session_factory(engine := create_memory_engine())
    create_schema(engine)
    with session_scope(factory) as db:
        repo = SqlAlchemyPublicStatsRepository(db)
        repo.replace("corpus", [_group("primus", "corpus", source_sha256="ab" * 32)])
        repo.replace("cadenza", [_group("pruebas", stats=None, sessions=2), _group("cadenza")])

    with session_scope(factory) as db:
        groups = SqlAlchemyPublicStatsRepository(db).list()

    assert [(g.source, g.id) for g in groups] == [
        ("cadenza", "cadenza"),
        ("cadenza", "pruebas"),
        ("corpus", "primus"),
    ]
    cadenza, pruebas, primus = groups
    assert cadenza.stats == {"read": 10, "ops": {"SetPitch": 2}}
    assert cadenza.computed_at == WHEN
    assert pruebas.stats is None
    assert pruebas.published is False
    assert cadenza.published is True
    assert primus.source_sha256 == "ab" * 32


def test_replace_drops_the_groups_of_that_source_that_no_longer_come() -> None:
    factory = create_session_factory(engine := create_memory_engine())
    create_schema(engine)
    with session_scope(factory) as db:
        repo = SqlAlchemyPublicStatsRepository(db)
        repo.replace("corpus", [_group("primus", "corpus"), _group("muscima", "corpus")])
        repo.replace("cadenza", [_group("cadenza")])
    later = datetime(2026, 11, 19, 12, 5, tzinfo=UTC)
    with session_scope(factory) as db:
        SqlAlchemyPublicStatsRepository(db).replace(
            "corpus", [_group("primus", "corpus", computed_at=later, sessions=9)]
        )

    with session_scope(factory) as db:
        groups = {g.id: g for g in SqlAlchemyPublicStatsRepository(db).list()}

    assert set(groups) == {"cadenza", "primus"}
    assert groups["primus"].sessions == 9
    assert groups["primus"].computed_at == later
