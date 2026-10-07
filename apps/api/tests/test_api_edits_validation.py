"""Pruebas de la API para validación de ediciones (422 y 409) (Issue #10, ADR-0007, ADR-0011)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cadenza.api import Settings, create_app
from cadenza.application import (
    Role,
    SequenceConflict,
    User,
)
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


def _setup_api_client(tmp_path: Path) -> tuple[TestClient, str]:
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as db:
        user_repo = SqlAlchemyUserRepository(db)
        user_repo.add(
            User(
                id="user-t1",
                username="transcriptor1",
                password_hash="test",
                role=Role.TRANSCRIPTOR,
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

    token = app.state.token_service.create_access_token(user_id="user-t1", role=Role.TRANSCRIPTOR)
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {token}"

    upload_resp = client.post(
        "/transcribe",
        files={"file": ("score.png", PNG_BYTES, "image/png")},
    )
    assert upload_resp.status_code == 201
    session_id = upload_resp.json()["session_id"]
    return client, session_id


def test_append_edit_invalid_anchor_returns_422(tmp_path: Path) -> None:
    client, session_id = _setup_api_client(tmp_path)

    # Ancla con compás 999 inexistente
    payload = {
        "base_seq": 0,
        "op": "SetPitch",
        "anchor": {
            "part": 0,
            "staff": 0,
            "staff_id": "part-0-staff-0",
            "measure": 999,
            "voice": 0,
            "event_index": 0,
        },
        "after": {"pitch": "D4"},
    }
    response = client.post(f"/sessions/{session_id}/edits", json=payload)
    assert response.status_code == 422
    assert "detail" in response.json()
    assert (
        "compás inexistente" in response.json()["detail"].lower()
        or "no aplicable" in response.json()["detail"].lower()
    )

    # Verificar que el log de la sesión sigue vacío
    detail = client.get(f"/sessions/{session_id}").json()
    assert detail["edits"] == []


def test_append_edit_mismatched_before_returns_422(tmp_path: Path) -> None:
    client, session_id = _setup_api_client(tmp_path)

    # Evento 0 en compás 1 es C4; enviamos before={"pitch": "G4"}
    payload = {
        "base_seq": 0,
        "op": "SetPitch",
        "anchor": {
            "part": 0,
            "staff": 0,
            "staff_id": "part-0-staff-0",
            "measure": 1,
            "voice": 0,
            "event_index": 0,
        },
        "before": {"pitch": "G4"},
        "after": {"pitch": "D4"},
    }
    response = client.post(f"/sessions/{session_id}/edits", json=payload)
    assert response.status_code == 422
    body = response.json()
    assert "before" in body["detail"].lower()
    assert "no coincide" in body["detail"].lower()

    # No se añadió al log
    detail = client.get(f"/sessions/{session_id}").json()
    assert detail["edits"] == []


def test_append_edit_non_applicable_op_returns_422(tmp_path: Path) -> None:
    client, session_id = _setup_api_client(tmp_path)

    # SetPitch con una altura no válida que falle en la proyección
    payload = {
        "base_seq": 0,
        "op": "SetPitch",
        "anchor": {
            "part": 0,
            "staff": 0,
            "staff_id": "part-0-staff-0",
            "measure": 1,
            "voice": 0,
            "event_index": 99,
        },
        "after": {"pitch": "D4"},
    }
    response = client.post(f"/sessions/{session_id}/edits", json=payload)
    assert response.status_code == 422


def test_append_edit_sequence_conflict_returns_409(tmp_path: Path) -> None:
    client, session_id = _setup_api_client(tmp_path)

    valid_payload = {
        "base_seq": 0,
        "op": "SetPitch",
        "anchor": {
            "part": 0,
            "staff": 0,
            "staff_id": "part-0-staff-0",
            "measure": 1,
            "voice": 0,
            "event_index": 0,
        },
        "before": {"pitch": "C4"},
        "after": {"pitch": "D4"},
    }

    # Primera edición exitosa
    resp1 = client.post(f"/sessions/{session_id}/edits", json=valid_payload)
    assert resp1.status_code == 201

    # Simular una colisión de secuencia en el repositorio (IntegrityError / SequenceConflict)
    with patch(
        "cadenza.persistence.SqlAlchemyEditEventRepository.append",
        side_effect=SequenceConflict(
            expected_seq=2,
            actual_seq=1,
            message="Conflicto de secuencia en concurrencia",
        ),
    ):
        resp_conflict = client.post(
            f"/sessions/{session_id}/edits",
            json={
                "base_seq": 1,
                "op": "SetPitch",
                "anchor": {
                    "part": 0,
                    "staff": 0,
                    "staff_id": "part-0-staff-0",
                    "measure": 1,
                    "voice": 0,
                    "event_index": 0,
                },
                "before": {"pitch": "D4"},
                "after": {"pitch": "E4"},
            },
        )
        assert resp_conflict.status_code == 409
        assert "conflicto de secuencia" in resp_conflict.json()["detail"].lower()
