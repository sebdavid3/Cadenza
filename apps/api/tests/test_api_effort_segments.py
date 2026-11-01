"""`PUT /sessions/{id}/effort/segments/{segment_id}`: el registro que acumula la web (#188).

ADR-0050: un registro por sesión que suma los tramos de tiempo de cada pestaña, cuenta las
intervenciones del log por compás y por clase, y los descartes, las restauraciones y las
respuestas a las sugerencias; finalizar lo cierra, y reabrir y volver a finalizar acumula.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from cadenza.api import Settings, create_app
from cadenza.application import Role, User
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


class Api:
    def __init__(self, tmp_path: Path) -> None:
        engine = create_memory_engine()
        create_schema(engine)
        factory = create_session_factory(engine)
        with factory() as db:
            users = SqlAlchemyUserRepository(db)
            for user_id, role in (
                ("owner", Role.TRANSCRIPTOR),
                ("other", Role.TRANSCRIPTOR),
                ("inv", Role.INVESTIGADOR),
            ):
                users.add(User(id=user_id, username=user_id, password_hash="h", role=role))
            db.commit()
        app = create_app(
            factory,
            omr_engine=FakeOMREngine(),
            settings=Settings(
                auth_secret_key="secret-key-at-least-32-bytes-long-for-testing",
                artifacts_dir=tmp_path / "artifacts",
            ),
        )
        self.client = TestClient(app)
        self.tokens = {
            user_id: app.state.token_service.create_access_token(user_id=user_id, role=role)
            for user_id, role in (
                ("owner", Role.TRANSCRIPTOR),
                ("other", Role.TRANSCRIPTOR),
                ("inv", Role.INVESTIGADOR),
            )
        }
        res = self.post("/transcribe", files={"file": ("score.png", PNG_BYTES, "image/png")})
        assert res.status_code == 201, res.text
        self.session_id: str = res.json()["session_id"]

    def headers(self, user: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[user]}"}

    def post(self, path: str, *, user: str = "owner", **kwargs: Any) -> Any:
        return self.client.post(path, headers=self.headers(user), **kwargs)

    def segment(
        self,
        segment_id: str,
        active_ms: int,
        first_edit_ms: int | None = None,
        *,
        user: str = "owner",
    ) -> Any:
        return self.client.put(
            f"/sessions/{self.session_id}/effort/segments/{segment_id}",
            json={
                "active_ms": active_ms,
                "first_edit_ms": first_edit_ms,
                "idle_threshold_ms": 120_000,
            },
            headers=self.headers(user),
        )

    def records(self) -> list[dict[str, Any]]:
        res = self.client.get(f"/sessions/{self.session_id}/effort", headers=self.headers("owner"))
        assert res.status_code == 200, res.text
        records: list[dict[str, Any]] = res.json()
        return records

    def edit(self, op: str, after: dict[str, Any], base_seq: int) -> None:
        res = self.post(
            f"/sessions/{self.session_id}/edits",
            json={"base_seq": base_seq, "op": op, "anchor": ANCHOR, "after": after},
        )
        assert res.status_code == 201, res.text


@pytest.fixture
def api(tmp_path: Path) -> Api:
    return Api(tmp_path)


def test_segments_accumulate_in_one_record(api: Api) -> None:
    first = api.segment("tab-a", 12_000)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["accumulated"] is True
    assert body["duration_ms"] == 12_000
    assert body["segments"] == [
        {"id": "tab-a", "active_ms": 12_000, "first_edit_ms": None, "idle_threshold_ms": 120_000}
    ]

    api.edit("SetPitch", {"pitch": "G4"}, base_seq=0)
    assert api.segment("tab-a", 20_000, first_edit_ms=15_000).status_code == 200
    # Una recarga sin `sessionStorage` abre otro tramo; la petición repetida no cuenta dos veces.
    assert api.segment("tab-b", 3_000).status_code == 200
    assert api.segment("tab-b", 3_000).status_code == 200

    (record,) = api.records()
    assert record["duration_ms"] == 23_000
    assert record["time_to_first_edit_ms"] == 15_000
    assert record["interventions"] == {"1": 1}
    assert record["interventions_by_class"] == {"content": {"1": 1}, "mark": {}, "meter": {}}
    assert record["updated_at"] is not None


def test_dismissing_and_restoring_are_counted(api: Api) -> None:
    # Una figura que descuadra el compás 1: la revalidación lo señala.
    api.edit("SetDuration", {"duration_beats": "3"}, base_seq=0)
    validated = api.post(f"/sessions/{api.session_id}/validate")
    assert validated.status_code == 200, validated.text
    finding_id = validated.json()["findings"][0]["id"]
    base = f"/sessions/{api.session_id}/findings/{finding_id}"

    assert api.post(f"{base}/dismiss").status_code == 200
    assert api.post(f"{base}/dismiss").status_code == 200
    assert api.post(f"{base}/restore").status_code == 200

    (record,) = api.records()
    assert (record["findings_dismissed"], record["findings_restored"]) == (1, 1)
    assert (record["suggestions_applied"], record["suggestions_rejected"]) == (0, 0)


def test_finalize_closes_and_reopen_keeps_accumulating(api: Api) -> None:
    assert api.segment("tab-a", 10_000).status_code == 200
    api.edit("SetPitch", {"pitch": "G4"}, base_seq=0)

    assert api.post(f"/sessions/{api.session_id}/finalize").status_code == 200
    (record,) = api.records()
    # Finalizar recuenta el log, aunque no llegara otro tramo después de la edición.
    assert record["interventions"] == {"1": 1}
    closed = api.segment("tab-a", 11_000)
    assert closed.status_code == 409
    assert api.records()[0]["duration_ms"] == 10_000

    assert api.post(f"/sessions/{api.session_id}/reopen").status_code == 200
    assert api.segment("tab-a", 16_000).status_code == 200
    api.edit("SetPitch", {"pitch": "A4"}, base_seq=1)
    assert api.post(f"/sessions/{api.session_id}/finalize").status_code == 200

    (record,) = api.records()
    assert record["duration_ms"] == 16_000
    assert record["interventions"] == {"1": 2}


def test_only_the_owner_measures(api: Api) -> None:
    unauthenticated = api.client.put(
        f"/sessions/{api.session_id}/effort/segments/tab-a",
        json={"active_ms": 1, "first_edit_ms": None},
    )
    assert unauthenticated.status_code == 401
    assert api.segment("tab-a", 1, user="other").status_code == 404
    assert api.segment("tab-a", 1, user="inv").status_code == 403
    assert api.records() == []


@pytest.mark.parametrize(
    ("segment_id", "body"),
    [
        ("tab-a", {"active_ms": -1, "first_edit_ms": None}),
        ("tab-a", {"active_ms": 1_000, "first_edit_ms": 1_001}),
        ("tab-a", {"active_ms": 1_000, "extra": 1}),
        ("tab-a", {"active_ms": 1_000, "idle_threshold_ms": 0}),
        ("x" * 65, {"active_ms": 1_000}),
        ("tab.a", {"active_ms": 1_000}),
    ],
)
def test_an_impossible_segment_is_a_422(api: Api, segment_id: str, body: dict[str, Any]) -> None:
    res = api.client.put(
        f"/sessions/{api.session_id}/effort/segments/{segment_id}",
        json=body,
        headers=api.headers("owner"),
    )
    assert res.status_code == 422, res.text
    assert api.records() == []


def test_loose_records_still_work_and_are_listed_apart(api: Api) -> None:
    loose = api.post(f"/sessions/{api.session_id}/effort", json={"duration_ms": 5})
    assert loose.status_code == 201
    assert loose.json()["accumulated"] is False
    assert api.segment("tab-a", 7).status_code == 200

    records = api.records()
    assert sorted(r["accumulated"] for r in records) == [False, True]
