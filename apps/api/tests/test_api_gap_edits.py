"""Los huecos de una voz en la API v1 (ADR-0058, #317): `SetEventKind` escribe una nota en un hueco
(un silencio invisible, ADR-0032) o lo hace visible, y `DeleteEvent` lo borra, con el estado nuevo
en el 201, la exportación y deshacer."""

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


def _note(pitch: str, beats: str, voice: int = 0) -> Event:
    return Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=Fraction(beats), voice=voice)


def _gap(beats: str, voice: int = 0) -> Event:
    return Event(kind=EventKind.REST, duration_beats=Fraction(beats), hidden=True, voice=voice)


def _score() -> ScoreIR:
    # 6/8. Compás 1, la voz de TS-03 como la importa HOMR: un hueco donde va el Fa#4 y otro que
    # sobra. Compás 2: una voz completa y otra que empieza con un hueco de negra.
    first = (
        _note("G#4", "3/4"),
        _gap("1/4"),
        _note("F#4", "1/2"),
        _note("D5", "3/4"),
        _gap("1/4"),
        _note("G#4", "1/4"),
        _note("G#4", "1/2"),
    )
    second = (
        _note("C#4", "1/2"),
        _note("E4", "1/2"),
        _note("C#5", "1/2"),
        _note("A4", "3/2"),
        _gap("1", voice=1),
        _note("E4", "1/2", voice=1),
    )
    measures = (
        Measure(number=1, events=first, time_signature=TimeSignature(6, 8)),
        Measure(number=2, events=second),
    )
    return ScoreIR(parts=(Part(id="part-0", staves=(Staff(id=STAFF_ID, measures=measures),)),))


class _Engine(FakeOMREngine):
    """Doble del motor: la voz de TS-03 con sus huecos."""

    def transcribe(self, image_path: Path) -> ScoreDocument:
        score = _score()
        return ScoreDocument(
            id="doc-huecos",
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
        omr_engine=_Engine(),
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


def _anchor(event_index: int, measure: int = 1, voice: int = 0) -> dict[str, Any]:
    return {
        "part": 0,
        "staff": 0,
        "measure": measure,
        "voice": voice,
        "event_index": event_index,
        "staff_id": STAFF_ID,
    }


def _edit(
    client: TestClient,
    headers: dict[str, str],
    sid: str,
    op: str,
    anchor: dict[str, Any],
    after: dict[str, Any] | None,
    base_seq: int = 0,
) -> Any:
    return client.post(
        f"/sessions/{sid}/edits",
        json={"base_seq": base_seq, "op": op, "anchor": anchor, "after": after},
        headers=headers,
    )


def _events(body: dict[str, Any], measure: int = 1) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = body["current_score"]["parts"][0]["staves"][0]["measures"][
        measure - 1
    ]["events"]
    return events


def _measure_xml(xml: str, number: int) -> str:
    found = re.search(rf'<measure[^>]*number="{number}".*?</measure>', xml, flags=re.DOTALL)
    assert found is not None
    return found.group(0)


def _initial(client: TestClient, headers: dict[str, str], sid: str) -> Any:
    return client.get(f"/sessions/{sid}", headers=headers).json()["current_score"]


GAP = {"kind": "rest", "pitch": None, "hidden": True}


def test_a_note_in_a_gap_and_a_deleted_gap_correct_the_voice(tmp_path: Path) -> None:
    client, headers = _client(tmp_path)
    sid = _session(client, headers)
    initial = _initial(client, headers, sid)
    hidden_before = _measure_xml(
        client.get(f"/sessions/{sid}/export?format=musicxml", headers=headers).text, 1
    ).count('print-object="no"')
    assert hidden_before == 2

    note = {"kind": "note", "pitch": "F#4", "hidden": False}
    res = _edit(client, headers, sid, "SetEventKind", _anchor(1), note)
    assert res.status_code == 201, res.text
    body = res.json()
    assert (body["op"], body["before"], body["after"]) == ("SetEventKind", GAP, note)
    filled = _events(body)[1]
    assert (filled["kind"], filled["pitch"], filled["duration_beats"]) == ("note", "F#4", "1/4")
    assert "hidden" not in filled or filled["hidden"] is False

    res = _edit(client, headers, sid, "DeleteEvent", _anchor(4), None, 1)
    assert res.status_code == 201, res.text
    assert res.json()["before"]["hidden"] is True
    pitches = [(e["pitch"], e["duration_beats"]) for e in _events(res.json())]
    assert pitches == [
        ("G#4", "3/4"),
        ("F#4", "1/4"),
        ("F#4", "1/2"),
        ("D5", "3/4"),
        ("G#4", "1/4"),
        ("G#4", "1/2"),
    ]

    # El compás exportado ya no tiene silencios invisibles: el Fa#4 se dibuja y suena.
    export = client.get(f"/sessions/{sid}/export?format=musicxml", headers=headers)
    assert export.status_code == 200, export.text
    first = _measure_xml(export.text, 1)
    assert 'print-object="no"' not in first
    assert first.count("<step>F</step>") == 2

    # Deshacer los dos pasos devuelve los dos huecos.
    undo = client.post(f"/sessions/{sid}/undo", json={"base_seq": 2}, headers=headers)
    assert undo.status_code == 200, undo.text
    undo = client.post(f"/sessions/{sid}/undo", json={"base_seq": 3}, headers=headers)
    assert undo.status_code == 200, undo.text
    assert undo.json()["current_score"] == initial


def test_a_voice_that_starts_with_a_gap_is_written_from_it(tmp_path: Path) -> None:
    client, headers = _client(tmp_path)
    sid = _session(client, headers)
    shown = {"kind": "rest", "pitch": None, "hidden": False}
    res = _edit(client, headers, sid, "SetEventKind", _anchor(0, 2, voice=1), shown)
    assert res.status_code == 201, res.text
    lower = [e for e in _events(res.json(), 2) if e["voice"] == 1]
    assert [(e["kind"], e.get("hidden", False)) for e in lower] == [
        ("rest", False),
        ("note", False),
    ]
    note = {"kind": "note", "pitch": "C#4", "hidden": False}
    res = _edit(client, headers, sid, "SetEventKind", _anchor(0, 2, voice=1), note, 1)
    # Ya no es un hueco: un silencio que se ve se corrige con las demás operaciones.
    assert res.status_code == 422, res.text


def test_invalid_gap_edits_are_422(tmp_path: Path) -> None:
    client, headers = _client(tmp_path)
    sid = _session(client, headers)
    cases: list[tuple[dict[str, Any], dict[str, Any] | None]] = [
        (_anchor(0), {"kind": "rest", "pitch": None, "hidden": False}),
        (_anchor(1), GAP),
        (_anchor(1), {"kind": "note", "pitch": "F#4"}),
        (_anchor(1), {"kind": "note", "pitch": "F#4", "hidden": True}),
        (_anchor(1), {"kind": "rest", "pitch": "F#4", "hidden": False}),
        (_anchor(1), None),
        (_anchor(9), {"kind": "note", "pitch": "F#4", "hidden": False}),
    ]
    for anchor, after in cases:
        res = _edit(client, headers, sid, "SetEventKind", anchor, after)
        assert res.status_code == 422, (anchor, after, res.text)
    assert client.get(f"/sessions/{sid}", headers=headers).json()["current_seq"] == 0
