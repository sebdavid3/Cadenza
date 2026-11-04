"""Ligaduras de prolongación y notas de un acorde en la API v1 (ADR-0055, #312, D61): `SetTie`,
`InsertEvent` con `is_chord` y `DeleteEvent` con `{"keep_chord": true}`, con el estado nuevo en
el 201, la exportación, el mapa de tiempos y deshacer."""

from __future__ import annotations

import re
import secrets
from fractions import Fraction
from pathlib import Path
from typing import Any

from cadenza.api import Settings, create_app
from cadenza.application import Role, User
from cadenza.domain import (
    Articulation,
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


def _note(pitch: str, beats: int, **kwargs: Any) -> Event:
    return Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=Fraction(beats), **kwargs)


def _score() -> ScoreIR:
    # 4/4: un acorde de Do mayor en negras con acento, un Re negra y un Sol blanca; después un
    # Sol redonda.
    first = (
        _note("C4", 1, articulations=(Articulation.ACCENT,)),
        _note("E4", 1, is_chord=True),
        _note("G4", 1, is_chord=True),
        _note("D4", 1),
        _note("G4", 2),
    )
    measures = (
        Measure(number=1, events=first, time_signature=TimeSignature(4, 4)),
        Measure(number=2, events=(_note("G4", 4),)),
    )
    return ScoreIR(parts=(Part(id="part-0", staves=(Staff(id=STAFF_ID, measures=measures),)),))


class _Engine(FakeOMREngine):
    """Doble del motor: dos compases con un acorde y dos Sol seguidos a través de la barra."""

    def transcribe(self, image_path: Path) -> ScoreDocument:
        score = _score()
        return ScoreDocument(
            id="doc-ligadura",
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


def _anchor(event_index: int, measure: int = 1) -> dict[str, Any]:
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


def _notes(xml: str) -> list[str]:
    return re.findall(r"<note\b.*?</note>", xml, flags=re.DOTALL)


def _undo_restores(
    client: TestClient, headers: dict[str, str], sid: str, seq: int, initial: Any
) -> None:
    undo = client.post(f"/sessions/{sid}/undo", json={"base_seq": seq}, headers=headers)
    assert undo.status_code == 200, undo.text
    assert undo.json()["current_score"] == initial


def _initial(client: TestClient, headers: dict[str, str], sid: str) -> Any:
    return client.get(f"/sessions/{sid}", headers=headers).json()["current_score"]


ACROSS: dict[str, Any] = {
    "tie": "start",
    "next": {"measure": 2, "voice": 0, "event_index": 0, "tie": "stop"},
}


def test_a_tie_across_the_barline_is_exported_and_undone(tmp_path: Path) -> None:
    client, headers = _client(tmp_path)
    sid = _session(client, headers)
    initial = _initial(client, headers, sid)

    res = _edit(client, headers, sid, "SetTie", _anchor(4), ACROSS)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["op"] == "SetTie"
    assert body["before"] == {
        "tie": None,
        "next": {"measure": 2, "voice": 0, "event_index": 0, "tie": None},
    }
    assert _events(body, 1)[4]["tie"] == "start"
    assert _events(body, 2)[0]["tie"] == "stop"
    # El mapa de tiempos no cambia: la ligadura une el sonido en la reproducción, no los eventos.
    assert body["timing"] is None

    export = client.get(f"/sessions/{sid}/export?format=musicxml", headers=headers)
    assert export.status_code == 200, export.text
    notes = _notes(export.text)
    assert '<tie type="start"' in notes[4] and '<tie type="stop"' in notes[5]

    _undo_restores(client, headers, sid, 1, initial)


def test_a_note_is_added_to_a_chord_and_its_first_note_removed(tmp_path: Path) -> None:
    client, headers = _client(tmp_path)
    sid = _session(client, headers)
    initial = _initial(client, headers, sid)

    added = {"kind": "note", "pitch": "B4", "duration_beats": "1", "is_chord": True}
    res = _edit(client, headers, sid, "InsertEvent", _anchor(3), added)
    assert res.status_code == 201, res.text
    assert [e["pitch"] for e in _events(res.json())][:5] == ["C4", "E4", "G4", "B4", "D4"]
    timing = {
        t["anchor"]["event_index"]: t["offset_beats"]
        for t in res.json()["timing"]["events"]
        if t["anchor"]["measure"] == 1
    }
    assert [timing[i] for i in range(5)] == ["0", "0", "0", "0", "1"]

    res = _edit(client, headers, sid, "DeleteEvent", _anchor(0), {"keep_chord": True}, 1)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["after"] == {"keep_chord": True}
    assert body["before"]["next_in_chord"] == {
        "duration_beats": "1",
        "articulations": [],
        "fermata": False,
        "slurs": [],
    }
    head = _events(body)[0]
    assert (head["pitch"], head["is_chord"], head["articulations"]) == ("E4", False, ["accent"])

    export = client.get(f"/sessions/{sid}/export?format=musicxml", headers=headers)
    chords = [re.search(r"<chord\s*/>", note) is not None for note in _notes(export.text)]
    # Mi, Sol y Si siguen siendo un acorde, con el acento en su primera nota.
    assert chords[:4] == [False, True, True, False]
    assert "<accent" in _notes(export.text)[0]

    # Deshacer los dos pasos devuelve la partitura transcrita.
    undo = client.post(f"/sessions/{sid}/undo", json={"base_seq": 2}, headers=headers)
    assert undo.status_code == 200, undo.text
    _undo_restores(client, headers, sid, 3, initial)


def test_invalid_tie_and_chord_edits_are_422(tmp_path: Path) -> None:
    client, headers = _client(tmp_path)
    sid = _session(client, headers)
    cases: list[tuple[str, dict[str, Any], dict[str, Any] | None]] = [
        # La primera nota de un acorde se borra conservando el acorde.
        ("DeleteEvent", _anchor(0), None),
        ("DeleteEvent", _anchor(1), {"keep_chord": True}),
        ("DeleteEvent", _anchor(0), {"keep_chord": False}),
        # Un evento sin is_chord no parte el acorde; una nota de acorde va tras otra nota.
        ("InsertEvent", _anchor(2), {"kind": "rest", "duration_beats": "1"}),
        (
            "InsertEvent",
            _anchor(0),
            {"kind": "note", "pitch": "A3", "duration_beats": "1", "is_chord": True},
        ),
        (
            "InsertEvent",
            _anchor(3),
            {**{"kind": "note", "pitch": "A3", "duration_beats": "1"}, "next_in_chord": {}},
        ),
        # La ligadura: distinta altura, una nota que no es la siguiente, mal formada.
        ("SetTie", _anchor(3), {**ACROSS, "next": {**ACROSS["next"], "measure": 1}}),
        (
            "SetTie",
            _anchor(3),
            {"tie": "start", "next": {"measure": 1, "voice": 0, "event_index": 4, "tie": "stop"}},
        ),
        ("SetTie", _anchor(4), {"tie": "start"}),
        ("SetTie", _anchor(4), {"tie": "start", "next": None}),
    ]
    for op, anchor, after in cases:
        res = _edit(client, headers, sid, op, anchor, after)
        assert res.status_code == 422, (op, anchor, after, res.text)
    assert client.get(f"/sessions/{sid}", headers=headers).json()["current_seq"] == 0
