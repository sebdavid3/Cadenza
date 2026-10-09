"""Pruebas de integración HTTP para descarte y restauración de hallazgos (#36).

Valida:
- Descarte de hallazgos como falsos positivos (POST /sessions/{id}/findings/{finding_id}/dismiss).
- Restauración de hallazgos a estado activo (POST /sessions/{id}/findings/{finding_id}/restore).
- Filtrado por defecto en GET /sessions/{id}/findings (include_dismissed=False).
- Preservación de falsos positivos en revalidación (POST /sessions/{id}/validate) si el
  evento no fue modificado tras el descarte.
- Reactivación del hallazgo en revalidación si el evento fue modificado tras el descarte.
- Control de autorización ADR-0012 (transcriptor ajeno 404, investigador ajeno 403, dueño 200).
- Verificación de ciclo de vida ADR-0014 (sesión finalizada responde 409 SessionClosed).
"""

from __future__ import annotations

import time
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

ANCHOR_M1 = {
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


class MultiMeasureUnbalancedOMR(OMREngine):
    """OMR determinista con compases 1 y 2 desbalanceados (3 tiempos en 4/4)."""

    @property
    def engine_id(self) -> str:
        return "multi-unbalanced-fake"

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
        m2 = Measure(
            number=2,
            events=(
                Event(kind=EventKind.NOTE, voice=0, pitch="F4", duration_beats=Fraction(1)),
                Event(kind=EventKind.NOTE, voice=0, pitch="G4", duration_beats=Fraction(1)),
                Event(kind=EventKind.NOTE, voice=0, pitch="A4", duration_beats=Fraction(1)),
            ),
            time_signature=TimeSignature(4, 4),
        )
        score = ScoreIR(
            parts=(Part(id="part-0", staves=(Staff(id="part-0-staff-0", measures=(m1, m2)),)),)
        )
        return ScoreDocument(
            id="doc-multi-unbalanced",
            score=score,
            anchors=build_anchor_index(score),
            provenance=Provenance(omr_engine=self.engine_id, model_version=self.model_version),
        )


def _setup_environment(
    tmp_path: Path,
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
        omr_engine=MultiMeasureUnbalancedOMR(),
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


def test_dismiss_and_restore_finding_flow(tmp_path: Path) -> None:
    client, tokens = _setup_environment(tmp_path)
    client.headers["Authorization"] = f"Bearer {tokens['owner']}"

    # 1. Transcribir
    resp = client.post("/transcribe", files={"file": ("score.png", PNG_BYTES, "image/png")})
    assert resp.status_code == 201
    session_id = resp.json()["session_id"]

    # 2. Listar hallazgos iniciales
    resp_findings = client.get(f"/sessions/{session_id}/findings")
    assert resp_findings.status_code == 200
    findings = resp_findings.json()
    assert len(findings) == 2  # compás 1 y compás 2 desbalanceados
    finding_id = findings[0]["id"]
    assert findings[0]["status"] == "active"
    assert findings[0]["dismissed_at"] is None

    # 3. Descartar hallazgo con motivo
    dismiss_resp = client.post(
        f"/sessions/{session_id}/findings/{finding_id}/dismiss",
        json={"reason": "Compás anacrúsico deliberado"},
    )
    assert dismiss_resp.status_code == 200
    dismissed = dismiss_resp.json()
    assert dismissed["id"] == finding_id
    assert dismissed["status"] == "dismissed"
    assert dismissed["dismissed_by"] == "transcriptor1"
    assert dismissed["dismissal_reason"] == "Compás anacrúsico deliberado"
    assert dismissed["dismissed_at"] is not None

    # 4. GET /sessions/{id}/findings no lo incluye por defecto
    active_resp = client.get(f"/sessions/{session_id}/findings")
    assert active_resp.status_code == 200
    active_findings = active_resp.json()
    assert len(active_findings) == 1
    assert active_findings[0]["id"] != finding_id

    # 5. GET /sessions/{id}/findings?include_dismissed=true sí lo incluye
    all_resp = client.get(f"/sessions/{session_id}/findings?include_dismissed=true")
    assert all_resp.status_code == 200
    all_findings = all_resp.json()
    assert len(all_findings) == 2
    match_dismissed = next(f for f in all_findings if f["id"] == finding_id)
    assert match_dismissed["status"] == "dismissed"

    # 6. GET /sessions cuenta solo activos en findings_count
    sessions_resp = client.get("/sessions")
    assert sessions_resp.status_code == 200
    session_summary = next(s for s in sessions_resp.json() if s["session_id"] == session_id)
    assert session_summary["findings_count"] == 1

    # 7. Restaurar hallazgo
    restore_resp = client.post(f"/sessions/{session_id}/findings/{finding_id}/restore")
    assert restore_resp.status_code == 200
    restored = restore_resp.json()
    assert restored["id"] == finding_id
    assert restored["status"] == "active"
    assert restored["dismissed_at"] is None
    assert restored["dismissed_by"] is None
    assert restored["dismissal_reason"] is None

    # 8. Ahora vuelve a aparecer en la lista por defecto
    active_resp_after = client.get(f"/sessions/{session_id}/findings")
    assert len(active_resp_after.json()) == 2


def test_revalidation_preserves_dismissed_finding_if_event_not_modified(tmp_path: Path) -> None:
    client, tokens = _setup_environment(tmp_path)
    client.headers["Authorization"] = f"Bearer {tokens['owner']}"

    # 1. Transcribir
    resp = client.post("/transcribe", files={"file": ("score.png", PNG_BYTES, "image/png")})
    session_id = resp.json()["session_id"]

    findings = client.get(f"/sessions/{session_id}/findings").json()
    # Identificar hallazgo de compás 1
    m1_finding = next(f for f in findings if f["anchor"]["measure"] == 1)
    m1_finding_id = m1_finding["id"]

    # 2. Descartar hallazgo de compás 1
    client.post(
        f"/sessions/{session_id}/findings/{m1_finding_id}/dismiss",
        json={"reason": "Falso positivo confirmado en M1"},
    )

    # 3. Revalidar sin modificaciones en compás 1 (de hecho, sin ninguna edición)
    val_resp = client.post(f"/sessions/{session_id}/validate")
    assert val_resp.status_code == 200
    active_findings = val_resp.json()["findings"]
    # El hallazgo de M1 NO debe reaparecer como activo
    assert len(active_findings) == 1
    assert active_findings[0]["anchor"]["measure"] == 2

    # Verificar que en la base de datos se preservó como descartado
    all_findings = client.get(f"/sessions/{session_id}/findings?include_dismissed=true").json()
    m1_preserved = next(f for f in all_findings if f["anchor"]["measure"] == 1)
    assert m1_preserved["status"] == "dismissed"
    assert m1_preserved["dismissal_reason"] == "Falso positivo confirmado en M1"


def test_revalidation_reactivates_finding_if_event_modified_after_dismissal(tmp_path: Path) -> None:
    client, tokens = _setup_environment(tmp_path)
    client.headers["Authorization"] = f"Bearer {tokens['owner']}"

    # 1. Transcribir
    resp = client.post("/transcribe", files={"file": ("score.png", PNG_BYTES, "image/png")})
    session_id = resp.json()["session_id"]

    findings = client.get(f"/sessions/{session_id}/findings").json()
    m1_finding = next(f for f in findings if f["anchor"]["measure"] == 1)
    m1_finding_id = m1_finding["id"]

    # 2. Descartar hallazgo de compás 1
    client.post(
        f"/sessions/{session_id}/findings/{m1_finding_id}/dismiss",
        json={"reason": "Descarte temporal"},
    )

    # Esperar un breve instante para garantizar monotonicidad de created_at
    time.sleep(0.01)

    # 3. Editar el evento señalado en el ancla (SetPitch en compás 1, evento 0)
    edit_resp = client.post(
        f"/sessions/{session_id}/edits",
        json={
            "base_seq": 0,
            "op": "SetPitch",
            "anchor": ANCHOR_M1,
            "before": {"pitch": "C4"},
            "after": {"pitch": "D4"},
        },
    )
    assert edit_resp.status_code == 201

    # 4. Revalidar: como el evento fue modificado con posterioridad al descarte,
    # el hallazgo de compás 1 SÍ debe reactivarse y reaparecer como activo.
    val_resp = client.post(f"/sessions/{session_id}/validate")
    assert val_resp.status_code == 200
    active_findings = val_resp.json()["findings"]
    measures_with_findings = [f["anchor"]["measure"] for f in active_findings]
    assert 1 in measures_with_findings
    assert 2 in measures_with_findings


def test_authorization_controls_for_dismiss_and_restore(tmp_path: Path) -> None:
    client, tokens = _setup_environment(tmp_path)

    # Dueño crea la sesión
    client.headers["Authorization"] = f"Bearer {tokens['owner']}"
    resp = client.post("/transcribe", files={"file": ("score.png", PNG_BYTES, "image/png")})
    session_id = resp.json()["session_id"]
    finding_id = client.get(f"/sessions/{session_id}/findings").json()[0]["id"]

    # 1. Transcriptor ajeno responde 404 (ADR-0012)
    client.headers["Authorization"] = f"Bearer {tokens['other']}"
    assert client.post(f"/sessions/{session_id}/findings/{finding_id}/dismiss").status_code == 404
    assert client.post(f"/sessions/{session_id}/findings/{finding_id}/restore").status_code == 404

    # 2. Investigador ajeno responde 403 (ADR-0012)
    client.headers["Authorization"] = f"Bearer {tokens['researcher']}"
    assert client.post(f"/sessions/{session_id}/findings/{finding_id}/dismiss").status_code == 403
    assert client.post(f"/sessions/{session_id}/findings/{finding_id}/restore").status_code == 403

    # 3. Dueño responde 200
    client.headers["Authorization"] = f"Bearer {tokens['owner']}"
    assert client.post(f"/sessions/{session_id}/findings/{finding_id}/dismiss").status_code == 200
    assert client.post(f"/sessions/{session_id}/findings/{finding_id}/restore").status_code == 200


def test_finalized_session_lifecycle_check(tmp_path: Path) -> None:
    client, tokens = _setup_environment(tmp_path)
    client.headers["Authorization"] = f"Bearer {tokens['owner']}"

    resp = client.post("/transcribe", files={"file": ("score.png", PNG_BYTES, "image/png")})
    session_id = resp.json()["session_id"]
    finding_id = client.get(f"/sessions/{session_id}/findings").json()[0]["id"]

    # Finalizar sesión
    fin_resp = client.post(f"/sessions/{session_id}/finalize")
    assert fin_resp.status_code == 200

    # Intentar descartar o restaurar en sesión finalizada responde 409 (ADR-0014)
    dismiss_closed = client.post(f"/sessions/{session_id}/findings/{finding_id}/dismiss")
    assert dismiss_closed.status_code == 409
    assert "finalizada" in dismiss_closed.json()["detail"]

    restore_closed = client.post(f"/sessions/{session_id}/findings/{finding_id}/restore")
    assert restore_closed.status_code == 409
    assert "finalizada" in restore_closed.json()["detail"]


def test_nonexistent_session_or_finding_returns_404(tmp_path: Path) -> None:
    client, tokens = _setup_environment(tmp_path)
    client.headers["Authorization"] = f"Bearer {tokens['owner']}"

    resp = client.post("/transcribe", files={"file": ("score.png", PNG_BYTES, "image/png")})
    session_id = resp.json()["session_id"]

    # Sesión inexistente
    assert client.post("/sessions/nonexistent/findings/1/dismiss").status_code == 404
    assert client.post("/sessions/nonexistent/findings/1/restore").status_code == 404

    # Finding inexistente
    f_resp = client.post(f"/sessions/{session_id}/findings/99999/dismiss")
    assert f_resp.status_code == 404
    assert f_resp.json()["detail"] == "finding not found"

    f_restore = client.post(f"/sessions/{session_id}/findings/99999/restore")
    assert f_restore.status_code == 404
    assert f_restore.json()["detail"] == "finding not found"
