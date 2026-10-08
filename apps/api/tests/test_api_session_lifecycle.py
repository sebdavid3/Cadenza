"""Pruebas de integración de la API para el ciclo de vida de la sesión (Issue #34, ADR-0014)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

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
from cadenza.omr import OMREngine
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi.testclient import TestClient

ANCHOR = {
    "part": 0,
    "staff": 0,
    "measure": 1,
    "voice": 0,
    "event_index": 0,
    "staff_id": "part-0-staff-0",
}

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
)


class SyntheticOMREngine(OMREngine):
    """OMR sintético para pruebas de ciclo de vida con 3 notas en compás de 4/4."""

    @property
    def engine_id(self) -> str:
        return "synthetic-omr"

    @property
    def model_version(self) -> str:
        return "1.0.0"

    def transcribe(self, image_path: Path) -> ScoreDocument:
        m1 = Measure(
            number=1,
            events=(
                Event(kind=EventKind.NOTE, voice=0, pitch="C4", duration_beats=Fraction(1)),
                Event(kind=EventKind.NOTE, voice=0, pitch="D4", duration_beats=Fraction(1)),
                Event(kind=EventKind.NOTE, voice=0, pitch="E4", duration_beats=Fraction(1)),
            ),
            time_signature=TimeSignature(4, 4),
        )
        score = ScoreIR(
            parts=(Part(id="part-0", staves=(Staff(id="part-0-staff-0", measures=(m1,)),)),)
        )
        return ScoreDocument(
            id="doc-lifecycle-api",
            score=score,
            anchors=build_anchor_index(score),
            provenance=Provenance(omr_engine=self.engine_id, model_version=self.model_version),
        )


def _setup_api(tmp_path: Path) -> tuple[TestClient, dict[str, str]]:
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as db:
        user_repo = SqlAlchemyUserRepository(db)
        user_repo.add(
            User(
                id="user-t1",
                username="transcriptor1",
                password_hash="hash1",
                role=Role.TRANSCRIPTOR,
                active=True,
            )
        )
        user_repo.add(
            User(
                id="user-t2",
                username="transcriptor2",
                password_hash="hash2",
                role=Role.TRANSCRIPTOR,
                active=True,
            )
        )
        user_repo.add(
            User(
                id="user-inv",
                username="investigador1",
                password_hash="hash3",
                role=Role.INVESTIGADOR,
                active=True,
            )
        )
        db.commit()

    settings = Settings(
        auth_secret_key="secret-key-at-least-32-bytes-long-for-testing",
        artifacts_dir=tmp_path / "artifacts",
    )
    app = create_app(
        session_factory,
        omr_engine=SyntheticOMREngine(),
        settings=settings,
    )

    tokens = {
        "owner": app.state.token_service.create_access_token(
            user_id="user-t1", role=Role.TRANSCRIPTOR
        ),
        "other": app.state.token_service.create_access_token(
            user_id="user-t2", role=Role.TRANSCRIPTOR
        ),
        "researcher": app.state.token_service.create_access_token(
            user_id="user-inv", role=Role.INVESTIGADOR
        ),
    }

    return TestClient(app), tokens


def test_session_lifecycle_end_to_end(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    owner_headers = {"Authorization": f"Bearer {tokens['owner']}"}

    # 1. Transcribir -> estado inicial transcribed
    files = {"file": ("test.png", PNG_BYTES, "image/png")}
    res_tx = client.post("/transcribe", files=files, headers=owner_headers)
    assert res_tx.status_code == 201
    session_id = res_tx.json()["session_id"]

    res_get = client.get(f"/sessions/{session_id}", headers=owner_headers)
    assert res_get.status_code == 200
    assert res_get.json()["status"] == "transcribed"

    # 2. Primera edición -> pasa a correcting
    res_edit = client.post(
        f"/sessions/{session_id}/edits",
        headers=owner_headers,
        json={
            "base_seq": 0,
            "anchor": ANCHOR,
            "op": "SetPitch",
            "before": {"pitch": "C4"},
            "after": {"pitch": "C#4"},
        },
    )
    assert res_edit.status_code == 201
    assert res_edit.json()["seq"] == 1

    res_get2 = client.get(f"/sessions/{session_id}", headers=owner_headers)
    assert res_get2.status_code == 200
    assert res_get2.json()["status"] == "correcting"

    # 3. Finalizar sesión
    res_finalize = client.post(f"/sessions/{session_id}/finalize", headers=owner_headers)
    assert res_finalize.status_code == 200
    final_data = res_finalize.json()
    assert final_data["session_id"] == session_id
    assert final_data["status"] == "finalized"
    assert final_data["final_seq"] == 1
    assert isinstance(final_data["findings"], list)

    res_get3 = client.get(f"/sessions/{session_id}", headers=owner_headers)
    assert res_get3.status_code == 200
    assert res_get3.json()["status"] == "finalized"

    # 4. Intento de editar una sesión finalizada -> 409 Conflict
    res_blocked_edit = client.post(
        f"/sessions/{session_id}/edits",
        headers=owner_headers,
        json={
            "base_seq": 1,
            "anchor": ANCHOR,
            "op": "SetPitch",
            "before": {"pitch": "C#4"},
            "after": {"pitch": "D4"},
        },
    )
    assert res_blocked_edit.status_code == 409
    assert "finalizada" in res_blocked_edit.json()["detail"].lower()

    # 5. Reabrir sesión
    res_reopen = client.post(f"/sessions/{session_id}/reopen", headers=owner_headers)
    assert res_reopen.status_code == 200
    reopen_data = res_reopen.json()
    assert reopen_data["session_id"] == session_id
    assert reopen_data["status"] == "correcting"
    assert reopen_data["current_seq"] == 1

    # 6. Edición tras reapertura -> 201 Created
    res_post_reopen_edit = client.post(
        f"/sessions/{session_id}/edits",
        headers=owner_headers,
        json={
            "base_seq": 1,
            "anchor": ANCHOR,
            "op": "SetPitch",
            "before": {"pitch": "C#4"},
            "after": {"pitch": "D4"},
        },
    )
    assert res_post_reopen_edit.status_code == 201
    assert res_post_reopen_edit.json()["seq"] == 2


def test_session_lifecycle_authorization(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    owner_headers = {"Authorization": f"Bearer {tokens['owner']}"}
    other_headers = {"Authorization": f"Bearer {tokens['other']}"}
    researcher_headers = {"Authorization": f"Bearer {tokens['researcher']}"}

    # Crear sesión con el dueño
    files = {"file": ("test.png", PNG_BYTES, "image/png")}
    res_tx = client.post("/transcribe", files=files, headers=owner_headers)
    session_id = res_tx.json()["session_id"]

    # Sin token -> 401
    assert client.post(f"/sessions/{session_id}/finalize").status_code == 401
    assert client.post(f"/sessions/{session_id}/reopen").status_code == 401

    # Transcriptor ajeno -> 404
    assert client.post(f"/sessions/{session_id}/finalize", headers=other_headers).status_code == 404
    assert client.post(f"/sessions/{session_id}/reopen", headers=other_headers).status_code == 404

    # Investigador ajeno -> 403 Forbidden
    assert (
        client.post(f"/sessions/{session_id}/finalize", headers=researcher_headers).status_code
        == 403
    )
    assert (
        client.post(f"/sessions/{session_id}/reopen", headers=researcher_headers).status_code == 403
    )

    # Sesión inexistente -> 404
    assert client.post("/sessions/nonexistent/finalize", headers=owner_headers).status_code == 404
    assert client.post("/sessions/nonexistent/reopen", headers=owner_headers).status_code == 404
