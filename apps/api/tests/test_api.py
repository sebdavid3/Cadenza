"""Flujo E2E: FastAPI → FakeOMREngine → ValidationEngine → SQLite (ADR-0012, #45)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from cadenza.api import Settings, create_app
from cadenza.application import Role, User
from cadenza.domain import ScoreDocument, build_anchor_index
from cadenza.omr import FakeOMREngine, OMREngine
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi.testclient import TestClient

ANCHOR = {
    "part": 0,
    "staff": 0,
    "measure": 1,
    "voice": 0,
    "event_index": 0,
    "staff_id": "part-0-staff-0",
    "bbox": [20.0, 40.0, 36.0, 60.0],
    "confidence": None,
}


class _UnbalancedEngine(OMREngine):
    """Fake con el primer compás desbalanceado para ejercitar la validación."""

    def __init__(self) -> None:
        self._fake = FakeOMREngine()

    @property
    def engine_id(self) -> str:
        return "fake-unbalanced"

    def transcribe(self, image_path: Path) -> ScoreDocument:
        document = self._fake.transcribe(image_path)
        part = document.score.parts[0]
        staff = part.staves[0]
        measures = staff.measures
        broken = replace(measures[0], events=measures[0].events[:-1])
        new_staff = replace(staff, measures=(broken, *measures[1:]))
        score = replace(document.score, parts=(replace(part, staves=(new_staff,)),))
        return replace(document, score=score, anchors=build_anchor_index(score))


def _client(omr_engine: OMREngine | None = None) -> TestClient:
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as db:
        user_repo = SqlAlchemyUserRepository(db)
        user_repo.add(
            User(
                id="default-user",
                username="admin",
                password_hash="test-pass",
                role=Role.INVESTIGADOR,
                active=True,
            )
        )
        db.commit()

    settings = Settings(auth_secret_key="test-jwt-signing-key-minimum-32-bytes-long")
    app = create_app(
        session_factory,
        omr_engine=omr_engine,
        settings=settings,
    )
    token = app.state.token_service.create_access_token(
        user_id="default-user", role=Role.INVESTIGADOR
    )
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
def client() -> Iterator[TestClient]:
    with _client() as test_client:
        yield test_client


def _upload() -> dict[str, tuple[str, bytes, str]]:
    return {"file": ("score.png", b"\x89PNG\r\n\x1a\n", "image/png")}


def test_transcribe_creates_session_without_findings(client: TestClient) -> None:
    response = client.post("/transcribe", files=_upload())
    assert response.status_code == 201
    body = response.json()
    assert body["findings_count"] == 0
    assert body["omr_engine"] == "fake"


def test_transcribe_creates_session_with_findings() -> None:
    with _client(_UnbalancedEngine()) as test_client:
        response = test_client.post("/transcribe", files=_upload())
        assert response.status_code == 201
        body = response.json()
        assert body["findings_count"] == 1
        assert body["omr_engine"] == "fake"

        findings = test_client.get(f"/sessions/{body['session_id']}/findings").json()
        assert len(findings) == 1
        assert findings[0]["rule_id"] == "measure.balance"
        assert findings[0]["severity"] == "error"
        assert findings[0]["at_seq"] == 0


def test_findings_for_unknown_session_returns_404(client: TestClient) -> None:
    assert client.get("/sessions/unknown/findings").status_code == 404


def test_append_edit_is_immutable_append_only(client: TestClient) -> None:
    session_id = client.post("/transcribe", files=_upload()).json()["session_id"]
    payload_first = {
        "op": "SetPitch",
        "anchor": ANCHOR,
        "before": {"pitch": "C4"},
        "after": {"pitch": "D4"},
    }
    payload_second = {
        "op": "SetPitch",
        "anchor": ANCHOR,
        "before": {"pitch": "D4"},
        "after": {"pitch": "E4"},
    }
    first = client.post(f"/sessions/{session_id}/edits", json=payload_first)
    second = client.post(f"/sessions/{session_id}/edits", json=payload_second)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["seq"] == 1
    assert second.json()["seq"] == 2
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["op"] == "SetPitch"
    assert first.json()["author"] == "admin"


def test_append_edit_unknown_session_returns_404(client: TestClient) -> None:
    payload = {"op": "SetPitch", "anchor": ANCHOR}
    assert client.post("/sessions/unknown/edits", json=payload).status_code == 404


def test_get_session_returns_document_anchors_and_findings() -> None:
    with _client(_UnbalancedEngine()) as test_client:
        body = test_client.post("/transcribe", files=_upload()).json()
        response = test_client.get(f"/sessions/{body['session_id']}")
        assert response.status_code == 200
        detail = response.json()
        assert detail["document_id"] == body["document_id"]
        assert detail["omr_engine"] == "fake"

        entries = detail["document"]["anchors"]["entries"]
        assert entries
        assert entries[0]["anchor"]["bbox"] is not None
        assert len(detail["findings"]) == 1
        assert detail["findings"][0]["at_seq"] == 0
        assert detail["edits"] == []
        assert detail["status"] == "transcribed"
        assert detail["model_version"] == "fake-1"
        assert detail["image_artifact"] is not None
        assert len(detail["image_artifact"]) == 64


def test_get_session_includes_appended_edits(client: TestClient) -> None:
    session_id = client.post("/transcribe", files=_upload()).json()["session_id"]
    payload = {"op": "SetPitch", "anchor": ANCHOR}
    client.post(f"/sessions/{session_id}/edits", json=payload)

    detail = client.get(f"/sessions/{session_id}").json()
    assert len(detail["edits"]) == 1
    assert detail["edits"][0]["seq"] == 1
    assert detail["edits"][0]["author"] == "admin"


def test_get_session_unknown_returns_404(client: TestClient) -> None:
    assert client.get("/sessions/unknown").status_code == 404


def test_get_session_materializes_current_score_from_log(client: TestClient) -> None:
    session_id = client.post("/transcribe", files=_upload()).json()["session_id"]
    payload = {
        "op": "SetPitch",
        "anchor": ANCHOR,
        "before": {"pitch": "C4"},
        "after": {"pitch": "F#4"},
    }
    client.post(f"/sessions/{session_id}/edits", json=payload)

    detail = client.get(f"/sessions/{session_id}").json()
    raw = detail["document"]["score"]["parts"][0]["staves"][0]["measures"][0]["events"]
    assert raw[0]["pitch"] == "C4"
    assert (
        detail["current_score"]["parts"][0]["staves"][0]["measures"][0]["events"][0]["pitch"]
        == "F#4"
    )


def test_application_exception_handlers(client: TestClient) -> None:
    session_id = client.post("/transcribe", files=_upload()).json()["session_id"]

    # Edición con op no soportada -> 422
    invalid_edit = {"op": "UnknownOp", "anchor": ANCHOR}
    response = client.post(f"/sessions/{session_id}/edits", json=invalid_edit)
    assert response.status_code == 422


def test_unauthenticated_requests_return_401() -> None:
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)
    settings = Settings(auth_secret_key="test-jwt-signing-key-minimum-32-bytes-long")
    app = create_app(session_factory, settings=settings)
    raw_client = TestClient(app)

    # Peticiones sin header Authorization -> 401
    assert raw_client.post("/transcribe", files=_upload()).status_code == 401
    assert raw_client.get("/sessions/any-id").status_code == 401
    assert raw_client.get("/sessions/any-id/findings").status_code == 401
    assert (
        raw_client.post(
            "/sessions/any-id/edits", json={"op": "SetPitch", "anchor": ANCHOR}
        ).status_code
        == 401
    )


def test_ownership_authorization_rules_in_api() -> None:
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as db:
        user_repo = SqlAlchemyUserRepository(db)
        u1 = user_repo.add(
            User(id="u1", username="transcriptor1", password_hash="h", role=Role.TRANSCRIPTOR)
        )
        u2 = user_repo.add(
            User(id="u2", username="transcriptor2", password_hash="h", role=Role.TRANSCRIPTOR)
        )
        res = user_repo.add(
            User(id="u3", username="investigador1", password_hash="h", role=Role.INVESTIGADOR)
        )
        db.commit()

    settings = Settings(auth_secret_key="test-jwt-signing-key-minimum-32-bytes-long")
    app = create_app(session_factory, settings=settings)
    token_serv = app.state.token_service

    t1_token = token_serv.create_access_token(user_id=u1.id, role=u1.role)
    t2_token = token_serv.create_access_token(user_id=u2.id, role=u2.role)
    res_token = token_serv.create_access_token(user_id=res.id, role=res.role)

    c1 = TestClient(app, headers={"Authorization": f"Bearer {t1_token}"})
    c2 = TestClient(app, headers={"Authorization": f"Bearer {t2_token}"})
    c_res = TestClient(app, headers={"Authorization": f"Bearer {res_token}"})

    # Transcriptor 1 crea una sesión
    sess_id = c1.post("/transcribe", files=_upload()).json()["session_id"]

    # Transcriptor 1 accede a su sesión -> 200
    assert c1.get(f"/sessions/{sess_id}").status_code == 200
    assert c1.get(f"/sessions/{sess_id}/findings").status_code == 200

    # Transcriptor 2 intenta acceder a la sesión de Transcriptor 1 -> 404
    assert c2.get(f"/sessions/{sess_id}").status_code == 404
    assert c2.get(f"/sessions/{sess_id}/findings").status_code == 404
    assert (
        c2.post(f"/sessions/{sess_id}/edits", json={"op": "SetPitch", "anchor": ANCHOR}).status_code
        == 404
    )

    # Investigador intenta leer la sesión de Transcriptor 1 -> 200 permitido
    assert c_res.get(f"/sessions/{sess_id}").status_code == 200
    assert c_res.get(f"/sessions/{sess_id}/findings").status_code == 200

    # Investigador intenta editar la sesión ajena -> 403 Forbidden
    edit_res = c_res.post(f"/sessions/{sess_id}/edits", json={"op": "SetPitch", "anchor": ANCHOR})
    assert edit_res.status_code == 403
    assert "investigador" in edit_res.json()["detail"].lower()
