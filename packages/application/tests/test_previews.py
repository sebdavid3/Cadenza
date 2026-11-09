"""Transcribir sin cuenta y reclamarlo al entrar, en la capa de aplicación (#278, ADR-0054)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cadenza.application import (
    InMemoryArtifactStore,
    InMemoryPreviewRepository,
    InMemorySessionRepository,
    PreviewCapacityExceeded,
    PreviewData,
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
from cadenza.omr import MeterFeature, MeterStage
from cadenza.omr.testing import FakeOMREngine
from cadenza.validation import ValidationEngine, get_default_rules

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
ANA = User(id="ana", username="ana", password_hash="-", role=Role.TRANSCRIPTOR)
LUIS = User(id="luis", username="luis", password_hash="-", role=Role.TRANSCRIPTOR)


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

    # Si se perdió la respuesta, la misma cuenta recibe su sesión otra vez y no se crea otra
    # (#278); otra cuenta, como si no existiera.
    again = claim_preview(
        result.preview_id,
        result.claim_token,
        preview_repository=previews,
        session_repository=sessions,
        artifact_store=artifacts,
        validator=ValidationEngine([]),
        current_user=ANA,
        now=NOW,
    )
    assert again == claimed
    assert len(sessions.list()) == 1
    with pytest.raises(PreviewNotFound):
        claim_preview(
            result.preview_id,
            result.claim_token,
            preview_repository=previews,
            session_repository=sessions,
            artifact_store=artifacts,
            validator=ValidationEngine([]),
            current_user=LUIS,
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


def test_a_preview_runs_the_meter_stage_and_the_claimed_session_keeps_it(tmp_path: Path) -> None:
    # Como en POST /transcribe (ADR-0059): la sesión reclamada parte de la misma lectura, con la
    # etapa del compás en su procedencia.
    previews = InMemoryPreviewRepository()
    sessions = InMemorySessionRepository()
    image = tmp_path / "minueto.png"
    image.write_bytes(PNG)
    result = create_preview(
        image,
        omr_engine=FakeOMREngine(),
        validator=ValidationEngine(get_default_rules()),
        preview_repository=previews,
        now=NOW,
        ttl=timedelta(hours=1),
        meter_stage=MeterStage({MeterFeature.SYMBOL}),
    )

    claimed = claim_preview(
        result.preview_id,
        result.claim_token,
        preview_repository=previews,
        session_repository=sessions,
        artifact_store=InMemoryArtifactStore(),
        validator=ValidationEngine(get_default_rules()),
        current_user=ANA,
        now=NOW + timedelta(minutes=5),
    )

    session = sessions.get(claimed.session_id)
    assert session is not None
    measures = session.document["score"]["parts"][0]["staves"][0]["measures"]
    assert {m["time_signature"]["symbol"] for m in measures} == {"common"}
    assert session.document["provenance"]["omr_stages"]["meter"]["features"] == ["symbol"]


def test_an_overlapping_retry_of_the_same_account_gets_its_session(tmp_path: Path) -> None:
    """La segunda petición vio la fila, pero la primera la borró antes: si es la misma cuenta
    con el mismo token, recibe la sesión que confirmó la primera (#278)."""
    previews = InMemoryPreviewRepository()
    sessions = InMemorySessionRepository()
    artifacts = InMemoryArtifactStore()
    result = _preview(tmp_path, previews)
    stale = previews.get(result.preview_id)
    assert stale is not None

    def claim(user: User, token: str, repo: InMemoryPreviewRepository) -> Any:
        return claim_preview(
            result.preview_id,
            token,
            preview_repository=repo,
            session_repository=sessions,
            artifact_store=artifacts,
            validator=ValidationEngine([]),
            current_user=user,
            now=NOW,
        )

    first = claim(ANA, result.claim_token, previews)

    class _Overlapping(InMemoryPreviewRepository):
        """Ve la fila que la primera reclamación ya borró."""

        def get(self, preview_id: str) -> PreviewData | None:
            return stale

    assert claim(ANA, result.claim_token, _Overlapping()) == first
    with pytest.raises(PreviewNotFound):
        claim(LUIS, result.claim_token, _Overlapping())
    # Con otro token, ni la misma cuenta llega a la sesión.
    with pytest.raises(PreviewNotFound):
        claim(ANA, "otro-token", previews)
    assert len(sessions.list()) == 1


def test_the_cap_says_when_the_oldest_preview_expires(tmp_path: Path) -> None:
    previews = InMemoryPreviewRepository()
    _preview(tmp_path, previews)

    with pytest.raises(PreviewCapacityExceeded) as excinfo:
        ensure_preview_capacity(previews, now=NOW + timedelta(minutes=10), max_active=1)

    assert excinfo.value.retry_after_seconds == 50 * 60
    assert previews.next_expiry(NOW) == NOW + timedelta(hours=1)
    assert previews.next_expiry(NOW + timedelta(hours=2)) is None


def test_purge_all_deletes_the_valid_ones_too(tmp_path: Path) -> None:
    previews = InMemoryPreviewRepository()
    _preview(tmp_path, previews)
    _preview(tmp_path, previews)

    assert previews.purge_all() == 2
    assert previews.count_active(NOW) == 0
