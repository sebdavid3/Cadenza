"""Transcribir sin cuenta y reclamarlo al entrar, en la capa de aplicación (#278, ADR-0054)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cadenza.application import (
    InMemoryArtifactStore,
    InMemoryPreviewRepository,
    InMemorySessionRepository,
    PreviewCapacityExceeded,
    PreviewNotFound,
    PreviewResult,
    Role,
    User,
    claim_preview,
    create_preview,
    ensure_preview_capacity,
    hash_claim_token,
)
from cadenza.domain import Instrument, PartMetadata, ScoreMetadata
from cadenza.omr.testing import FakeOMREngine
from cadenza.validation import ValidationEngine, get_default_rules

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
ANA = User(id="ana", username="ana", password_hash="-", role=Role.TRANSCRIPTOR)


def _preview(
    tmp_path: Path, repo: InMemoryPreviewRepository, metadata: ScoreMetadata | None = None
) -> PreviewResult:
    image = tmp_path / "minueto.png"
    image.write_bytes(PNG)
    return create_preview(
        image,
        omr_engine=FakeOMREngine(),
        validator=ValidationEngine(get_default_rules()),
        preview_repository=repo,
        now=NOW,
        ttl=timedelta(hours=1),
        source_filename="minueto.png",
        metadata=metadata,
    )


def test_a_preview_keeps_the_document_and_the_image_but_only_a_hash_of_the_token(
    tmp_path: Path,
) -> None:
    repo = InMemoryPreviewRepository()
    metadata = ScoreMetadata(
        title="Minueto", parts=(PartMetadata(Instrument.VIOLIN), PartMetadata(Instrument.PIANO))
    )

    result = _preview(tmp_path, repo, metadata=metadata)

    stored = repo.get(result.preview_id)
    assert stored is not None
    assert stored.image == PNG
    assert stored.token_hash == hash_claim_token(result.claim_token)
    assert stored.token_hash != result.claim_token
    assert stored.expires_at == NOW + timedelta(hours=1)
    # Sin las partes que HOMR no detectó, como al transcribir (ADR-0041 §3).
    assert stored.metadata.parts == (PartMetadata(Instrument.VIOLIN),)
    assert stored.document["provenance"]["rules_version"]


def test_claiming_creates_the_same_session_once_with_the_user_as_owner(tmp_path: Path) -> None:
    previews = InMemoryPreviewRepository()
    sessions = InMemorySessionRepository()
    artifacts = InMemoryArtifactStore()
    result = _preview(tmp_path, previews, metadata=ScoreMetadata(title="Minueto"))

    claimed = claim_preview(
        result.preview_id,
        result.claim_token,
        preview_repository=previews,
        session_repository=sessions,
        artifact_store=artifacts,
        validator=ValidationEngine(get_default_rules()),
        current_user=ANA,
        now=NOW + timedelta(minutes=5),
    )

    session = sessions.get(claimed.session_id)
    assert session is not None
    assert session.owner_id == "ana"
    assert session.condition == "assisted"
    assert session.metadata.title == "Minueto"
    assert session.source_filename == "minueto.png"
    assert session.image_artifact is not None
    assert artifacts.get(session.image_artifact) == PNG
    assert session.document["score"] == result.document.score.to_primitive()
    assert claimed.findings_count == result.findings_count
    assert previews.get(result.preview_id) is None

    with pytest.raises(PreviewNotFound):
        claim_preview(
            result.preview_id,
            result.claim_token,
            preview_repository=previews,
            session_repository=sessions,
            artifact_store=artifacts,
            validator=ValidationEngine([]),
            current_user=ANA,
            now=NOW,
        )


@pytest.mark.parametrize(
    ("token", "minutes"),
    [("otro", 5), (None, 61)],
    ids=["otro token", "caducada"],
)
def test_a_wrong_token_or_an_expired_preview_is_not_found(
    tmp_path: Path, token: str | None, minutes: int
) -> None:
    previews = InMemoryPreviewRepository()
    result = _preview(tmp_path, previews)

    with pytest.raises(PreviewNotFound):
        claim_preview(
            result.preview_id,
            token or result.claim_token,
            preview_repository=previews,
            session_repository=InMemorySessionRepository(),
            artifact_store=InMemoryArtifactStore(),
            validator=ValidationEngine([]),
            current_user=ANA,
            now=NOW + timedelta(minutes=minutes),
        )
    # Un token equivocado no la gasta; la caducada, en cambio, se borra al intentarlo.
    assert (previews.get(result.preview_id) is not None) == (token is not None)


def test_capacity_purges_the_expired_and_counts_the_rest(tmp_path: Path) -> None:
    previews = InMemoryPreviewRepository()
    _preview(tmp_path, previews)

    with pytest.raises(PreviewCapacityExceeded):
        ensure_preview_capacity(previews, now=NOW, max_active=1)

    ensure_preview_capacity(previews, now=NOW + timedelta(hours=2), max_active=1)
    assert previews.previews == {}
