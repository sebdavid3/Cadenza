"""Pruebas de seq de la sesión, base_seq en ediciones y concurrencia (Issue #48, ADR-0011)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


def _setup_client(tmp_path: Path) -> tuple[TestClient, str]:
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


def test_append_edit_requires_base_seq(tmp_path: Path) -> None:
    client, session_id = _setup_client(tmp_path)

    # Edición sin campo base_seq es rechazada con HTTP 422 por validación del esquema Pydantic
    payload_without_base_seq: dict[str, Any] = {
        "op": "SetPitch",
        "anchor": ANCHOR,
        "before": {"pitch": "C4"},
        "after": {"pitch": "D4"},
    }
    resp = client.post(f"/sessions/{session_id}/edits", json=payload_without_base_seq)
    assert resp.status_code == 422


def test_append_edit_mismatched_base_seq_returns_409(tmp_path: Path) -> None:
    client, session_id = _setup_client(tmp_path)

    # Sesión está en current_seq=0, pero cliente declara base_seq=5
    payload = {
        "base_seq": 5,
        "op": "SetPitch",
        "anchor": ANCHOR,
        "before": {"pitch": "C4"},
        "after": {"pitch": "D4"},
    }
    resp = client.post(f"/sessions/{session_id}/edits", json=payload)
    assert resp.status_code == 409
    assert "conflicto de secuencia" in resp.json()["detail"].lower()


def test_two_clients_concurrency_conflict_and_recovery(tmp_path: Path) -> None:
    """Dos clientes sobre la misma sesión: el segundo recibe 409 y tras recargar entra."""
    client, session_id = _setup_client(tmp_path)

    # Ambos clientes leen el estado inicial (current_seq = 0)
    session_c1 = client.get(f"/sessions/{session_id}").json()
    session_c2 = client.get(f"/sessions/{session_id}").json()
    assert session_c1["current_seq"] == 0
    assert session_c2["current_seq"] == 0
    assert session_c1["current_score"] is not None
    assert session_c1["anchor_index"] is not None

    # Cliente 1 envía su edición basada en base_seq=0 -> ÉXITO (201)
    edit1_payload = {
        "base_seq": 0,
        "op": "SetPitch",
        "anchor": ANCHOR,
        "before": {"pitch": "C4"},
        "after": {"pitch": "D4"},
    }
    resp1 = client.post(f"/sessions/{session_id}/edits", json=edit1_payload)
    assert resp1.status_code == 201
    assert resp1.json()["seq"] == 1

    # Cliente 2 intenta enviar su edición con base_seq=0 (preparada sobre el estado inicial)
    # Servidor la rechaza con 409 sin modificar el log ni reintentar silenciosamente (ADR-0011)
    edit2_obsolete_payload = {
        "base_seq": 0,
        "op": "SetPitch",
        "anchor": ANCHOR,
        "before": {"pitch": "C4"},
        "after": {"pitch": "E4"},
    }
    resp2_failed = client.post(
        f"/sessions/{session_id}/edits",
        json=edit2_obsolete_payload,
    )
    assert resp2_failed.status_code == 409
    assert "conflicto de secuencia" in resp2_failed.json()["detail"].lower()

    # Cliente 2 recarga la sesión con GET /sessions/{id}
    reloaded_c2 = client.get(f"/sessions/{session_id}").json()
    assert reloaded_c2["current_seq"] == 1
    # Verifica que el pitch actual en el estado 1 es D4
    first_event_pitch = reloaded_c2["current_score"]["parts"][0]["staves"][0]["measures"][0][
        "events"
    ][0]["pitch"]
    assert first_event_pitch == "D4"

    # Cliente 2 construye su edición sobre el estado actual (base_seq=1, before=D4)
    edit2_recovered_payload = {
        "base_seq": 1,
        "op": "SetPitch",
        "anchor": ANCHOR,
        "before": {"pitch": "D4"},
        "after": {"pitch": "E4"},
    }
    resp2_success = client.post(
        f"/sessions/{session_id}/edits",
        json=edit2_recovered_payload,
    )
    assert resp2_success.status_code == 201
    assert resp2_success.json()["seq"] == 2

    # El estado final de la sesión ahora es current_seq = 2
    final_session = client.get(f"/sessions/{session_id}").json()
    assert final_session["current_seq"] == 2
    assert len(final_session["edits"]) == 2
    final_pitch = final_session["current_score"]["parts"][0]["staves"][0]["measures"][0]["events"][
        0
    ]["pitch"]
    assert final_pitch == "E4"


def test_get_session_exposes_current_seq_and_anchor_index_with_inherited_attributes(
    tmp_path: Path,
) -> None:
    """Verifica que get_session expone current_seq y anchor_index con atributos heredados."""
    client, session_id = _setup_client(tmp_path)

    # Estado 0
    detail0 = client.get(f"/sessions/{session_id}").json()
    assert detail0["current_seq"] == 0
    assert detail0["current_score"] is not None
    assert detail0["anchor_index"] is not None
    assert len(detail0["anchor_index"]["entries"]) > 0

    # Edición
    client.post(
        f"/sessions/{session_id}/edits",
        json={
            "base_seq": 0,
            "op": "SetPitch",
            "anchor": ANCHOR,
            "before": {"pitch": "C4"},
            "after": {"pitch": "D4"},
        },
    )

    # Estado 1
    detail1 = client.get(f"/sessions/{session_id}").json()
    assert detail1["current_seq"] == 1
    assert (
        detail1["current_score"]["parts"][0]["staves"][0]["measures"][0]["events"][0]["pitch"]
        == "D4"
    )
    assert detail1["anchor_index"] is not None
    # El índice de anclas conserva las entradas
    entries = detail1["anchor_index"]["entries"]
    assert len(entries) > 0
