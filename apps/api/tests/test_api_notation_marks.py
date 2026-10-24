"""Marcas de notación en el contrato de la API v1 (ADR-0031, #213).

Los campos nuevos de `ScoreEventPayload` y `MeasurePayload` son una ampliación compatible:
opcionales y con valor por defecto, también para un documento guardado antes de #213.
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
MARKS_PIANO = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "interchange"
    / "tests"
    / "fixtures"
    / "marks_piano.musicxml"
)


class _MarkedEngine(FakeOMREngine):
    """Doble del motor que transcribe siempre la fixture de piano con todas las marcas."""

    def transcribe(self, image_path: Path) -> ScoreDocument:
        score = musicxml_to_score_ir(MARKS_PIANO.read_text(encoding="utf-8"))
        return ScoreDocument(
            id="doc-marcas",
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
                password_hash="hash1",
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


def _measures(score: dict[str, Any], staff: int) -> list[dict[str, Any]]:
    measures: list[dict[str, Any]] = score["parts"][0]["staves"][staff]["measures"]
    return measures


def _anchor(staff: int, measure: int, event_index: int) -> dict[str, Any]:
    return {
        "part": 0,
        "staff": staff,
        "measure": measure,
        "voice": 0,
        "event_index": event_index,
        "staff_id": f"part-0-staff-{staff}",
    }


def test_session_detail_returns_the_marks(tmp_path: Path) -> None:
    client, headers = _client(tmp_path, _MarkedEngine())
    sid = _transcribe(client, headers)
    detail = client.get(f"/sessions/{sid}", headers=headers).json()

    for score in (detail["document"]["score"], detail["current_score"]):
        right_hand = _measures(score, 0)
        first = right_hand[0]["events"][0]
        assert first["articulations"] == ["staccato"]
        assert first["fermata"] is False
        assert first["slurs"] == [{"type": "start", "number": 1}]
        assert right_hand[0]["events"][3]["fermata"] is True
        assert right_hand[1]["dynamics"] == [
            {"mark": "mf", "offset_beats": "0"},
            {"mark": "sfz", "offset_beats": "2"},
        ]
        left_hand = _measures(score, 1)
        assert left_hand[0]["events"][0]["articulations"] == ["marcato"]
        assert left_hand[0]["wedges"] == [
            {"type": "crescendo", "number": 1, "offset_beats": "0"},
            {"type": "stop", "number": 1, "offset_beats": "2"},
        ]
        # Sin marcas, los campos salen con su valor por defecto.
        assert left_hand[1]["events"][0]["articulations"] == []
        assert left_hand[1]["events"][0]["slurs"] == []
        assert right_hand[2]["wedges"] == []


def test_session_without_marks_gets_the_defaults(tmp_path: Path) -> None:
    """Un documento sin los campos nuevos (como los guardados antes de #213) se lee igual."""

    client, headers = _client(tmp_path, FakeOMREngine())
    sid = _transcribe(client, headers)
    detail = client.get(f"/sessions/{sid}", headers=headers).json()
    for score in (detail["document"]["score"], detail["current_score"]):
        for measure in _measures(score, 0):
            assert measure["dynamics"] == []
            assert measure["wedges"] == []
            for event in measure["events"]:
                assert event["articulations"] == []
                assert event["fermata"] is False
                assert event["slurs"] == []


def test_export_writes_the_marks(tmp_path: Path) -> None:
    client, headers = _client(tmp_path, _MarkedEngine())
    sid = _transcribe(client, headers)
    res = client.get(f"/sessions/{sid}/export?format=musicxml", headers=headers)
    assert res.status_code == 200
    root = ET.fromstring(res.content)
    tags = {element.tag for element in root.iter()}
    assert {"staccato", "staccatissimo", "accent", "strong-accent", "tenuto"} <= tags
    assert {"fermata", "slur", "wedge", "dynamics"} <= tags


def test_deleting_a_marked_note_and_undoing_restores_it(tmp_path: Path) -> None:
    client, headers = _client(tmp_path, _MarkedEngine())
    sid = _transcribe(client, headers)
    original = client.get(f"/sessions/{sid}", headers=headers).json()["current_score"]

    deleted = client.post(
        f"/sessions/{sid}/edits",
        json={
            "base_seq": 0,
            "op": "DeleteEvent",
            "anchor": _anchor(0, 1, 3),
            "before": None,
            "after": None,
        },
        headers=headers,
    )
    assert deleted.status_code == 201, deleted.text
    assert deleted.json()["before"]["fermata"] is True
    assert deleted.json()["before"]["slurs"] == [
        {"type": "stop", "number": 1},
        {"type": "start", "number": 2},
    ]

    undone = client.post(f"/sessions/{sid}/undo", json={"base_seq": 1}, headers=headers)
    assert undone.status_code == 200, undone.text
    assert undone.json()["current_score"] == original
    assert client.get(f"/sessions/{sid}", headers=headers).json()["current_score"] == original


def test_insert_event_accepts_marks_and_rejects_invalid_ones(tmp_path: Path) -> None:
    client, headers = _client(tmp_path, _MarkedEngine())
    sid = _transcribe(client, headers)

    def insert(base_seq: int, marks: dict[str, Any]) -> Any:
        return client.post(
            f"/sessions/{sid}/edits",
            json={
                "base_seq": base_seq,
                "op": "InsertEvent",
                "anchor": _anchor(0, 3, 0),
                "before": None,
                "after": {"kind": "note", "pitch": "E5", "duration_beats": "1", **marks},
            },
            headers=headers,
        )

    assert insert(0, {"articulations": ["staccato"], "fermata": True}).status_code == 201
    assert insert(1, {"articulations": ["trill"]}).status_code == 422
    assert insert(1, {"slurs": [{"type": "start", "number": 0}]}).status_code == 422
    events = _measures(client.get(f"/sessions/{sid}", headers=headers).json()["current_score"], 0)
    assert events[2]["events"][0]["articulations"] == ["staccato"]
    assert events[2]["events"][0]["fermata"] is True
