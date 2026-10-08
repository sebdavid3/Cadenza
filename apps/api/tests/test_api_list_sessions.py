"""Pruebas de integración de la API para el listado de sesiones GET /sessions.

Issue #27, ADR-0009, ADR-0012.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cadenza.api import Settings, create_app
from cadenza.application import Role, User
from cadenza.domain import ScoreDocument, build_anchor_index
from cadenza.omr import FakeOMREngine, OMREngine
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from cadenza.persistence.models import Session as SessionRecord
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
)


class _UnbalancedEngine(OMREngine):
    """Fake con el primer compás desbalanceado para ejercitar hallazgos."""

    def __init__(self) -> None:
        self._fake = FakeOMREngine()

    @property
    def engine_id(self) -> str:
        return "fake-unbalanced"

    def transcribe(self, image_path: Path) -> ScoreDocument:
        document = self._fake.transcribe(image_path)
        part = document.score.parts[0]
        staff = part.staves[0]
        measures = staff.measures
        broken = replace(measures[0], events=measures[0].events[:-1])
        new_staff = replace(staff, measures=(broken, *measures[1:]))
        score = replace(document.score, parts=(replace(part, staves=(new_staff,)),))
        return replace(document, score=score, anchors=build_anchor_index(score))


def _setup_api(
    tmp_path: Path,
    omr_engine: OMREngine | None = None,
) -> tuple[TestClient, dict[str, str], sessionmaker[DbSession]]:
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
        omr_engine=omr_engine or FakeOMREngine(),
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

    return TestClient(app), tokens, session_factory


def test_list_sessions_empty_returns_empty_list(tmp_path: Path) -> None:
    client, tokens, _ = _setup_api(tmp_path)
    res = client.get("/sessions", headers={"Authorization": f"Bearer {tokens['t1']}"})
    assert res.status_code == 200
    assert res.json() == []


def test_list_sessions_unauthenticated_returns_401(tmp_path: Path) -> None:
    client, _, _ = _setup_api(tmp_path)
    res = client.get("/sessions")
    assert res.status_code == 401


def test_list_sessions_role_visibility_and_fields(tmp_path: Path) -> None:
    client, tokens, _ = _setup_api(tmp_path)
    h_t1 = {"Authorization": f"Bearer {tokens['t1']}"}
    h_t2 = {"Authorization": f"Bearer {tokens['t2']}"}
    h_inv = {"Authorization": f"Bearer {tokens['inv']}"}

    # Transcriptor 1 crea 2 sesiones
    files = {"file": ("score1.png", PNG_BYTES, "image/png")}
    res_s1 = client.post("/transcribe", files=files, headers=h_t1)
    assert res_s1.status_code == 201
    s1_id = res_s1.json()["session_id"]

    res_s2 = client.post("/transcribe", files=files, headers=h_t1)
    assert res_s2.status_code == 201
    s2_id = res_s2.json()["session_id"]

    # Transcriptor 2 crea 1 sesión
    res_s3 = client.post("/transcribe", files=files, headers=h_t2)
    assert res_s3.status_code == 201
    s3_id = res_s3.json()["session_id"]

    # Transcriptor 1 solo ve s1 y s2
    res_list_t1 = client.get("/sessions", headers=h_t1)
    assert res_list_t1.status_code == 200
    items_t1 = res_list_t1.json()
    assert len(items_t1) == 2
    session_ids_t1 = {item["session_id"] for item in items_t1}
    assert session_ids_t1 == {s1_id, s2_id}

    # Verificar estructura del resumen: campos presentes y ausencia de 'document'
    first = items_t1[0]
    assert "session_id" in first
    assert "document_id" in first
    assert "omr_engine" in first
    assert "status" in first
    assert "created_at" in first
    assert "findings_count" in first
    assert "edits_count" in first
    assert "document" not in first  # No carga el JSONB pesado

    # Transcriptor 2 solo ve s3
    res_list_t2 = client.get("/sessions", headers=h_t2)
    assert res_list_t2.status_code == 200
    items_t2 = res_list_t2.json()
    assert len(items_t2) == 1
    assert items_t2[0]["session_id"] == s3_id

    # Investigador ve las 3 sesiones
    res_list_inv = client.get("/sessions", headers=h_inv)
    assert res_list_inv.status_code == 200
    items_inv = res_list_inv.json()
    assert len(items_inv) == 3
    assert {item["session_id"] for item in items_inv} == {s1_id, s2_id, s3_id}


def test_list_sessions_pagination_and_ordering(tmp_path: Path) -> None:
    client, tokens, session_factory = _setup_api(tmp_path)
    h_t1 = {"Authorization": f"Bearer {tokens['t1']}"}

    # Crear 3 sesiones con t1
    ids: list[str] = []
    base_time = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    for i in range(3):
        files = {"file": (f"score{i}.png", PNG_BYTES, "image/png")}
        r = client.post("/transcribe", files=files, headers=h_t1)
        assert r.status_code == 201
        ids.append(r.json()["session_id"])

    # Fijar created_at distintos en la base de datos para probar orden determinista
    with session_factory() as db:
        for i, sid in enumerate(ids):
            rec = db.get(SessionRecord, sid)
            if rec:
                rec.created_at = base_time + timedelta(hours=i)
        db.commit()

    # Orden descendente: el último creado debe aparecer primero
    res_all = client.get("/sessions", headers=h_t1)
    assert res_all.status_code == 200
    all_items = res_all.json()
    assert [item["session_id"] for item in all_items] == [ids[2], ids[1], ids[0]]

    # Paginación: limit=1, offset=0
    p1 = client.get("/sessions?limit=1&offset=0", headers=h_t1).json()
    assert len(p1) == 1
    assert p1[0]["session_id"] == ids[2]

    # Paginación: limit=1, offset=1
    p2 = client.get("/sessions?limit=1&offset=1", headers=h_t1).json()
    assert len(p2) == 1
    assert p2[0]["session_id"] == ids[1]

    # Paginación: limit=1, offset=2
    p3 = client.get("/sessions?limit=1&offset=2", headers=h_t1).json()
    assert len(p3) == 1
    assert p3[0]["session_id"] == ids[0]


def test_list_sessions_filter_by_status(tmp_path: Path) -> None:
    client, tokens, _ = _setup_api(tmp_path)
    h_t1 = {"Authorization": f"Bearer {tokens['t1']}"}

    # Crear 2 sesiones
    files = {"file": ("score.png", PNG_BYTES, "image/png")}
    s1_id = client.post("/transcribe", files=files, headers=h_t1).json()["session_id"]
    s2_id = client.post("/transcribe", files=files, headers=h_t1).json()["session_id"]

    # Finalizar s1
    res_final = client.post(f"/sessions/{s1_id}/finalize", headers=h_t1)
    assert res_final.status_code == 200

    # Filtrar solo finalizadas
    res_finalized = client.get("/sessions?status=finalized", headers=h_t1).json()
    assert len(res_finalized) == 1
    assert res_finalized[0]["session_id"] == s1_id
    assert res_finalized[0]["status"] == "finalized"

    # Filtrar solo transcritas
    res_tx = client.get("/sessions?status=transcribed", headers=h_t1).json()
    assert len(res_tx) == 1
    assert res_tx[0]["session_id"] == s2_id
    assert res_tx[0]["status"] == "transcribed"


def test_list_sessions_counts_findings_and_edits_via_api(tmp_path: Path) -> None:
    client, tokens, _ = _setup_api(tmp_path, omr_engine=_UnbalancedEngine())
    h_t1 = {"Authorization": f"Bearer {tokens['t1']}"}

    # Transcribir con _UnbalancedEngine genera un hallazgo activo (at_seq=0)
    files = {"file": ("score.png", PNG_BYTES, "image/png")}
    res_tx = client.post("/transcribe", files=files, headers=h_t1)
    assert res_tx.status_code == 201
    sid = res_tx.json()["session_id"]

    # Antes de editar: 1 hallazgo, 0 ediciones
    items = client.get("/sessions", headers=h_t1).json()
    assert len(items) == 1
    assert items[0]["findings_count"] == 1
    assert items[0]["edits_count"] == 0

    # Aplicar una edición válida
    edit_payload = {
        "base_seq": 0,
        "anchor": {
            "part": 0,
            "staff": 0,
            "measure": 1,
            "voice": 0,
            "event_index": 0,
            "staff_id": "part-0-staff-0",
        },
        "op": "SetPitch",
        "before": {"pitch": "C4"},
        "after": {"pitch": "D4"},
    }
    res_edit = client.post(f"/sessions/{sid}/edits", json=edit_payload, headers=h_t1)
    assert res_edit.status_code == 201

    # Tras editar: 1 hallazgo activo (validated_at_seq=0), 1 edición
    items_after = client.get("/sessions", headers=h_t1).json()
    assert len(items_after) == 1
    assert items_after[0]["findings_count"] == 1
    assert items_after[0]["edits_count"] == 1
