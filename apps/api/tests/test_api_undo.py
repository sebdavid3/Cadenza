"""Pruebas de integración HTTP para el endpoint de deshacer (Issue #35, ADR-0007, ADR-0012)."""

from __future__ import annotations

from pathlib import Path

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
        omr_engine=FakeOMREngine(),
        settings=settings,
    )

    tokens = {
        "t1": app.state.token_service.create_access_token(
            user_id="user-t1", role=Role.TRANSCRIPTOR
        ),
        "t2": app.state.token_service.create_access_token(
            user_id="user-t2", role=Role.TRANSCRIPTOR
        ),
        "inv": app.state.token_service.create_access_token(
            user_id="user-inv", role=Role.INVESTIGADOR
        ),
    }

    return TestClient(app), tokens


def _create_session(client: TestClient, token: str) -> str:
    res = client.post(
        "/transcribe",
        files={"file": ("score.png", PNG_BYTES, "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201, res.text
    session_id = res.json()["session_id"]
    assert isinstance(session_id, str)
    return session_id


def test_undo_endpoint_success_and_verifies_state(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    token = tokens["t1"]
    session_id = _create_session(client, token)

    # 1. Aplicar edición: C4 -> G4 en compás 1, nota 0
    edit_payload = {
        "base_seq": 0,
        "op": "SetPitch",
        "anchor": {
            "part": 0,
            "staff": 0,
            "measure": 1,
            "voice": 0,
            "event_index": 0,
            "staff_id": "part-0-staff-0",
        },
        "before": {"pitch": "C4"},
        "after": {"pitch": "G4"},
    }
    edit_res = client.post(
        f"/sessions/{session_id}/edits",
        json=edit_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert edit_res.status_code == 201
    edit_data = edit_res.json()
    assert edit_data["seq"] == 1

    # 2. Deshacer la edición en el servidor
    undo_res = client.post(
        f"/sessions/{session_id}/undo",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert undo_res.status_code == 200
    undo_data = undo_res.json()
    assert undo_data["session_id"] == session_id
    assert undo_data["current_seq"] == 2
    assert undo_data["undone_edit_id"] == edit_data["id"]
    assert undo_data["compensatory_edit_id"] is not None
    assert undo_data["compensatory_edit"]["reverts_edit_id"] == edit_data["id"]

    # 3. La partitura materializada tiene nuevamente la nota inicial "C4"
    events = undo_data["current_score"]["parts"][0]["staves"][0]["measures"][0]["events"]
    assert events[0]["pitch"] == "C4"

    # 4. GET /sessions/{id} confirma que current_seq=2 y el log tiene 2 eventos
    detail_res = client.get(
        f"/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["current_seq"] == 2
    assert len(detail["edits"]) == 2
    assert detail["edits"][0]["id"] == edit_data["id"]
    assert detail["edits"][1]["reverts_edit_id"] == edit_data["id"]
    assert (
        detail["current_score"]["parts"][0]["staves"][0]["measures"][0]["events"][0]["pitch"]
        == "C4"
    )


def test_undo_endpoint_consecutive_edits(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    token = tokens["t1"]
    session_id = _create_session(client, token)

    # Edit 1: C4 -> G4
    client.post(
        f"/sessions/{session_id}/edits",
        json={
            "base_seq": 0,
            "op": "SetPitch",
            "anchor": {
                "part": 0,
                "staff": 0,
                "measure": 1,
                "voice": 0,
                "event_index": 0,
                "staff_id": "part-0-staff-0",
            },
            "before": {"pitch": "C4"},
            "after": {"pitch": "G4"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    # Edit 2: D4 -> A4
    client.post(
        f"/sessions/{session_id}/edits",
        json={
            "base_seq": 1,
            "op": "SetPitch",
            "anchor": {
                "part": 0,
                "staff": 0,
                "measure": 1,
                "voice": 0,
                "event_index": 1,
                "staff_id": "part-0-staff-0",
            },
            "before": {"pitch": "D4"},
            "after": {"pitch": "A4"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    # Undo 1: revierte Edit 2 -> notas: G4, D4
    res1 = client.post(
        f"/sessions/{session_id}/undo",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res1.status_code == 200
    events1 = res1.json()["current_score"]["parts"][0]["staves"][0]["measures"][0]["events"]
    assert events1[0]["pitch"] == "G4"
    assert events1[1]["pitch"] == "D4"

    # Undo 2: revierte Edit 1 -> notas: C4, D4
    res2 = client.post(
        f"/sessions/{session_id}/undo",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res2.status_code == 200
    events2 = res2.json()["current_score"]["parts"][0]["staves"][0]["measures"][0]["events"]
    assert events2[0]["pitch"] == "C4"
    assert events2[1]["pitch"] == "D4"

    # Undo 3: ya no hay ediciones activas -> HTTP 422
    res3 = client.post(
        f"/sessions/{session_id}/undo",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res3.status_code == 422
    assert "no hay ediciones activas" in res3.json()["detail"].lower()


def test_undo_endpoint_on_empty_session_returns_422(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    session_id = _create_session(client, tokens["t1"])

    res = client.post(
        f"/sessions/{session_id}/undo",
        headers={"Authorization": f"Bearer {tokens['t1']}"},
    )
    assert res.status_code == 422
    assert "no hay ediciones activas" in res.json()["detail"].lower()


def test_undo_endpoint_with_base_seq_validation(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    token = tokens["t1"]
    session_id = _create_session(client, token)

    client.post(
        f"/sessions/{session_id}/edits",
        json={
            "base_seq": 0,
            "op": "SetPitch",
            "anchor": {
                "part": 0,
                "staff": 0,
                "measure": 1,
                "voice": 0,
                "event_index": 0,
                "staff_id": "part-0-staff-0",
            },
            "before": {"pitch": "C4"},
            "after": {"pitch": "G4"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    # base_seq=0 con current_seq=1 -> 409 Conflict
    conflict_res = client.post(
        f"/sessions/{session_id}/undo",
        json={"base_seq": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert conflict_res.status_code == 409
    assert "conflicto de secuencia" in conflict_res.json()["detail"].lower()

    # base_seq=1 -> éxito 200
    success_res = client.post(
        f"/sessions/{session_id}/undo",
        json={"base_seq": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert success_res.status_code == 200
    assert success_res.json()["current_seq"] == 2


def test_undo_endpoint_authorization_adr0012(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    session_id = _create_session(client, tokens["t1"])

    # 1. Sin token -> 401
    res_unauth = client.post(f"/sessions/{session_id}/undo")
    assert res_unauth.status_code == 401

    # 2. Transcriptor ajeno -> 404 (ADR-0012)
    res_other_trans = client.post(
        f"/sessions/{session_id}/undo",
        headers={"Authorization": f"Bearer {tokens['t2']}"},
    )
    assert res_other_trans.status_code == 404

    # 3. Investigador ajeno -> 403 (ADR-0012)
    res_other_inv = client.post(
        f"/sessions/{session_id}/undo",
        headers={"Authorization": f"Bearer {tokens['inv']}"},
    )
    assert res_other_inv.status_code == 403


def test_undo_endpoint_on_finalized_session_returns_409(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    token = tokens["t1"]
    session_id = _create_session(client, token)

    # Finalizar sesión
    fin_res = client.post(
        f"/sessions/{session_id}/finalize",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert fin_res.status_code == 200

    # Deshacer sobre sesión finalizada -> 409 SessionClosed
    undo_res = client.post(
        f"/sessions/{session_id}/undo",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert undo_res.status_code == 409
    assert "está finalizada" in undo_res.json()["detail"].lower()
