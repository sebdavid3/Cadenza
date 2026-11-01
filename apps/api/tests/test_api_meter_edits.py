"""El compás con su símbolo, cambiar el compás y poner o quitar tresillos en la API v1
(ADR-0044, #236): ampliación compatible del contrato."""

from __future__ import annotations

import secrets
from fractions import Fraction
from pathlib import Path
from typing import Any

from cadenza.api import Settings, create_app
from cadenza.application import Role, User
from cadenza.domain import (
    Event,
    EventKind,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Staff,
    TimeSignature,
    build_anchor_index,
)
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
STAFF_ID = "part-0-staff-0"


def _score() -> ScoreIR:
    common = TimeSignature(4, 4, "common")
    eighths = tuple(
        Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=Fraction(1, 2))
        for pitch in ["C5", "D5", "E5", "F5", "G5", "A5", "B5", "C6", "B5", "A5", "G5", "F5"]
    )
    measures = (
        Measure(number=1, events=eighths, time_signature=common),
        Measure(
            number=2,
            events=(Event(kind=EventKind.NOTE, pitch="E5", duration_beats=Fraction(4)),),
            time_signature=common,
        ),
    )
    return ScoreIR(parts=(Part(id="part-0", staves=(Staff(id=STAFF_ID, measures=measures),)),))


class _TripletEngine(FakeOMREngine):
    """Doble del motor: un compás de C con doce corcheas que eran tresillos."""

    def transcribe(self, image_path: Path) -> ScoreDocument:
        score = _score()
        return ScoreDocument(
            id="doc-tresillos",
            score=score,
            anchors=build_anchor_index(score),
            provenance=Provenance(omr_engine="fake", model_version="fake-1", device="cpu"),
        )


def _client(tmp_path: Path) -> tuple[TestClient, dict[str, str]]:
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
        omr_engine=_TripletEngine(),
        settings=Settings(
            auth_secret_key=secrets.token_urlsafe(48),
            artifacts_dir=tmp_path / "artifacts",
        ),
    )
    token = app.state.token_service.create_access_token(user_id="user-t1", role=Role.TRANSCRIPTOR)
    client = TestClient(app)
    return client, {"Authorization": f"Bearer {token}"}


def _session(client: TestClient, headers: dict[str, str]) -> str:
    res = client.post(
        "/transcribe", files={"file": ("score.png", PNG_BYTES, "image/png")}, headers=headers
    )
    assert res.status_code == 201, res.text
    return str(res.json()["session_id"])


def _anchor(measure: int = 1, event_index: int = 0) -> dict[str, Any]:
    return {
        "part": 0,
        "staff": 0,
        "measure": measure,
        "voice": 0,
        "event_index": event_index,
        "staff_id": STAFF_ID,
    }


def _edit(
    client: TestClient,
    headers: dict[str, str],
    sid: str,
    op: str,
    after: dict[str, Any] | None,
    base_seq: int,
) -> Any:
    return client.post(
        f"/sessions/{sid}/edits",
        json={"base_seq": base_seq, "op": op, "anchor": _anchor(), "after": after},
        headers=headers,
    )


def _measures(client: TestClient, headers: dict[str, str], sid: str) -> list[dict[str, Any]]:
    detail = client.get(f"/sessions/{sid}", headers=headers).json()
    measures: list[dict[str, Any]] = detail["current_score"]["parts"][0]["staves"][0]["measures"]
    return measures


def _musicxml(client: TestClient, headers: dict[str, str], sid: str) -> str:
    res = client.get(f"/sessions/{sid}/export?format=musicxml", headers=headers)
    assert res.status_code == 200, res.text
    return res.text


def test_the_symbol_is_in_the_score_and_in_the_export(tmp_path: Path) -> None:
    client, headers = _client(tmp_path)
    sid = _session(client, headers)
    measures = _measures(client, headers, sid)
    assert measures[0]["time_signature"] == {"beats": 4, "beat_type": 4, "symbol": "common"}
    assert 'symbol="common"' in _musicxml(client, headers, sid)


def test_twelve_eighths_to_triplets_is_one_edit_exported_and_undone(tmp_path: Path) -> None:
    client, headers = _client(tmp_path)
    sid = _session(client, headers)
    initial = client.get(f"/sessions/{sid}", headers=headers).json()["current_score"]

    res = _edit(client, headers, sid, "SetTuplet", {"durations": ["1/3"] * 12}, 0)
    assert res.status_code == 201, res.text
    assert res.json()["before"] == {"durations": ["1/2"] * 12}
    events = _measures(client, headers, sid)[0]["events"]
    assert {event["duration_beats"] for event in events} == {"1/3"}
    xml = _musicxml(client, headers, sid)
    assert xml.count("<time-modification>") == 12
    assert "<actual-notes>3</actual-notes>" in xml

    undo = client.post(f"/sessions/{sid}/undo", json={"base_seq": 1}, headers=headers)
    assert undo.status_code == 200, undo.text
    assert undo.json()["current_score"] == initial


def test_set_time_from_a_measure_and_undo(tmp_path: Path) -> None:
    client, headers = _client(tmp_path)
    sid = _session(client, headers)
    initial = client.get(f"/sessions/{sid}", headers=headers).json()["current_score"]

    res = _edit(
        client, headers, sid, "SetTime", {"time_signature": {"beats": 12, "beat_type": 8}}, 0
    )
    assert res.status_code == 201, res.text
    assert res.json()["before"] == {
        "time_signature": {"beats": 4, "beat_type": 4, "symbol": "common"},
        "measures": 2,
    }
    assert [m["time_signature"] for m in _measures(client, headers, sid)] == [
        {"beats": 12, "beat_type": 8, "symbol": None}
    ] * 2
    assert "<beats>12</beats>" in _musicxml(client, headers, sid)

    undo = client.post(f"/sessions/{sid}/undo", json={"base_seq": 1}, headers=headers)
    assert undo.status_code == 200, undo.text
    assert undo.json()["current_score"] == initial


def test_invalid_meter_edits_are_422_and_stale_ones_409(tmp_path: Path) -> None:
    client, headers = _client(tmp_path)
    sid = _session(client, headers)

    for op, after in (
        ("SetTime", {"time_signature": {"beats": 3, "beat_type": 4, "symbol": "cut"}}),
        ("SetTime", {"time_signature": None}),
        ("SetTuplet", {"durations": ["1/4"] * 12}),
        ("SetTuplet", {"durations": ["1/3"] * 13}),
    ):
        res = _edit(client, headers, sid, op, after, 0)
        assert res.status_code == 422, (op, after, res.text)
    assert client.get(f"/sessions/{sid}", headers=headers).json()["current_seq"] == 0

    ok = _edit(client, headers, sid, "SetTuplet", {"durations": ["1/3"] * 12}, 0)
    assert ok.status_code == 201
    stale = _edit(
        client, headers, sid, "SetTime", {"time_signature": {"beats": 3, "beat_type": 4}}, 0
    )
    assert stale.status_code == 409
