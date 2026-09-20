"""Flujo E2E: FastAPI → FakeOMREngine → ValidationEngine → SQLite."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from cadenza.api import create_app
from cadenza.domain import ScoreDocument, build_anchor_index
from cadenza.omr import FakeOMREngine, OMREngine
from cadenza.persistence import create_memory_engine, create_schema, create_session_factory
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
    app = create_app(create_session_factory(engine), omr_engine=omr_engine)
    return TestClient(app)


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

    findings = client.get(f"/sessions/{body['session_id']}/findings")
    assert findings.status_code == 200
    assert findings.json() == []


def test_transcribe_persists_findings_e2e() -> None:
    with _client(_UnbalancedEngine()) as test_client:
        body = test_client.post("/transcribe", files=_upload()).json()
        assert body["findings_count"] == 1

        findings = test_client.get(f"/sessions/{body['session_id']}/findings").json()
        assert len(findings) == 1
        assert findings[0]["rule_id"] == "measure.balance"
        assert findings[0]["severity"] == "error"
        assert findings[0]["anchor"]["measure"] == 1
        assert findings[0]["anchor"]["bbox"] is not None


def test_findings_for_unknown_session_returns_404(client: TestClient) -> None:
    assert client.get("/sessions/unknown/findings").status_code == 404


def test_append_edit_is_immutable_append_only(client: TestClient) -> None:
    session_id = client.post("/transcribe", files=_upload()).json()["session_id"]
    payload = {
        "op": "SetPitch",
        "anchor": ANCHOR,
        "author": "tester",
        "before": {"pitch": "C4"},
        "after": {"pitch": "D4"},
    }
    first = client.post(f"/sessions/{session_id}/edits", json=payload)
    second = client.post(f"/sessions/{session_id}/edits", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["seq"] == 1
    assert second.json()["seq"] == 2
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["op"] == "SetPitch"


def test_append_edit_unknown_session_returns_404(client: TestClient) -> None:
    payload = {"op": "SetPitch", "anchor": ANCHOR, "author": "tester"}
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
        assert detail["edits"] == []


def test_get_session_includes_appended_edits(client: TestClient) -> None:
    session_id = client.post("/transcribe", files=_upload()).json()["session_id"]
    payload = {"op": "SetPitch", "anchor": ANCHOR, "author": "tester"}
    client.post(f"/sessions/{session_id}/edits", json=payload)

    detail = client.get(f"/sessions/{session_id}").json()
    assert len(detail["edits"]) == 1
    assert detail["edits"][0]["seq"] == 1


def test_get_session_unknown_returns_404(client: TestClient) -> None:
    assert client.get("/sessions/unknown").status_code == 404
