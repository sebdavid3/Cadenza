"""Cambiar el compás en todas las partes con una sola edición en la API v1 (#326, enmienda de
ADR-0044): `SetTime` con ``"all_parts": true``, ampliación compatible del contrato."""

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
THREE = {"beats": 3, "beat_type": 4}
# Las tres pentagramas: la voz y las dos manos del piano.
STAVES = ((0, 0), (1, 0), (1, 1))


def _staff(part: int, staff: int) -> Staff:
    return Staff(
        id=f"part-{part}-staff-{staff}",
        measures=tuple(
            Measure(
                number=number,
                events=(
                    Event(kind=EventKind.NOTE, pitch="C5", duration_beats=Fraction(3)),
                ),
            )
            for number in (1, 2)
        ),
    )


def _score() -> ScoreIR:
    """Como TS-02 leída por HOMR: la voz y el piano, sin indicación de compás."""

    return ScoreIR(
        parts=(
            Part(id="part-0", staves=(_staff(0, 0),)),
            Part(id="part-1", staves=(_staff(1, 0), _staff(1, 1))),
        )
    )


class _VoiceAndPianoEngine(FakeOMREngine):
    def transcribe(self, image_path: Path) -> ScoreDocument:
        score = _score()
        return ScoreDocument(
            id="doc-voz-y-piano",
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
        omr_engine=_VoiceAndPianoEngine(),
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


def _set_time(
    client: TestClient, headers: dict[str, str], sid: str, after: dict[str, Any], base_seq: int
) -> Any:
    # Desde una nota de la mano izquierda: la parte del ancla no es la de la voz.
    anchor = {
        "part": 1,
        "staff": 1,
        "measure": 1,
        "voice": 0,
        "event_index": 0,
        "staff_id": "part-1-staff-1",
    }
    return client.post(
        f"/sessions/{sid}/edits",
        json={"base_seq": base_seq, "op": "SetTime", "anchor": anchor, "after": after},
        headers=headers,
    )


def _signatures(score: dict[str, Any]) -> list[list[Any]]:
    return [
        [m["time_signature"] for m in score["parts"][part]["staves"][staff]["measures"]]
        for part, staff in STAVES
    ]


def test_one_set_time_puts_the_meter_in_every_part_and_undoes_in_one_step(
    tmp_path: Path,
) -> None:
    client, headers = _client(tmp_path)
    sid = _session(client, headers)
    initial = client.get(f"/sessions/{sid}", headers=headers).json()["current_score"]

    res = _set_time(client, headers, sid, {"time_signature": THREE, "all_parts": True}, 0)
    assert res.status_code == 201, res.text
    assert res.json()["before"] == {
        "time_signature": None,
        "measures": 2,
        "all_parts": True,
        "parts": [{"time_signature": None, "measures": 2}] * 2,
    }
    detail = client.get(f"/sessions/{sid}", headers=headers).json()
    assert detail["current_seq"] == 1
    three = {**THREE, "symbol": None}
    assert _signatures(detail["current_score"]) == [[three, None]] * 3
    export = client.get(f"/sessions/{sid}/export?format=musicxml", headers=headers)
    assert export.text.count("<beats>3</beats>") == 2  # una por parte

    undo = client.post(f"/sessions/{sid}/undo", json={"base_seq": 1}, headers=headers)
    assert undo.status_code == 200, undo.text
    assert undo.json()["current_score"] == initial

    # Rehacer reenvía el `after` original.
    redo = _set_time(client, headers, sid, {"time_signature": THREE, "all_parts": True}, 2)
    assert redo.status_code == 201, redo.text
    detail = client.get(f"/sessions/{sid}", headers=headers).json()
    assert _signatures(detail["current_score"]) == [[three, None]] * 3


def test_without_all_parts_set_time_stays_in_the_part_of_the_anchor(tmp_path: Path) -> None:
    client, headers = _client(tmp_path)
    sid = _session(client, headers)
    res = _set_time(client, headers, sid, {"time_signature": THREE}, 0)
    assert res.status_code == 201, res.text
    assert res.json()["before"] == {"time_signature": None, "measures": 2}
    detail = client.get(f"/sessions/{sid}", headers=headers).json()
    three = {**THREE, "symbol": None}
    assert _signatures(detail["current_score"]) == [[None, None], [three, None], [three, None]]


def test_invalid_all_parts_is_422(tmp_path: Path) -> None:
    client, headers = _client(tmp_path)
    sid = _session(client, headers)
    for after in (
        {"time_signature": THREE, "all_parts": "true"},
        {"time_signature": THREE, "all_parts": True, "parts": []},
    ):
        res = _set_time(client, headers, sid, after, 0)
        assert res.status_code == 422, (after, res.text)
    assert client.get(f"/sessions/{sid}", headers=headers).json()["current_seq"] == 0
