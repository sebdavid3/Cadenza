"""Título, compositor e instrumentos por la API: al transcribir, al leer y con el PATCH (#235).

ADR-0041: campos opcionales en `POST /transcribe`; el detalle, la vista y el listado los
devuelven con el nombre del archivo subido; `PATCH /sessions/{id}` los cambia, solo el dueño, sin
tocar el log, e invalida la caché del estado (D66); el MusicXML y el MIDI los llevan.
"""

from __future__ import annotations

import secrets
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from cadenza.api import Settings, create_app
from cadenza.application import InMemoryScoreStateCache, Role, User
from cadenza.domain import ScoreDocument, ScoreIR, build_anchor_index
from cadenza.omr.testing import FakeOMREngine
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi.testclient import TestClient
from music21 import midi

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
)
ANCHOR = {
    "part": 0,
    "staff": 0,
    "measure": 1,
    "voice": 0,
    "event_index": 0,
    "staff_id": "part-0-staff-0",
}
PROGRAM_CHANGE = 0xC0


class _TwoPartsOMR(FakeOMREngine):
    """Dos partes, como la voz y el piano que HOMR detecta en *Mondnacht*."""

    def transcribe(self, image_path: Path) -> ScoreDocument:
        document = super().transcribe(image_path)
        (part,) = document.score.parts
        score = ScoreIR(parts=(part, replace(part, id="part-1")))
        return replace(document, score=score, anchors=build_anchor_index(score))


class Api:
    def __init__(self, tmp_path: Path) -> None:
        engine = create_memory_engine()
        create_schema(engine)
        factory = create_session_factory(engine)
        users = {
            "owner": Role.TRANSCRIPTOR,
            "other": Role.TRANSCRIPTOR,
            "researcher": Role.INVESTIGADOR,
        }
        with factory() as db:
            repo = SqlAlchemyUserRepository(db)
            for user_id, role in users.items():
                repo.add(
                    User(id=user_id, username=user_id, password_hash="h", role=role, active=True)
                )
            db.commit()
        self.cache = InMemoryScoreStateCache()
        app = create_app(
            factory,
            omr_engine=_TwoPartsOMR(),
            settings=Settings(
                auth_secret_key=secrets.token_urlsafe(48),
                artifacts_dir=tmp_path / "artifacts",
            ),
            score_cache=self.cache,
        )
        self.client = TestClient(app)
        self.headers = {
            user_id: {
                "Authorization": "Bearer "
                + app.state.token_service.create_access_token(user_id=user_id, role=role)
            }
            for user_id, role in users.items()
        }

    def transcribe(self, data: dict[str, Any] | None = None, filename: str = "score.png") -> Any:
        return self.client.post(
            "/transcribe",
            files={"file": (filename, PNG_BYTES, "image/png")},
            data=data,
            headers=self.headers["owner"],
        )

    def session(self, data: dict[str, Any] | None = None, filename: str = "score.png") -> str:
        response = self.transcribe(data, filename)
        assert response.status_code == 201, response.text
        return str(response.json()["session_id"])

    def get(self, path: str, user: str = "owner") -> Any:
        return self.client.get(path, headers=self.headers[user])

    def patch(self, session_id: str, body: dict[str, Any], user: str = "owner") -> Any:
        return self.client.patch(f"/sessions/{session_id}", json=body, headers=self.headers[user])


MONDNACHT = {
    "title": "Mondnacht",
    "composer": "Robert Schumann",
    "instruments": ["voice", "piano"],
    "part_names": ["Soprano", ""],
}
MONDNACHT_INSTRUMENTS = [
    {"instrument": "voice", "name": "Soprano"},
    {"instrument": "piano", "name": None},
]


@pytest.fixture
def api(tmp_path: Path) -> Api:
    return Api(tmp_path)


def _musicxml(api: Api, session_id: str) -> ET.Element:
    response = api.get(f"/sessions/{session_id}/export?format=musicxml")
    assert response.status_code == 200, response.text
    return ET.fromstring(response.content)


def _midi_programs(api: Api, session_id: str) -> list[list[int]]:
    response = api.get(f"/sessions/{session_id}/export?format=midi")
    assert response.status_code == 200
    mf = midi.MidiFile()
    mf.readstr(response.content)
    return [
        list(dict.fromkeys(int(e.data) for e in track.events if e.type == PROGRAM_CHANGE))
        for track in mf.tracks
    ]


# --- Al transcribir y al leer ------------------------------------------------------------------


def test_transcribe_with_metadata_and_read_it_back(api: Api) -> None:
    session_id = api.session(MONDNACHT, filename="Mondnacht p1.png")

    expected = {
        "title": "Mondnacht",
        "composer": "Robert Schumann",
        "instruments": MONDNACHT_INSTRUMENTS,
        "source_filename": "Mondnacht p1.png",
    }
    for path in (f"/sessions/{session_id}", f"/sessions/{session_id}?fields=view"):
        body = api.get(path).json()
        assert {key: body[key] for key in expected} == expected
    (summary,) = api.get("/sessions").json()
    assert {key: summary[key] for key in expected} == expected


def test_transcribe_without_metadata_has_none(api: Api) -> None:
    session_id = api.session()

    body = api.get(f"/sessions/{session_id}").json()
    assert body["title"] is None
    assert body["composer"] is None
    assert body["instruments"] == []
    assert body["source_filename"] == "score.png"
    # Lo exportado es lo de siempre: sin título, sin compositor y sin instrumentos.
    root = _musicxml(api, session_id)
    assert root.find("work") is None
    assert root.find("identification/creator") is None
    assert root.find("part-list/score-part/score-instrument") is None
    assert all(programs == [] for programs in _midi_programs(api, session_id))


def test_instrument_without_name_and_name_without_instrument(api: Api) -> None:
    session_id = api.session({"instruments": ["", "other"], "part_names": ["Canto", "Theremin"]})

    body = api.get(f"/sessions/{session_id}").json()
    assert body["instruments"] == [
        {"instrument": None, "name": "Canto"},
        {"instrument": "other", "name": "Theremin"},
    ]


def test_instruments_for_parts_omr_did_not_find_are_dropped(api: Api) -> None:
    session_id = api.session({"instruments": ["voice", "piano", "cello"]})

    body = api.get(f"/sessions/{session_id}").json()
    assert [item["instrument"] for item in body["instruments"]] == ["voice", "piano"]


@pytest.mark.parametrize(
    "data",
    [
        {"instruments": ["kazoo"]},
        {"title": "x" * 201},
        {"composer": "x" * 201},
        {"part_names": ["x" * 101]},
    ],
)
def test_invalid_metadata_is_rejected_before_transcribing(api: Api, data: dict[str, Any]) -> None:
    response = api.transcribe(data)

    assert response.status_code == 422, response.text
    assert api.get("/sessions").json() == []


# --- El PATCH ------------------------------------------------------------------------------------


def test_owner_changes_only_what_is_sent(api: Api) -> None:
    session_id = api.session(MONDNACHT)

    response = api.patch(session_id, {"title": "Mondnacht, Op. 39 n.º 5"})

    assert response.status_code == 200, response.text
    assert response.json() == {
        "session_id": session_id,
        "title": "Mondnacht, Op. 39 n.º 5",
        "composer": "Robert Schumann",
        "instruments": MONDNACHT_INSTRUMENTS,
        "source_filename": "score.png",
    }
    assert api.get(f"/sessions/{session_id}").json()["title"] == "Mondnacht, Op. 39 n.º 5"


def test_null_clears_and_instruments_are_replaced(api: Api) -> None:
    session_id = api.session(MONDNACHT)

    response = api.patch(
        session_id,
        {"composer": None, "instruments": [{"instrument": "cello"}]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Mondnacht"
    assert body["composer"] is None
    assert body["instruments"] == [{"instrument": "cello", "name": None}]


def test_patch_is_not_an_edit(api: Api) -> None:
    session_id = api.session()
    before = api.get(f"/sessions/{session_id}").json()

    assert api.patch(session_id, {"title": "Mondnacht"}).status_code == 200

    after = api.get(f"/sessions/{session_id}").json()
    assert after["edits"] == before["edits"] == []
    assert after["current_seq"] == before["current_seq"] == 0
    assert after["status"] == before["status"] == "transcribed"


def test_finalized_session_can_be_renamed(api: Api) -> None:
    session_id = api.session()
    finalize = api.client.post(f"/sessions/{session_id}/finalize", headers=api.headers["owner"])
    assert finalize.status_code == 200, finalize.text

    response = api.patch(session_id, {"title": "Mondnacht"})

    assert response.status_code == 200
    assert api.get(f"/sessions/{session_id}").json()["status"] == "finalized"


@pytest.mark.parametrize(("user", "status"), [("other", 404), ("researcher", 403)])
def test_only_the_owner_can_change_it(api: Api, user: str, status: int) -> None:
    session_id = api.session(MONDNACHT)

    assert api.patch(session_id, {"title": "Otro"}, user=user).status_code == status
    assert api.get(f"/sessions/{session_id}").json()["title"] == "Mondnacht"


def test_patch_needs_authentication(api: Api) -> None:
    session_id = api.session()
    response = api.client.patch(f"/sessions/{session_id}", json={"title": "x"})
    assert response.status_code == 401


def test_patch_missing_session(api: Api) -> None:
    assert api.patch("nope", {"title": "x"}).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"instruments": [{"instrument": "piano"}] * 3},
        {"instruments": [{"instrument": "kazoo"}]},
        {"title": "x" * 201},
        {"instruments": [{"name": "x" * 101}]},
        {"owner_id": "other"},
        {"instruments": [{"instrument": "piano", "midi_program": 3}]},
    ],
)
def test_invalid_patch_is_rejected(api: Api, body: dict[str, Any]) -> None:
    session_id = api.session(MONDNACHT)

    assert api.patch(session_id, body).status_code == 422
    assert api.get(f"/sessions/{session_id}").json()["instruments"] == MONDNACHT_INSTRUMENTS


# --- Lo exportado ---------------------------------------------------------------------------------


def test_export_carries_title_composer_and_instruments(api: Api) -> None:
    session_id = api.session(MONDNACHT)

    root = _musicxml(api, session_id)
    assert root.findtext("work/work-title") == "Mondnacht"
    assert root.findtext("identification/creator[@type='composer']") == "Robert Schumann"
    names = [p.findtext("part-name") for p in root.findall("part-list/score-part")]
    assert names == ["Soprano", "Piano"]
    programs = [
        p.findtext("midi-instrument/midi-program") for p in root.findall("part-list/score-part")
    ]
    assert programs == ["53", "1"]
    # La pista 0 es la de tempo; luego, una por parte.
    assert _midi_programs(api, session_id)[1:] == [[52], [0]]


def test_patch_invalidates_the_cached_musicxml(api: Api) -> None:
    # D66: el MusicXML cambia sin que cambie el `seq`.
    session_id = api.session(MONDNACHT)
    assert _musicxml(api, session_id).findtext("work/work-title") == "Mondnacht"
    assert len(api.cache) > 0

    assert api.patch(session_id, {"title": "Mondnacht, Op. 39"}).status_code == 200

    assert len(api.cache) == 0
    assert _musicxml(api, session_id).findtext("work/work-title") == "Mondnacht, Op. 39"


def test_edit_response_carries_the_metadata(api: Api) -> None:
    session_id = api.session()
    assert api.patch(session_id, {"title": "Mondnacht"}).status_code == 200

    response = api.client.post(
        f"/sessions/{session_id}/edits",
        json={"base_seq": 0, "op": "SetPitch", "anchor": ANCHOR, "after": {"pitch": "G4"}},
        headers=api.headers["owner"],
    )

    assert response.status_code == 201, response.text
    musicxml = response.json()["musicxml"]
    assert ET.fromstring(musicxml.encode("utf-8")).findtext("work/work-title") == "Mondnacht"
