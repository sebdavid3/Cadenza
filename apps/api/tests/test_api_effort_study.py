"""Pruebas de endpoints para el protocolo de estudio de esfuerzo con participantes (#33, D38)."""

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
                id="usr-p01",
                username="P01",
                password_hash="hash1",
                role=Role.TRANSCRIPTOR,
                active=True,
            )
        )
        user_repo.add(
            User(
                id="usr-p02",
                username="P02",
                password_hash="hash2",
                role=Role.TRANSCRIPTOR,
                active=True,
            )
        )
        user_repo.add(
            User(
                id="usr-res",
                username="investigador",
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
        "p1": app.state.token_service.create_access_token(
            user_id="usr-p01", role=Role.TRANSCRIPTOR
        ),
        "p2": app.state.token_service.create_access_token(
            user_id="usr-p02", role=Role.TRANSCRIPTOR
        ),
        "res": app.state.token_service.create_access_token(
            user_id="usr-res", role=Role.INVESTIGADOR
        ),
    }

    return TestClient(app), tokens


def test_transcribe_unassisted_via_query_params(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)

    res = client.post(
        "/transcribe?condition=unassisted&test_score_id=TS-01",
        files={"file": ("score.png", PNG_BYTES, "image/png")},
        headers={"Authorization": f"Bearer {tokens['p1']}"},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["condition"] == "unassisted"
    assert data["test_score_id"] == "TS-01"
    assert data["findings_count"] == 0

    session_id = data["session_id"]
    get_res = client.get(
        f"/sessions/{session_id}",
        headers={"Authorization": f"Bearer {tokens['p1']}"},
    )
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["condition"] == "unassisted"
    assert detail["test_score_id"] == "TS-01"
    assert detail["owner_id"] == "usr-p01"
    assert len(detail["findings"]) == 0


def test_transcribe_unassisted_via_form_fields(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)

    res = client.post(
        "/transcribe",
        files={"file": ("score.png", PNG_BYTES, "image/png")},
        data={"condition": "no_asistida", "test_score_id": "TS-02"},
        headers={"Authorization": f"Bearer {tokens['p1']}"},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["condition"] == "unassisted"
    assert data["test_score_id"] == "TS-02"
    assert data["findings_count"] == 0


def test_transcribe_invalid_condition_returns_422(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)

    res = client.post(
        "/transcribe?condition=invalid_condition",
        files={"file": ("score.png", PNG_BYTES, "image/png")},
        headers={"Authorization": f"Bearer {tokens['p1']}"},
    )
    assert res.status_code == 422, res.text
    assert "Condición inválida" in res.json()["detail"]


def test_revalidate_unassisted_session_keeps_zero_findings(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)

    tx_res = client.post(
        "/transcribe?condition=unassisted&test_score_id=TS-01",
        files={"file": ("score.png", PNG_BYTES, "image/png")},
        headers={"Authorization": f"Bearer {tokens['p1']}"},
    )
    sess_id = tx_res.json()["session_id"]

    rev_res = client.post(
        f"/sessions/{sess_id}/validate",
        headers={"Authorization": f"Bearer {tokens['p1']}"},
    )
    assert rev_res.status_code == 200, rev_res.text
    assert len(rev_res.json()["findings"]) == 0


def test_list_sessions_filter_by_condition_and_score(tmp_path: Path) -> None:
    client, tokens = _setup_api(tmp_path)

    client.post(
        "/transcribe?condition=assisted&test_score_id=TS-01",
        files={"file": ("score.png", PNG_BYTES, "image/png")},
        headers={"Authorization": f"Bearer {tokens['p1']}"},
    )
    client.post(
        "/transcribe?condition=unassisted&test_score_id=TS-02",
        files={"file": ("score.png", PNG_BYTES, "image/png")},
        headers={"Authorization": f"Bearer {tokens['p1']}"},
    )

    # Filtrar por condición asistida
    res_ast = client.get(
        "/sessions?condition=assisted",
        headers={"Authorization": f"Bearer {tokens['res']}"},
    )
    assert res_ast.status_code == 200
    assert len(res_ast.json()) == 1
    assert res_ast.json()[0]["condition"] == "assisted"
    assert res_ast.json()[0]["test_score_id"] == "TS-01"

    # Filtrar por condición no asistida
    res_una = client.get(
        "/sessions?condition=unassisted",
        headers={"Authorization": f"Bearer {tokens['res']}"},
    )
    assert res_una.status_code == 200
    assert len(res_una.json()) == 1
    assert res_una.json()[0]["condition"] == "unassisted"
    assert res_una.json()[0]["test_score_id"] == "TS-02"

    # Filtrar por partitura de prueba
    res_ts2 = client.get(
        "/sessions?test_score_id=TS-02",
        headers={"Authorization": f"Bearer {tokens['res']}"},
    )
    assert res_ts2.status_code == 200
    assert len(res_ts2.json()) == 1
    assert res_ts2.json()[0]["test_score_id"] == "TS-02"
