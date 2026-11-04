"""Varias voces y silencios invisibles en el contrato de la API v1 (ADR-0032, #218).

`ScoreEventPayload.hidden` es una ampliación compatible: opcional y `false` por defecto, también
para un documento guardado antes de #218.
"""

from __future__ import annotations

import secrets
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from cadenza.api import Settings, create_app
from cadenza.application import Role, User
from cadenza.domain import Provenance, ScoreDocument, build_anchor_index
from cadenza.interchange import musicxml_to_score_ir
from cadenza.omr.testing import FakeOMREngine
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi.testclient import TestClient

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
)
# Compás de 4/4: voz 1, un Mi5 redonda; voz 2, `<forward>` de dos negras y después Do5 y Si4.
FORWARD = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "interchange"
    / "tests"
    / "fixtures"
    / "forward_second_voice.musicxml"
)


class _ForwardEngine(FakeOMREngine):
    """Doble del motor que transcribe siempre una segunda voz que entra a mitad del compás."""

    def transcribe(self, image_path: Path) -> ScoreDocument:
        score = musicxml_to_score_ir(FORWARD.read_text(encoding="utf-8"))
        return ScoreDocument(
            id="doc-voces",
            score=score,
            anchors=build_anchor_index(score),
            provenance=Provenance(omr_engine="fake", model_version="fake-1", device="cpu"),
        )


def _client(tmp_path: Path, engine: FakeOMREngine) -> tuple[TestClient, dict[str, str]]:
    database = create_memory_engine()
    create_schema(database)
    session_factory = create_session_factory(database)
    with session_factory() as db:
        SqlAlchemyUserRepository(db).add(
            User(
                id="user-t1",
                username="transcriptor1",
                password_hash=secrets.token_hex(16),
                role=Role.TRANSCRIPTOR,
                active=True,
            )
        )
        db.commit()
    app = create_app(
        session_factory,
        omr_engine=engine,
        settings=Settings(
            auth_secret_key=secrets.token_urlsafe(48),
            artifacts_dir=tmp_path / "artifacts",
        ),
    )
    token = app.state.token_service.create_access_token(user_id="user-t1", role=Role.TRANSCRIPTOR)
    return TestClient(app), {"Authorization": f"Bearer {token}"}


def _transcribe(client: TestClient, headers: dict[str, str]) -> str:
    res = client.post(
        "/transcribe", files={"file": ("score.png", PNG_BYTES, "image/png")}, headers=headers
    )
    assert res.status_code == 201, res.text
    return str(res.json()["session_id"])


def _events(score: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = score["parts"][0]["staves"][0]["measures"][0]["events"]
    return events


def _anchor(event_index: int) -> dict[str, Any]:
    return {
        "part": 0,
        "staff": 0,
        "measure": 1,
        "voice": 1,
        "event_index": event_index,
        "staff_id": "part-0-staff-0",
    }


def test_the_session_has_the_hidden_rest_and_no_false_balance_error(tmp_path: Path) -> None:
    client, headers = _client(tmp_path, _ForwardEngine())
    sid = _transcribe(client, headers)
    detail = client.get(f"/sessions/{sid}", headers=headers).json()

    for score in (detail["document"]["score"], detail["current_score"]):
        assert [(e["voice"], e["kind"], e["pitch"], e["hidden"]) for e in _events(score)] == [
            (0, "note", "E5", False),
            (1, "rest", None, True),
            (1, "note", "C5", False),
            (1, "note", "B4", False),
        ]
    assert detail["findings"] == []

    timing = client.get(f"/sessions/{sid}/timing", headers=headers).json()
    onsets = {
        (t["anchor"]["voice"], t["anchor"]["event_index"]): t["offset_beats"]
        for t in timing["events"]
    }
    assert onsets == {(0, 0): "0", (1, 0): "0", (1, 1): "2", (1, 2): "3"}


def test_a_session_without_hidden_rests_gets_the_default(tmp_path: Path) -> None:
    client, headers = _client(tmp_path, FakeOMREngine())
    sid = _transcribe(client, headers)
    detail = client.get(f"/sessions/{sid}", headers=headers).json()
    for score in (detail["document"]["score"], detail["current_score"]):
        assert all(event["hidden"] is False for event in _events(score))


def test_export_writes_the_hidden_rest_invisible(tmp_path: Path) -> None:
    client, headers = _client(tmp_path, _ForwardEngine())
    sid = _transcribe(client, headers)
    res = client.get(f"/sessions/{sid}/export?format=musicxml", headers=headers)
    assert res.status_code == 200
    hidden = [n for n in ET.fromstring(res.content).iter("note") if n.get("print-object") == "no"]
    assert len(hidden) == 1
    assert hidden[0].find("rest") is not None


def test_deleting_the_hidden_rest_and_undoing_restores_it(tmp_path: Path) -> None:
    client, headers = _client(tmp_path, _ForwardEngine())
    sid = _transcribe(client, headers)
    original = client.get(f"/sessions/{sid}", headers=headers).json()["current_score"]

    deleted = client.post(
        f"/sessions/{sid}/edits",
        json={
            "base_seq": 0,
            "op": "DeleteEvent",
            "anchor": _anchor(0),
            "before": None,
            "after": None,
        },
        headers=headers,
    )
    assert deleted.status_code == 201, deleted.text
    assert deleted.json()["before"]["hidden"] is True

    undone = client.post(f"/sessions/{sid}/undo", json={"base_seq": 1}, headers=headers)
    assert undone.status_code == 200, undone.text
    assert undone.json()["current_score"] == original


def test_insert_event_accepts_a_hidden_rest_and_rejects_a_hidden_note(tmp_path: Path) -> None:
    client, headers = _client(tmp_path, _ForwardEngine())
    sid = _transcribe(client, headers)

    def insert(base_seq: int, after: dict[str, Any]) -> Any:
        return client.post(
            f"/sessions/{sid}/edits",
            json={
                "base_seq": base_seq,
                "op": "InsertEvent",
                "anchor": _anchor(3),
                "before": None,
                "after": after,
            },
            headers=headers,
        )

    assert insert(0, {"kind": "rest", "duration_beats": "1", "hidden": True}).status_code == 201
    rejected = insert(1, {"kind": "note", "pitch": "A4", "duration_beats": "1", "hidden": True})
    assert rejected.status_code == 422
    events = _events(client.get(f"/sessions/{sid}", headers=headers).json()["current_score"])
    assert events[-1] == {**events[-1], "kind": "rest", "voice": 1, "hidden": True}
