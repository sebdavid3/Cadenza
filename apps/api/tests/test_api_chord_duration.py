"""Cambiar la figura de un acorde entero en la API v1 (ADR-0049, #243, D61): ampliación
compatible del contrato con `SetChordDuration`."""

from __future__ import annotations

import re
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


def _note(pitch: str, beats: int, is_chord: bool = False) -> Event:
    return Event(
        kind=EventKind.NOTE, pitch=pitch, duration_beats=Fraction(beats), is_chord=is_chord
    )


def _score() -> ScoreIR:
    # 4/4: un acorde de Do mayor en blancas y una blanca. El acorde era de negras.
    events = (_note("C4", 2), _note("E4", 2, True), _note("G4", 2, True), _note("D4", 2))
    measure = Measure(number=1, events=events, time_signature=TimeSignature(4, 4))
    return ScoreIR(parts=(Part(id="part-0", staves=(Staff(id=STAFF_ID, measures=(measure,)),)),))


class _ChordEngine(FakeOMREngine):
    """Doble del motor: un compás con un acorde de tres notas."""

    def transcribe(self, image_path: Path) -> ScoreDocument:
        score = _score()
        return ScoreDocument(
            id="doc-acorde",
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
        omr_engine=_ChordEngine(),
        settings=Settings(
            auth_secret_key=secrets.token_urlsafe(48),
            artifacts_dir=tmp_path / "artifacts",
        ),
    )
    token = app.state.token_service.create_access_token(user_id="user-t1", role=Role.TRANSCRIPTOR)
    return TestClient(app), {"Authorization": f"Bearer {token}"}


def _session(client: TestClient, headers: dict[str, str]) -> str:
    res = client.post(
        "/transcribe", files={"file": ("score.png", PNG_BYTES, "image/png")}, headers=headers
    )
    assert res.status_code == 201, res.text
    return str(res.json()["session_id"])


def _anchor(event_index: int = 0) -> dict[str, Any]:
    return {
        "part": 0,
        "staff": 0,
        "measure": 1,
        "voice": 0,
        "event_index": event_index,
        "staff_id": STAFF_ID,
    }


def _edit(
    client: TestClient,
    headers: dict[str, str],
    sid: str,
    after: dict[str, Any] | None,
    base_seq: int = 0,
    event_index: int = 0,
) -> Any:
    return client.post(
        f"/sessions/{sid}/edits",
        json={
            "base_seq": base_seq,
            "op": "SetChordDuration",
            "anchor": _anchor(event_index),
            "after": after,
        },
        headers=headers,
    )


def _note_types(xml: str) -> list[tuple[bool, str]]:
    """Cada `<note>` del MusicXML: si lleva `<chord/>` y su `<type>`."""
    notes = re.findall(r"<note\b.*?</note>", xml, flags=re.DOTALL)
    return [
        (re.search(r"<chord\s*/>", note) is not None, re.findall(r"<type>(\w+)</type>", note)[0])
        for note in notes
    ]


def test_the_chord_figure_is_one_edit_with_timing_export_and_undo(tmp_path: Path) -> None:
    client, headers = _client(tmp_path)
    sid = _session(client, headers)
    initial = client.get(f"/sessions/{sid}", headers=headers).json()["current_score"]

    res = _edit(client, headers, sid, {"durations": ["1", "1", "1"]})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["op"] == "SetChordDuration"
    assert body["before"] == {"durations": ["2", "2", "2"]}
    events = body["current_score"]["parts"][0]["staves"][0]["measures"][0]["events"]
    assert [e["duration_beats"] for e in events] == ["1", "1", "1", "2"]
    # El 201 trae el mapa de tiempos nuevo (ADR-0037), el mismo que da /timing.
    timing = client.get(f"/sessions/{sid}/timing", headers=headers).json()
    assert body["timing"] == timing
    by_index = {t["anchor"]["event_index"]: t for t in timing["events"]}
    assert [by_index[i]["offset_beats"] for i in range(4)] == ["0", "0", "0", "1"]
    assert [by_index[i]["duration_beats"] for i in range(4)] == ["1", "1", "1", "2"]

    export = client.get(f"/sessions/{sid}/export?format=musicxml", headers=headers)
    assert export.status_code == 200, export.text
    assert _note_types(export.text)[:4] == [
        (False, "quarter"),
        (True, "quarter"),
        (True, "quarter"),
        (False, "half"),
    ]

    undo = client.post(f"/sessions/{sid}/undo", json={"base_seq": 1}, headers=headers)
    assert undo.status_code == 200, undo.text
    assert undo.json()["current_score"] == initial


def test_invalid_chord_edits_are_422_and_stale_ones_409(tmp_path: Path) -> None:
    client, headers = _client(tmp_path)
    sid = _session(client, headers)

    for after, event_index in (
        ({"durations": ["1"] * 2}, 0),
        ({"durations": ["1", "1", "1/2"]}, 0),
        ({"durations": ["1"] * 2}, 1),
        ({"durations": ["1"]}, 3),
        ({"duration_beats": "1"}, 0),
        (None, 0),
    ):
        res = _edit(client, headers, sid, after, event_index=event_index)
        assert res.status_code == 422, (after, event_index, res.text)
    assert client.get(f"/sessions/{sid}", headers=headers).json()["current_seq"] == 0

    assert _edit(client, headers, sid, {"durations": ["1"] * 3}).status_code == 201
    assert _edit(client, headers, sid, {"durations": ["4"] * 3}).status_code == 409
