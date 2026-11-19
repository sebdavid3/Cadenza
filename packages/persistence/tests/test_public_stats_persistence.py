"""El adaptador SQLAlchemy de las cifras públicas de los errores de HOMR (#423, ADR-0073)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from cadenza.application import PublicStatsGroup, PublicStatsImage
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


DETAIL: dict[str, Any] = {"id": "primus:1", "label": "1", "read": 12, "fixes": 2, "examples": []}


def test_the_detail_of_a_score_is_kept_until_its_group_goes_away() -> None:
    factory = create_session_factory(engine := create_memory_engine())
    create_schema(engine)
    primus = _group("primus", "corpus", format_version=3)
    camera = _group("camera-primus", "corpus")
    with session_scope(factory) as db:
        repo = SqlAlchemyPublicStatsRepository(db)
        repo.replace("corpus", [primus, camera])
        repo.replace_scores(primus, {"primus:1": DETAIL, "primus:2": {**DETAIL, "fixes": 0}})
        repo.replace_scores(camera, {"camera-primus:1": DETAIL})

    with session_scope(factory) as db:
        repo = SqlAlchemyPublicStatsRepository(db)
        score = repo.get_score("primus", "primus:1")
        assert score is not None
        assert (score.source, score.format_version, score.computed_at) == ("corpus", 3, WHEN)
        assert score.detail == DETAIL
        assert repo.get_score("primus", "primus:3") is None
        assert repo.get_score("camera-primus", "primus:1") is None
        # Reescribir los grupos sin recalcular uno no borra el detalle de sus partituras.
        repo.replace("corpus", [primus, camera])
        assert repo.get_score("camera-primus", "camera-primus:1") is not None
        # Recalcular uno sustituye el de sus partituras.
        repo.replace_scores(primus, {"primus:2": DETAIL})
        assert repo.get_score("primus", "primus:1") is None
        # Un grupo que ya no está se lleva el de las suyas.
        repo.replace("corpus", [primus])
        assert repo.get_score("camera-primus", "camera-primus:1") is None
        assert repo.get_score("primus", "primus:2") is not None


def test_the_image_of_a_score_is_stored_with_its_detail_and_read_apart() -> None:
    factory = create_session_factory(engine := create_memory_engine())
    create_schema(engine)
    primus = _group("primus", "corpus")
    png = PublicStatsImage(media_type="image/png", content=b"\x89PNG\r\n\x1a\n" + b"imagen")
    with session_scope(factory) as db:
        repo = SqlAlchemyPublicStatsRepository(db)
        repo.replace("corpus", [primus])
        repo.replace_scores(
            primus,
            {"primus:1": DETAIL, "primus:2": DETAIL},
            {"primus:1": png, "primus:9": png},  # una que no está en el detalle no se guarda
        )

    with session_scope(factory) as db:
        repo = SqlAlchemyPublicStatsRepository(db)
        assert repo.get_image("primus", "primus:1") == png
        assert repo.get_image("primus", "primus:2") is None
        assert repo.get_image("primus", "primus:9") is None
        repo.replace("corpus", [])
        assert repo.get_image("primus", "primus:1") is None
