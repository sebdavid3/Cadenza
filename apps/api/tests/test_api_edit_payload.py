"""`POST /sessions/{id}/edits` ante `after` inválido y `before` ausente (#117, ADR-0017).

Reproduce contra la API los casos detectados el 2026-10-13: ediciones con `after` sin
sentido respondían 201 y quedaban en el log (una altura `H9` dejaba la exportación en
500), y deshacer una edición enviada con `before: null` corrompía la sesión.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from cadenza.api import Settings, create_app
from cadenza.application import Role, User
from cadenza.omr import FakeOMREngine
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


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as db:
        SqlAlchemyUserRepository(db).add(
            User(id="u1", username="transcriptor1", password_hash="x", role=Role.TRANSCRIPTOR)
        )
        db.commit()
    app = create_app(
        session_factory,
        omr_engine=FakeOMREngine(),
        settings=Settings(
            auth_secret_key="secret-key-at-least-32-bytes-long-for-testing",
            artifacts_dir=tmp_path / "artifacts",
        ),
    )
    token = app.state.token_service.create_access_token(user_id="u1", role=Role.TRANSCRIPTOR)
    test_client = TestClient(app)
    test_client.headers["Authorization"] = f"Bearer {token}"
    return test_client


def _new_session(client: TestClient) -> tuple[str, dict[str, Any]]:
    response = client.post("/transcribe", files={"file": ("score.png", PNG_BYTES, "image/png")})
    assert response.status_code == 201
    session_id = response.json()["session_id"]
    detail = client.get(f"/sessions/{session_id}").json()
    return session_id, detail


def _anchor(detail: dict[str, Any], measure: int = 1, event_index: int = 0) -> dict[str, Any]:
    """Ancla real del índice; para insertar al final de la voz, la posición siguiente."""

    same_measure = [
        dict(entry["anchor"])
        for entry in detail["anchor_index"]["entries"]
        if entry["anchor"]["measure"] == measure
    ]
    for anchor in same_measure:
        if anchor["event_index"] == event_index:
            return anchor
    if event_index == len(same_measure):
        return {**same_measure[0], "event_index": event_index, "bbox": None, "confidence": None}
    raise AssertionError(f"sin ancla en el compás {measure}, evento {event_index}")


def _assert_exportable(client: TestClient, session_id: str) -> None:
    for fmt in ("musicxml", "midi"):
        response = client.get(f"/sessions/{session_id}/export", params={"format": fmt})
        assert response.status_code == 200, (fmt, response.text)


@pytest.mark.parametrize(
    ("op", "after"),
    [
        ("SetPitch", {}),
        ("SetPitch", None),
        ("SetPitch", {"pitch": "H9"}),
        ("SetDuration", {}),
    ],
)
def test_invalid_after_is_rejected_and_nothing_is_persisted(
    client: TestClient, op: str, after: dict[str, Any] | None
) -> None:
    session_id, detail = _new_session(client)
    response = client.post(
        f"/sessions/{session_id}/edits",
        json={"base_seq": 0, "op": op, "anchor": _anchor(detail), "before": None, "after": after},
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert "after" in response.json()["detail"]
    after_detail = client.get(f"/sessions/{session_id}").json()
    assert after_detail["edits"] == []
    assert after_detail["status"] == "transcribed"
    _assert_exportable(client, session_id)


@pytest.mark.parametrize(
    ("op", "after"),
    [
        ("SetDuration", {"duration_beats": "1e30"}),
        ("SetDuration", {"duration_beats": 10**400}),
        ("SetDuration", {"duration_beats": "3/1000"}),
        ("SetKey", {"fifths": 1, "mode": []}),
        ("SetClef", {"sign": {}}),
        ("SetClef", {"clef": {"sign": ["G"]}}),
        ("InsertEvent", {"kind": "note", "pitch": "C4", "duration_beats": 1, "tie": []}),
        (
            "InsertEvent",
            {"kind": "note", "pitch": "C4", "duration_beats": 1, "bbox": [10**400, 0, 1, 1]},
        ),
        ("InsertEvent", {"kind": "rest", "duration_beats": 100000}),
    ],
)
def test_unexpected_json_values_return_422_not_500(
    client: TestClient, op: str, after: dict[str, Any]
) -> None:
    session_id, detail = _new_session(client)
    response = client.post(
        f"/sessions/{session_id}/edits",
        json={"base_seq": 0, "op": op, "anchor": _anchor(detail), "before": None, "after": after},
    )
    assert response.status_code == 422, response.text
    assert client.get(f"/sessions/{session_id}").json()["edits"] == []
    _assert_exportable(client, session_id)


def test_unusable_before_returns_422_not_500(client: TestClient) -> None:
    session_id, detail = _new_session(client)
    response = client.post(
        f"/sessions/{session_id}/edits",
        json={
            "base_seq": 0,
            "op": "SetDuration",
            "anchor": _anchor(detail),
            "before": {"duration_beats": "abc"},
            "after": {"duration_beats": "2"},
        },
    )
    assert response.status_code == 422
    assert "before" in response.json()["detail"]


VALID_EDITS: list[tuple[str, int, int, dict[str, Any] | None]] = [
    ("SetPitch", 1, 0, {"pitch": "Bb3"}),
    ("SetDuration", 1, 2, {"duration_beats": "1/2"}),
    ("SetAccidental", 1, 1, {"accidental": "#"}),
    ("InsertEvent", 2, 1, {"kind": "rest", "duration_beats": "1"}),
    ("InsertEvent", 1, 0, {"kind": "note", "pitch": "G4", "duration_beats": "1/2"}),
    ("DeleteEvent", 1, 0, None),
    ("SetClef", 1, 0, {"sign": "F", "line": 4}),
    ("SetKey", 2, 0, {"fifths": -3, "mode": "minor"}),
]


@pytest.mark.parametrize(("op", "measure", "event_index", "after"), VALID_EDITS)
def test_accepted_edit_keeps_session_exportable_and_undo_restores_it(
    client: TestClient,
    op: str,
    measure: int,
    event_index: int,
    after: dict[str, Any] | None,
) -> None:
    session_id, detail = _new_session(client)
    original_score = detail["current_score"]
    response = client.post(
        f"/sessions/{session_id}/edits",
        json={
            "base_seq": 0,
            "op": op,
            "anchor": _anchor(detail, measure, event_index),
            "before": None,
            "after": after,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["before"] is not None or op == "InsertEvent"
    _assert_exportable(client, session_id)

    undo = client.post(f"/sessions/{session_id}/undo", json={"base_seq": 1})
    assert undo.status_code == 200, undo.text
    assert undo.json()["current_score"] == original_score
    _assert_exportable(client, session_id)
