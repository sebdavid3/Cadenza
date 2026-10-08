"""Pruebas de integración HTTP para esfuerzo (#13, ADR-0004, ADR-0012)."""

from __future__ import annotations

from pathlib import Path

from cadenza.api import Settings, create_app
from cadenza.application import Role, User, compute_interventions_from_edits, contrast_interventions
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


def test_record_effort_requires_authentication(tmp_path: Path) -> None:
    client, _ = _setup_api(tmp_path)
    res = client.post(
        "/sessions/any-session/effort",
        json={"duration_ms": 30000},
    )
    assert res.status_code == 401


def test_record_effort_success_and_get_list(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    session_id = _create_session(client, tokens["t1"])

    # 1. Registrar esfuerzo
    payload = {
        "duration_ms": 45000,
        "time_to_first_edit_ms": 12000,
        "interventions": {"1": 3, "2": 1},
    }
    res = client.post(
        f"/sessions/{session_id}/effort",
        json=payload,
        headers={"Authorization": f"Bearer {tokens['t1']}"},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["session_id"] == session_id
    assert data["duration_ms"] == 45000
    assert data["time_to_first_edit_ms"] == 12000
    assert data["interventions"] == {"1": 3, "2": 1}
    assert "id" in data
    assert "created_at" in data

    # 2. Consultar lista vía GET /sessions/{id}/effort
    get_res = client.get(
        f"/sessions/{session_id}/effort",
        headers={"Authorization": f"Bearer {tokens['t1']}"},
    )
    assert get_res.status_code == 200
    metrics_list = get_res.json()
    assert len(metrics_list) == 1
    assert metrics_list[0]["id"] == data["id"]
    assert metrics_list[0]["duration_ms"] == 45000


def test_record_effort_other_transcriptor_returns_404(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    session_id = _create_session(client, tokens["t1"])

    # t2 intenta registrar esfuerzo en la sesión de t1 -> 404
    res = client.post(
        f"/sessions/{session_id}/effort",
        json={"duration_ms": 20000},
        headers={"Authorization": f"Bearer {tokens['t2']}"},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "session not found"

    # t2 intenta consultar esfuerzo en la sesión de t1 -> 404
    get_res = client.get(
        f"/sessions/{session_id}/effort",
        headers={"Authorization": f"Bearer {tokens['t2']}"},
    )
    assert get_res.status_code == 404


def test_record_effort_other_investigator_returns_403(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    session_id = _create_session(client, tokens["t1"])

    # Dueño registra una medición
    client.post(
        f"/sessions/{session_id}/effort",
        json={"duration_ms": 20000},
        headers={"Authorization": f"Bearer {tokens['t1']}"},
    )

    # Investigador intenta mutar / registrar esfuerzo en sesión ajena -> 403 Forbidden
    res = client.post(
        f"/sessions/{session_id}/effort",
        json={"duration_ms": 20000},
        headers={"Authorization": f"Bearer {tokens['inv']}"},
    )
    assert res.status_code == 403
    assert "investigador" in res.json()["detail"].lower()

    # Investigador consulta métricas de sesión ajena -> 200 OK (ADR-0012)
    get_res = client.get(
        f"/sessions/{session_id}/effort",
        headers={"Authorization": f"Bearer {tokens['inv']}"},
    )
    assert get_res.status_code == 200
    assert len(get_res.json()) == 1


def test_record_effort_investigator_own_session_allowed(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    # Investigador crea su propia sesión
    session_id = _create_session(client, tokens["inv"])

    res = client.post(
        f"/sessions/{session_id}/effort",
        json={"duration_ms": 15000},
        headers={"Authorization": f"Bearer {tokens['inv']}"},
    )
    assert res.status_code == 201
    assert res.json()["duration_ms"] == 15000


def test_record_effort_session_not_found(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    res = client.post(
        "/sessions/non-existent-session/effort",
        json={"duration_ms": 1000},
        headers={"Authorization": f"Bearer {tokens['t1']}"},
    )
    assert res.status_code == 404


def test_record_effort_validation_errors(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    session_id = _create_session(client, tokens["t1"])

    # 1. duration_ms < 0 -> 422
    res1 = client.post(
        f"/sessions/{session_id}/effort",
        json={"duration_ms": -10},
        headers={"Authorization": f"Bearer {tokens['t1']}"},
    )
    assert res1.status_code == 422

    # 2. time_to_first_edit_ms < 0 -> 422
    res2 = client.post(
        f"/sessions/{session_id}/effort",
        json={"duration_ms": 1000, "time_to_first_edit_ms": -1},
        headers={"Authorization": f"Bearer {tokens['t1']}"},
    )
    assert res2.status_code == 422

    # 3. campo desconocido (extra='forbid') -> 422
    res3 = client.post(
        f"/sessions/{session_id}/effort",
        json={"duration_ms": 1000, "unknown_field": "test"},
        headers={"Authorization": f"Bearer {tokens['t1']}"},
    )
    assert res3.status_code == 422


def test_contrast_effort_with_session_edits(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)
    session_id = _create_session(client, tokens["t1"])

    # 1. Realizar dos ediciones en el compás 1 y una en el compás 2
    # Obtener estado de la sesión para anclas
    sess_res = client.get(
        f"/sessions/{session_id}",
        headers={"Authorization": f"Bearer {tokens['t1']}"},
    )
    assert sess_res.status_code == 200
    sess_data = sess_res.json()
    anchor_payload_1 = {
        "part": 0,
        "staff": 0,
        "measure": 1,
        "voice": 0,
        "event_index": 0,
        "staff_id": sess_data["current_score"]["parts"][0]["staves"][0]["id"],
    }

    # Primera edición (compás 1)
    e1_res = client.post(
        f"/sessions/{session_id}/edits",
        json={
            "base_seq": 0,
            "anchor": anchor_payload_1,
            "op": "SetPitch",
            "after": {"pitch": "E4"},
        },
        headers={"Authorization": f"Bearer {tokens['t1']}"},
    )
    assert e1_res.status_code == 201

    # Segunda edición (compás 1)
    e2_res = client.post(
        f"/sessions/{session_id}/edits",
        json={
            "base_seq": 1,
            "anchor": anchor_payload_1,
            "op": "SetPitch",
            "after": {"pitch": "F4"},
        },
        headers={"Authorization": f"Bearer {tokens['t1']}"},
    )
    assert e2_res.status_code == 201

    # 2. Registrar esfuerzo con intervenciones reportadas (compás 1: 2 intervenciones)
    reported_interventions = {"1": 2}
    effort_res = client.post(
        f"/sessions/{session_id}/effort",
        json={
            "duration_ms": 25000,
            "time_to_first_edit_ms": 7000,
            "interventions": reported_interventions,
        },
        headers={"Authorization": f"Bearer {tokens['t1']}"},
    )
    assert effort_res.status_code == 201

    # 3. Contrastar intervenciones reportadas con edit_events registrados
    updated_sess_res = client.get(
        f"/sessions/{session_id}",
        headers={"Authorization": f"Bearer {tokens['t1']}"},
    )
    edits_logged = updated_sess_res.json()["edits"]
    assert len(edits_logged) == 2

    # Verificar función de cálculo
    computed = compute_interventions_from_edits(edits_logged)
    assert computed == {"1": 2}

    # Contrastar
    comparison = contrast_interventions(reported_interventions, edits_logged)
    assert len(comparison) == 1
    assert comparison[0].measure == "1"
    assert comparison[0].matches
    assert comparison[0].reported_count == 2
    assert comparison[0].logged_count == 2
