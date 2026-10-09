"""Pruebas de la API para revalidación tras correcciones (Issue #11, ADR-0013)."""

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
from cadenza.omr import FakeOMREngine, OMREngine
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


class UnbalancedOMREngine(OMREngine):
    """OMR determinista que produce 3 tiempos en un compás de 4/4."""

    @property
    def engine_id(self) -> str:
        return "unbalanced-fake"

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
            id="doc-unbalanced-api",
            score=score,
            anchors=build_anchor_index(score),
            provenance=Provenance(omr_engine=self.engine_id, model_version=self.model_version),
        )


def _setup_environment(
    tmp_path: Path,
    omr_engine: OMREngine,
) -> tuple[TestClient, dict[str, str]]:
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
        omr_engine=omr_engine,
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

    client = TestClient(app)
    return client, tokens


def test_revalidate_resolves_error_via_api(tmp_path: Path) -> None:
    client, tokens = _setup_environment(tmp_path, UnbalancedOMREngine())
    client.headers["Authorization"] = f"Bearer {tokens['owner']}"

    # 1. Transcribir documento desbalanceado
    upload_resp = client.post(
        "/transcribe",
        files={"file": ("score.png", PNG_BYTES, "image/png")},
    )
    assert upload_resp.status_code == 201
    session_id = upload_resp.json()["session_id"]
    assert upload_resp.json()["findings_count"] == 1

    # 2. Verificar hallazgo inicial
    findings_resp = client.get(f"/sessions/{session_id}/findings")
    assert findings_resp.status_code == 200
    initial_findings = findings_resp.json()
    assert len(initial_findings) == 1
    assert initial_findings[0]["at_seq"] == 0
    assert initial_findings[0]["rule_id"] == "measure.balance"

    # 3. Corregir compás con edición (base_seq=0, SetDuration de C4 de 1 a 2)
    edit_resp = client.post(
        f"/sessions/{session_id}/edits",
        json={
            "base_seq": 0,
            "op": "SetDuration",
            "anchor": ANCHOR,
            "after": {"duration_beats": "2"},
        },
    )
    assert edit_resp.status_code == 201
    assert edit_resp.json()["seq"] == 1

    # 4. Antes de revalidar, el hallazgo anterior sigue visible
    pre_val = client.get(f"/sessions/{session_id}/findings")
    assert len(pre_val.json()) == 1

    # 5. POST /sessions/{id}/validate
    val_resp = client.post(f"/sessions/{session_id}/validate")
    assert val_resp.status_code == 200
    val_data = val_resp.json()
    assert val_data["session_id"] == session_id
    assert val_data["current_seq"] == 1
    assert len(val_data["findings"]) == 0  # Eliminado tras corrección

    # 6. GET /sessions/{id} y GET /sessions/{id}/findings reflejan 0 hallazgos activos
    session_detail = client.get(f"/sessions/{session_id}").json()
    assert len(session_detail["findings"]) == 0
    assert session_detail["current_seq"] == 1

    active_findings = client.get(f"/sessions/{session_id}/findings").json()
    assert len(active_findings) == 0

    # 7. Los hallazgos anteriores se conservan para análisis de esfuerzo (latest_only=false)
    history_resp = client.get(f"/sessions/{session_id}/findings?latest_only=false")
    assert history_resp.status_code == 200
    assert len(history_resp.json()) == 1
    assert history_resp.json()[0]["at_seq"] == 0

    seq0_resp = client.get(f"/sessions/{session_id}/findings?at_seq=0")
    assert len(seq0_resp.json()) == 1

    seq1_resp = client.get(f"/sessions/{session_id}/findings?at_seq=1")
    assert len(seq1_resp.json()) == 0


def test_revalidate_detects_new_error_introduced_by_edit_via_api(tmp_path: Path) -> None:
    client, tokens = _setup_environment(tmp_path, FakeOMREngine())
    client.headers["Authorization"] = f"Bearer {tokens['owner']}"

    # 1. Transcripción balanceada
    upload_resp = client.post(
        "/transcribe",
        files={"file": ("score.png", PNG_BYTES, "image/png")},
    )
    session_id = upload_resp.json()["session_id"]
    assert upload_resp.json()["findings_count"] == 0

    # 2. Edición que rompe el balance del compás 1
    edit_resp = client.post(
        f"/sessions/{session_id}/edits",
        json={
            "base_seq": 0,
            "op": "SetDuration",
            "anchor": ANCHOR,
            "after": {"duration_beats": "3"},
        },
    )
    assert edit_resp.status_code == 201
    assert edit_resp.json()["seq"] == 1

    # 3. POST /sessions/{id}/validate
    val_resp = client.post(f"/sessions/{session_id}/validate")
    assert val_resp.status_code == 200
    val_data = val_resp.json()
    assert val_data["current_seq"] == 1
    assert len(val_data["findings"]) == 1
    assert val_data["findings"][0]["at_seq"] == 1
    assert val_data["findings"][0]["rule_id"] == "measure.balance"

    # 4. Los hallazgos vigentes ahora muestran el nuevo hallazgo
    cur_findings = client.get(f"/sessions/{session_id}/findings").json()
    assert len(cur_findings) == 1
    assert cur_findings[0]["at_seq"] == 1


def test_revalidate_authorization(tmp_path: Path) -> None:
    client, tokens = _setup_environment(tmp_path, FakeOMREngine())

    # Transcribir con el dueño
    client.headers["Authorization"] = f"Bearer {tokens['owner']}"
    upload_resp = client.post(
        "/transcribe",
        files={"file": ("score.png", PNG_BYTES, "image/png")},
    )
    session_id = upload_resp.json()["session_id"]

    # Sin autenticación: 401
    client.headers.pop("Authorization")
    unauth_resp = client.post(f"/sessions/{session_id}/validate")
    assert unauth_resp.status_code == 401

    # Transcriptor ajeno: 404 (ADR-0012)
    client.headers["Authorization"] = f"Bearer {tokens['other']}"
    forbidden_resp = client.post(f"/sessions/{session_id}/validate")
    assert forbidden_resp.status_code == 404

    # Investigador: 200
    client.headers["Authorization"] = f"Bearer {tokens['researcher']}"
    inv_resp = client.post(f"/sessions/{session_id}/validate")
    assert inv_resp.status_code == 200
    assert inv_resp.json()["session_id"] == session_id


def test_revalidate_idempotent_multiple_calls_same_seq(tmp_path: Path) -> None:
    client, tokens = _setup_environment(tmp_path, UnbalancedOMREngine())
    client.headers["Authorization"] = f"Bearer {tokens['owner']}"

    # 1. Transcribir con 1 hallazgo inicial en seq=0
    upload_resp = client.post(
        "/transcribe",
        files={"file": ("score.png", PNG_BYTES, "image/png")},
    )
    session_id = upload_resp.json()["session_id"]
    assert upload_resp.json()["findings_count"] == 1

    # 2. Llamar a /validate dos veces sobre seq=0 sin haber editado
    val1 = client.post(f"/sessions/{session_id}/validate")
    assert val1.status_code == 200
    assert len(val1.json()["findings"]) == 1

    val2 = client.post(f"/sessions/{session_id}/validate")
    assert val2.status_code == 200
    assert len(val2.json()["findings"]) == 1

    # Los hallazgos vigentes siguen siendo 1
    cur = client.get(f"/sessions/{session_id}/findings").json()
    assert len(cur) == 1

    # El historial total no tiene copias duplicadas del seq=0
    all_findings = client.get(f"/sessions/{session_id}/findings?latest_only=false").json()
    assert len(all_findings) == 1
