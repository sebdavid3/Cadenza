"""Una edición en un solo viaje, medida por etapas (#275, ADR-0037).

El 201 de `POST /edits` y la respuesta de `POST /undo` traen el estado nuevo; el detalle admite
`fields=view`; cada respuesta lleva `Server-Timing` y el `X-Request-ID` del cliente.
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path
from typing import Any

import pytest
from cadenza.api import Settings, create_app
from cadenza.application import InMemoryScoreStateCache, Role, User
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
ANCHOR = {
    "part": 0,
    "staff": 0,
    "measure": 1,
    "voice": 0,
    "event_index": 0,
    "staff_id": "part-0-staff-0",
}
EDIT_FIELDS = {
    "id",
    "session_id",
    "seq",
    "op",
    "author",
    "anchor",
    "before",
    "after",
    "reverts_edit_id",
    "created_at",
}


class Api:
    def __init__(self, tmp_path: Path, cache: InMemoryScoreStateCache | None = None) -> None:
        engine = create_memory_engine()
        create_schema(engine)
        factory = create_session_factory(engine)
        with factory() as db:
            SqlAlchemyUserRepository(db).add(
                User(
                    id="user-t1",
                    username="t1",
                    password_hash="hash",
                    role=Role.TRANSCRIPTOR,
                    active=True,
                )
            )
            db.commit()
        app = create_app(
            factory,
            omr_engine=FakeOMREngine(),
            settings=Settings(
                auth_secret_key=secrets.token_urlsafe(48),
                artifacts_dir=tmp_path / "artifacts",
            ),
            score_cache=cache,
        )
        token = app.state.token_service.create_access_token(
            user_id="user-t1", role=Role.TRANSCRIPTOR
        )
        self.app = app
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {token}"}
        response = self.client.post(
            "/transcribe",
            files={"file": ("score.png", PNG_BYTES, "image/png")},
            headers=self.headers,
        )
        assert response.status_code == 201, response.text
        self.session_id: str = response.json()["session_id"]

    @property
    def base(self) -> str:
        return f"/sessions/{self.session_id}"

    def edit(self, base_seq: int, op: str = "SetPitch", after: dict[str, Any] | None = None) -> Any:
        return self.client.post(
            f"{self.base}/edits",
            json={
                "base_seq": base_seq,
                "op": op,
                "anchor": ANCHOR,
                "before": None,
                "after": after if after is not None else {"pitch": "G4"},
            },
            headers=self.headers,
        )

    def get(self, path: str, **params: Any) -> Any:
        return self.client.get(path, params=params or None, headers=self.headers)


@pytest.fixture
def api(tmp_path: Path) -> Api:
    return Api(tmp_path)


def test_edit_201_keeps_the_edit_and_adds_the_new_state(api: Api) -> None:
    response = api.edit(0)

    assert response.status_code == 201
    body = response.json()
    assert set(body) >= EDIT_FIELDS
    assert body["seq"] == 1
    assert body["op"] == "SetPitch"
    assert body["before"] == {"pitch": "C4"}
    detail = api.get(api.base).json()
    assert body["current_seq"] == detail["current_seq"] == 1
    assert body["current_score"] == detail["current_score"]
    assert body["status"] == detail["status"] == "correcting"
    assert body["musicxml"] == api.get(f"{api.base}/export", format="musicxml").text
    assert "<score-partwise" in body["musicxml"]
    # Una altura no cambia los tiempos: no viajan.
    assert body["timing"] is None


def test_edit_returns_the_timing_when_it_changes(api: Api) -> None:
    response = api.edit(0, op="SetDuration", after={"duration_beats": "2"})

    assert response.status_code == 201
    assert response.json()["timing"] == api.get(f"{api.base}/timing").json()


def test_undo_returns_the_new_state_and_keeps_its_fields(api: Api) -> None:
    api.edit(0, op="SetDuration", after={"duration_beats": "2"})

    response = api.client.post(f"{api.base}/undo", json={"base_seq": 1}, headers=api.headers)

    assert response.status_code == 200
    body = response.json()
    assert {
        "session_id",
        "current_seq",
        "undone_edit_id",
        "current_score",
        "anchor_index",
        "compensatory_edit_id",
        "compensatory_edit",
    } <= set(body)
    assert body["anchor_index"] is not None
    assert body["current_seq"] == 2
    assert body["status"] == "correcting"
    assert body["musicxml"] == api.get(f"{api.base}/export", format="musicxml").text
    assert body["timing"] == api.get(f"{api.base}/timing").json()
    assert body["current_score"] == api.get(api.base).json()["current_score"]


def test_conflict_is_still_409_and_saves_nothing(api: Api) -> None:
    assert api.edit(0).status_code == 201

    stale = api.edit(0)

    assert stale.status_code == 409
    assert "current_score" not in stale.json()
    assert api.get(api.base).json()["current_seq"] == 1


def test_invalid_edit_is_still_422_and_saves_nothing(api: Api) -> None:
    response = api.edit(0, after={"pitch": "H9"})

    assert response.status_code == 422
    assert api.get(api.base).json()["edits"] == []


def test_detail_view_leaves_out_the_document_and_the_anchor_index(api: Api) -> None:
    api.edit(0)

    full = api.get(api.base).json()
    view = api.get(api.base, fields="view").json()

    assert "document" in full
    assert full["anchor_index"] is not None
    assert "document" not in view
    assert "anchor_index" not in view
    assert view == {k: v for k, v in full.items() if k not in ("document", "anchor_index")}


def test_detail_rejects_an_unknown_fields_value(api: Api) -> None:
    assert api.get(api.base, fields="todo").status_code == 422


@pytest.mark.parametrize(
    ("method", "suffix", "stages"),
    [
        ("POST", "/edits", {"db", "materialize", "export", "serialize"}),
        ("GET", "", {"db", "materialize", "serialize"}),
        ("GET", "/export?format=musicxml", {"db", "materialize", "export"}),
        ("GET", "/timing", {"db", "materialize", "timing", "serialize"}),
    ],
)
def test_responses_say_how_long_each_stage_took(
    tmp_path: Path, method: str, suffix: str, stages: set[str]
) -> None:
    # Sin caché, para que cada ruta materialice su estado.
    api = Api(tmp_path, cache=InMemoryScoreStateCache(max_entries=0))
    if method == "POST":
        response = api.edit(0)
    else:
        response = api.client.get(f"{api.base}{suffix}", headers=api.headers)

    assert response.status_code < 300
    header = response.headers["server-timing"]
    names = {item.split(";")[0].strip() for item in header.split(",")}
    assert stages | {"total"} <= names
    for item in header.split(","):
        _name, dur = item.strip().split(";")
        assert dur.startswith("dur=")
        assert float(dur[4:]) >= 0


def test_undo_says_how_long_each_stage_took(api: Api) -> None:
    api.edit(0)
    response = api.client.post(f"{api.base}/undo", json={"base_seq": 1}, headers=api.headers)
    names = {item.split(";")[0].strip() for item in response.headers["server-timing"].split(",")}
    assert {"db", "materialize", "export", "serialize", "total"} <= names


def test_a_well_formed_request_id_comes_back(api: Api) -> None:
    response = api.client.get(api.base, headers={**api.headers, "X-Request-ID": "web-1a2b.3_c"})
    assert response.headers["x-request-id"] == "web-1a2b.3_c"


@pytest.mark.parametrize("bad", ["con espacios", "x" * 65, "salto\\nde-linea", "a/b;c"])
def test_a_malformed_request_id_is_replaced(api: Api, bad: str) -> None:
    response = api.client.get(api.base, headers={**api.headers, "X-Request-ID": bad})
    returned = response.headers["x-request-id"]
    assert returned != bad
    assert len(returned) == 32


def test_the_cache_serves_the_state_the_edit_created(tmp_path: Path) -> None:
    cache = InMemoryScoreStateCache()
    api = Api(tmp_path, cache=cache)
    exporter = api.app.state.score_exporter
    calls: list[int] = []
    original = exporter.to_musicxml

    def counting(score: Any) -> str:
        calls.append(1)
        return str(original(score))

    exporter.to_musicxml = counting
    edited = api.edit(0).json()
    exported = api.get(f"{api.base}/export", format="musicxml")

    assert exported.text == edited["musicxml"]
    assert calls == [1]
    names = {i.split(";")[0].strip() for i in exported.headers["server-timing"].split(",")}
    assert "materialize" not in names
    assert "export" not in names


def _stable(musicxml: str) -> str:
    """El MusicXML sin lo que music21 cambia en cada exportación: ids de parte y fecha."""
    without_ids = re.sub(r"P[0-9a-f]{32}", "P", musicxml)
    return re.sub(r"<encoding-date>[^<]*</encoding-date>", "", without_ids)


def test_cached_states_match_an_api_without_cache(tmp_path: Path) -> None:
    """Editar, deshacer, rehacer y deshacer: lo que devuelve la API con caché es lo que daría
    sin ella, es decir, `materialize` sobre el log guardado."""
    cached = Api(tmp_path / "con", cache=InMemoryScoreStateCache())
    plain = Api(tmp_path / "sin", cache=InMemoryScoreStateCache(max_entries=0))

    def undo(api: Api, base_seq: int) -> Any:
        return api.client.post(f"{api.base}/undo", json={"base_seq": base_seq}, headers=api.headers)

    steps: list[tuple[str, Any]] = [
        ("edit", {"base_seq": 0, "op": "SetDuration", "after": {"duration_beats": "2"}}),
        ("undo", 1),
        ("edit", {"base_seq": 2, "op": "SetDuration", "after": {"duration_beats": "2"}}),
        ("edit", {"base_seq": 3, "op": "SetPitch", "after": {"pitch": "A4"}}),
        ("undo", 4),
    ]
    for kind, arg in steps:
        results = [
            api.edit(**arg).json() if kind == "edit" else undo(api, arg).json()
            for api in (cached, plain)
        ]
        with_cache, without = results
        for key in ("current_seq", "current_score", "status"):
            assert with_cache[key] == without[key], (kind, key)
        assert _stable(with_cache["musicxml"]) == _stable(without["musicxml"]), kind
        assert (with_cache["timing"] is None) == (without["timing"] is None)
        if with_cache["timing"] is not None:
            assert with_cache["timing"]["events"] == without["timing"]["events"]
        for api, body in ((cached, with_cache), (plain, without)):
            assert api.get(api.base).json()["current_score"] == body["current_score"]
