"""El puerto de las cifras públicas de los errores de HOMR (#423, ADR-0073)."""

from __future__ import annotations

from datetime import UTC, datetime

from cadenza.application import (
    PUBLIC_STATS_FORMAT_VERSION,
    InMemoryPublicStatsRepository,
    PublicStatsGroup,
    PublicStatsImage,
)

WHEN = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


def _group(group_id: str, source: str, stats: dict[str, int] | None) -> PublicStatsGroup:
    return PublicStatsGroup(
        id=group_id,
        source=source,
        computed_at=WHEN,
        format_version=PUBLIC_STATS_FORMAT_VERSION,
        min_sessions=5,
        sessions=6,
        stats=stats,
    )


def test_the_in_memory_repository_replaces_by_source_and_lists_cadenza_first() -> None:
    repo = InMemoryPublicStatsRepository()
    repo.replace("corpus", [_group("primus", "corpus", {"read": 3})])
    repo.replace("cadenza", [_group("pruebas", "cadenza", None), _group("cadenza", "cadenza", {})])
    repo.replace("cadenza", [_group("cadenza", "cadenza", {"read": 1})])

    groups = repo.list()

    assert [(g.source, g.id) for g in groups] == [("cadenza", "cadenza"), ("corpus", "primus")]
    assert groups[0].stats == {"read": 1}
    assert groups[0].published


def test_a_group_without_stats_is_not_published() -> None:
    assert not _group("pruebas", "cadenza", None).published


def test_the_in_memory_repository_keeps_the_detail_of_a_score_while_its_group_is_there() -> None:
    repo = InMemoryPublicStatsRepository()
    primus = _group("primus", "corpus", {"read": 3})
    repo.replace("corpus", [primus])
    png = PublicStatsImage(media_type="image/png", content=b"png")
    repo.replace_scores(primus, {"primus:1": {"fixes": 2}}, {"primus:1": png})
    assert repo.get_image("primus", "primus:1") == png

    score = repo.get_score("primus", "primus:1")
    assert score is not None
    assert (score.source, score.detail) == ("corpus", {"fixes": 2})
    assert repo.get_score("primus", "primus:2") is None
    repo.replace("corpus", [])
    assert repo.get_score("primus", "primus:1") is None
    assert repo.get_image("primus", "primus:1") is None
