"""Transcribir sin cuenta desde la portada y reclamarlo al entrar (#278, ADR-0054).

`POST /previews` transcribe sin sesión y guarda el resultado en su propia tabla, sin dueño,
hasta que caduca; devuelve el MusicXML, el `ScoreIR`, los tiempos, el número de posibles errores
y un token. `POST /previews/{id}/claim`, con sesión, lo convierte en una sesión de quien entra,
una sola vez y sin volver a ejecutar el OMR. Un interruptor apagado por defecto, un límite por
IP, un tope de transcripciones guardadas y ningún hueco de HOMR que no esté libre.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cadenza.api import Settings, create_app
from cadenza.application import Role, User
from cadenza.domain import ScoreDocument
from cadenza.omr import OMRTranscriptionError
from cadenza.omr.testing import FakeOMREngine
from cadenza.persistence import (
    PreviewRecord,
    Session,
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select

SECRET = secrets.token_hex(32)
ORIGIN = "https://cadenza.test"
PNG = b"\x89PNG\r\n\x1a\n" + secrets.token_bytes(64)


class _CountingOMR(FakeOMREngine):
    """El doble de HOMR, contando cuántas veces se le pide transcribir."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

        self.fail_next = False

    def transcribe(self, image_path: Path) -> ScoreDocument:
        self.calls += 1
        if self.fail_next:
            self.fail_next = False
            raise OMRTranscriptionError("no se reconoce ninguna partitura")
        return super().transcribe(image_path)


class Api:
    def __init__(self, **settings: Any) -> None:
        engine = create_memory_engine()
        create_schema(engine)
        self.factory = create_session_factory(engine)
        with self.factory() as db:
            repo = SqlAlchemyUserRepository(db)
            for user_id in ("ana", "luis"):
                repo.add(
                    User(id=user_id, username=user_id, password_hash="-", role=Role.TRANSCRIPTOR)
                )
            db.commit()
        self.omr = _CountingOMR()
        values: dict[str, Any] = {
            "auth_secret_key": SECRET,
            "cors_origins": [ORIGIN],
            "anonymous_preview_enabled": True,
        }
        values.update(settings)
        self.app: FastAPI = create_app(
            self.factory, omr_engine=self.omr, settings=Settings(**values)
        )
        self.now = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
        self.app.state.clock = lambda: self.now
        self.client = TestClient(self.app)

    def token(self, user_id: str) -> str:
        token: str = self.app.state.token_service.create_access_token(
            user_id=user_id, role=Role.TRANSCRIPTOR
        )
        return token

    def preview(self, **form: Any) -> Any:
        return self.client.post(
            "/previews", files={"file": ("minueto.png", PNG, "image/png")}, data=form
        )

    def claim(self, preview_id: str, claim_token: str, user_id: str = "ana") -> Any:
        return self.client.post(
            f"/previews/{preview_id}/claim",
            json={"claim_token": claim_token},
            headers={"Authorization": f"Bearer {self.token(user_id)}"},
        )

    def count(self, model: type[Any]) -> int:
        with self.factory() as db:
            return int(db.scalar(select(func.count()).select_from(model)) or 0)


def test_the_switch_is_off_by_default_and_both_routes_answer_404() -> None:
    assert Settings(auth_secret_key=SECRET).anonymous_preview_enabled is False
    api = Api(anonymous_preview_enabled=False)

    assert api.preview().status_code == 404
    assert api.claim("cualquiera", "token").status_code == 404
    assert api.omr.calls == 0


def test_the_switch_needs_a_closed_cors_like_the_registration() -> None:
    with pytest.raises(ValidationError):
        Settings(auth_secret_key=SECRET, anonymous_preview_enabled=True, cors_origins=["*"])


def test_a_preview_returns_the_score_the_musicxml_the_timing_and_a_token_without_a_session() -> (
    None
):
    api = Api()

    response = api.preview(title="  Minueto ", instruments=["violin"], part_names=[""])

    assert response.status_code == 201
    body = response.json()
    assert body["findings_count"] >= 0
    assert body["claim_token"] and len(body["claim_token"]) >= 40
    assert body["title"] == "Minueto"
    assert body["source_filename"] == "minueto.png"
    assert body["instruments"] == [{"instrument": "violin", "name": None}]
    assert body["musicxml"].lstrip().startswith("<?xml")
    assert body["score"]["parts"]
    assert body["timing"]["events"]
    expires = datetime.fromisoformat(body["expires_at"])
    assert expires == api.now + timedelta(seconds=3600)
    # Nada de sesión ni dueño: solo la fila de la transcripción sin cuenta.
    assert api.count(Session) == 0
    assert api.count(PreviewRecord) == 1
    with api.factory() as db:
        record = db.get(PreviewRecord, body["preview_id"])
        assert record is not None
        assert record.token_hash != body["claim_token"]
        assert record.image == PNG


def test_claiming_creates_a_session_of_the_user_with_the_same_document_and_image() -> None:
    api = Api()
    preview = api.preview(title="Minueto").json()

    response = api.claim(preview["preview_id"], preview["claim_token"])

    assert response.status_code == 201
    claimed = response.json()
    assert claimed["condition"] == "assisted"
    assert claimed["findings_count"] == preview["findings_count"]
    assert api.omr.calls == 1  # el OMR no vuelve a ejecutarse
    headers = {"Authorization": f"Bearer {api.token('ana')}"}
    detail = api.client.get(f"/sessions/{claimed['session_id']}", headers=headers).json()
    assert detail["owner_id"] == "ana"
    assert detail["title"] == "Minueto"
    assert detail["source_filename"] == "minueto.png"
    assert detail["current_score"] == preview["score"]
    image = api.client.get(f"/sessions/{claimed['session_id']}/image", headers=headers)
    assert image.content == PNG
    assert api.count(PreviewRecord) == 0
    # Otra persona no la ve: la sesión es de quien la reclamó (ADR-0012).
    other = {"Authorization": f"Bearer {api.token('luis')}"}
    assert api.client.get(f"/sessions/{claimed['session_id']}", headers=other).status_code == 404


def test_the_token_is_single_use_and_a_wrong_one_answers_like_a_missing_preview() -> None:
    api = Api()
    preview = api.preview().json()

    assert api.claim(preview["preview_id"], "otro-token").status_code == 404
    assert api.claim("no-existe", preview["claim_token"]).status_code == 404
    assert api.claim(preview["preview_id"], preview["claim_token"]).status_code == 201
    again = api.claim(preview["preview_id"], preview["claim_token"], user_id="luis")
    assert again.status_code == 404
    assert api.count(Session) == 1


def test_claiming_needs_a_session() -> None:
    api = Api()
    preview = api.preview().json()

    response = api.client.post(
        f"/previews/{preview['preview_id']}/claim", json={"claim_token": preview["claim_token"]}
    )

    assert response.status_code == 401
    assert api.count(PreviewRecord) == 1


def test_an_expired_preview_cannot_be_claimed_and_is_purged_with_its_image() -> None:
    api = Api(anonymous_preview_ttl_seconds=600)
    preview = api.preview().json()

    api.now += timedelta(seconds=601)
    assert api.claim(preview["preview_id"], preview["claim_token"]).status_code == 404

    # La siguiente transcripción sin cuenta borra las caducadas, imagen incluida.
    assert api.preview().status_code == 201
    with api.factory() as db:
        assert db.get(PreviewRecord, preview["preview_id"]) is None
    assert api.count(PreviewRecord) == 1


def test_the_limit_per_ip_answers_429_with_retry_after() -> None:
    api = Api(anonymous_preview_rate_limit_max_attempts=2)

    assert api.preview().status_code == 201
    assert api.preview().status_code == 201
    limited = api.preview()

    assert limited.status_code == 429
    assert 0 < int(limited.headers["Retry-After"]) <= 3600
    assert api.omr.calls == 2


def test_the_cap_of_stored_previews_answers_503() -> None:
    api = Api(anonymous_preview_max_active=1)

    assert api.preview().status_code == 201
    full = api.preview()

    assert full.status_code == 503
    assert "Retry-After" in full.headers
    assert api.omr.calls == 1


def test_a_preview_does_not_wait_for_a_busy_homr_slot() -> None:
    api = Api(transcribe_max_concurrency=1)
    slots = api.app.state.transcription_slots
    assert slots.semaphore.acquire(blocking=False)
    try:
        busy = api.preview()
    finally:
        slots.semaphore.release()

    assert busy.status_code == 503
    assert busy.headers["Retry-After"] == "10"
    assert api.omr.calls == 0
    # Con el hueco libre vuelve a transcribir: el suyo no quedó ocupado.
    assert api.preview().status_code == 201


def test_only_one_preview_runs_at_a_time() -> None:
    api = Api(transcribe_max_concurrency=2)
    gate = api.app.state.preview_gate
    assert gate.acquire(blocking=False)
    try:
        busy = api.preview()
    finally:
        gate.release()

    assert busy.status_code == 503
    assert api.omr.calls == 0


def test_size_and_type_are_checked_like_the_transcription() -> None:
    api = Api(max_upload_size_bytes=32)
    too_big = api.client.post("/previews", files={"file": ("a.png", PNG, "image/png")})
    assert too_big.status_code == 413

    api = Api()
    not_image = api.client.post("/previews", files={"file": ("a.png", b"hola mundo", "image/png")})
    assert not_image.status_code == 415
    pdf = api.client.post("/previews", files={"file": ("a.pdf", PNG, "application/pdf")})
    assert pdf.status_code == 415
    assert api.omr.calls == 0


def test_invalid_metadata_answers_422_before_transcribing() -> None:
    api = Api()

    response = api.preview(instruments=["tuba"])

    assert response.status_code == 422
    assert api.omr.calls == 0


def test_a_failed_transcription_releases_the_preview_slot() -> None:
    api = Api()
    api.omr.fail_next = True

    failed = api.preview()

    assert failed.status_code == 422
    assert api.count(PreviewRecord) == 0
    # El semáforo de lo transcrito sin cuenta quedó libre: la siguiente se transcribe.
    assert api.preview().status_code == 201


def test_switching_off_also_closes_the_claim_of_a_stored_preview() -> None:
    api = Api()
    preview = api.preview().json()

    api.app.state.settings = api.app.state.settings.model_copy(
        update={"anonymous_preview_enabled": False}
    )

    assert api.claim(preview["preview_id"], preview["claim_token"]).status_code == 404
    assert api.count(Session) == 0


def test_expired_previews_are_purged_when_the_api_starts() -> None:
    api = Api(anonymous_preview_ttl_seconds=60)
    # Transcrita hace dos horas: con el reloj real, al arrancar ya está caducada.
    api.now = datetime.now(UTC) - timedelta(hours=2)
    api.preview()
    assert api.count(PreviewRecord) == 1

    # Otra API sobre la misma base (el reinicio tras apagar el interruptor) las borra al arrancar.
    create_app(
        api.factory,
        omr_engine=api.omr,
        settings=Settings(auth_secret_key=SECRET, cors_origins=[ORIGIN]),
    )

    assert api.count(PreviewRecord) == 0
