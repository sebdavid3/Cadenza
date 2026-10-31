"""La capa de sugerencias en la API (ADR-0036 §4, §5, §8, §12)."""

from __future__ import annotations

import json
import logging
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from cadenza.api import Settings, create_app
from cadenza.application import Role, SuggestionModelVersionData, User
from cadenza.domain import (
    Event,
    EventKind,
    KeySignature,
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
    FilesystemArtifactStore,
    SqlAlchemySuggestionModelRegistry,
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from cadenza.validation.learned import (
    ARTIFACT_FORMAT,
    ARTIFACT_FORMAT_VERSION,
    FEATURE_VERSION,
    MODEL_TYPE,
)
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
SECRET = "secret-key-at-least-32-bytes-long-for-testing"


class FMajorEngine(OMREngine):
    """Fa mayor: en el compás 1 faltan dos tiempos; en el 2, un Si natural que las reglas no
    ven y que la capa sabe que suele ser Si bemol."""

    @property
    def engine_id(self) -> str:
        return "fake"

    def transcribe(self, image_path: Path) -> ScoreDocument:
        def notes(*pitches: str) -> tuple[Event, ...]:
            return tuple(
                Event(kind=EventKind.NOTE, pitch=p, duration_beats=Fraction(1)) for p in pitches
            )

        measures = (
            Measure(
                number=1,
                events=notes("F4", "A4"),
                time_signature=TimeSignature(4, 4),
                key_signature=KeySignature(fifths=-1),
            ),
            Measure(number=2, events=notes("C5", "B4", "A4", "G4")),
        )
        score = ScoreIR(parts=(Part(id="P1", staves=(Staff(id="P1-S1", measures=measures),)),))
        return ScoreDocument(
            id="doc",
            score=score,
            anchors=build_anchor_index(score),
            provenance=Provenance(omr_engine="fake"),
        )


def _artifact() -> dict[str, Any]:
    return {
        "format": ARTIFACT_FORMAT,
        "format_version": ARTIFACT_FORMAT_VERSION,
        "model_type": MODEL_TYPE,
        "feature_version": FEATURE_VERSION,
        "params": {"alpha": 1.0, "min_support": 5},
        "families": {
            "accidental": {
                "levels": [["acc_vs_key"], []],
                "tables": [
                    {"against_key": {"=key": 40, "none": 10}, "in_key": {"none": 900}},
                    {"": {"none": 910, "=key": 40}},
                ],
                "threshold": 0.5,
                "high_threshold": 0.7,
                "active": True,
            },
            "duration": {
                "levels": [["balance_sign"], []],
                "tables": [{"under": {"x2": 6, "none": 4}}, {"": {"none": 900, "x2": 10}}],
                "threshold": None,
                "high_threshold": None,
                "active": False,
            },
        },
    }


def _factory() -> sessionmaker[DbSession]:
    engine = create_memory_engine()
    create_schema(engine)
    factory = create_session_factory(engine)
    with factory() as db:
        users = SqlAlchemyUserRepository(db)
        users.add(User(id="u1", username="ana", password_hash="h", role=Role.TRANSCRIPTOR))
        users.add(User(id="u2", username="inv", password_hash="h", role=Role.INVESTIGADOR))
        db.commit()
    return factory


def _promote(
    factory: sessionmaker[DbSession],
    artifacts: Path,
    content: bytes,
    *,
    feature_version: int = FEATURE_VERSION,
    tamper: bool = False,
) -> None:
    with factory() as db:
        store = FilesystemArtifactStore(artifacts, session=db)
        digest = store.put(content, kind="suggestion_model", media_type="application/json")
        if tamper:
            store.resolve_path(digest).write_bytes(content + b" ")
        registry = SqlAlchemySuggestionModelRegistry(db)
        registry.register(
            SuggestionModelVersionData(
                version="sug-1",
                artifact_hash=digest,
                dataset_hash="d" * 64,
                config_hash="c" * 64,
                seed=42,
                model_type=MODEL_TYPE,
                feature_version=feature_version,
                metrics={},
            )
        )
        registry.promote("sug-1")
        db.commit()


def _app(
    tmp_path: Path,
    *,
    enabled: bool,
    promote: bool = True,
    settings: dict[str, Any] | None = None,
    **promote_kwargs: Any,
) -> tuple[TestClient, dict[str, dict[str, str]], Any]:
    factory = _factory()
    artifacts = tmp_path / "artifacts"
    if promote:
        _promote(factory, artifacts, json.dumps(_artifact()).encode(), **promote_kwargs)
    app = create_app(
        factory,
        omr_engine=FMajorEngine(),
        settings=Settings(
            auth_secret_key=SECRET,
            artifacts_dir=artifacts,
            suggestions_enabled=enabled,
            **(settings or {}),
        ),
    )
    service = app.state.token_service
    headers = {
        "owner": {
            "Authorization": "Bearer "
            + service.create_access_token(user_id="u1", role=Role.TRANSCRIPTOR)
        },
        "researcher": {
            "Authorization": "Bearer "
            + service.create_access_token(user_id="u2", role=Role.INVESTIGADOR)
        },
    }
    return TestClient(app), headers, app


def _transcribe(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/transcribe", files={"file": ("p.png", PNG, "image/png")}, headers=headers
    )
    assert response.status_code == 201, response.text
    return str(response.json()["session_id"])


def test_switch_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CADENZA_SUGGESTIONS_ENABLED", raising=False)
    assert Settings(auth_secret_key=SECRET).suggestions_enabled is False
    monkeypatch.setenv("CADENZA_SUGGESTIONS_ENABLED", "true")
    assert Settings(auth_secret_key=SECRET).suggestions_enabled is True


def test_with_the_switch_off_findings_carry_no_suggestions(tmp_path: Path) -> None:
    client, headers, app = _app(tmp_path, enabled=False)
    assert app.state.suggestion_model is None
    session_id = _transcribe(client, headers["owner"])
    findings = client.get(f"/sessions/{session_id}/findings", headers=headers["owner"]).json()
    assert [f["rule_id"] for f in findings] == ["measure.balance"]
    assert findings[0]["suggestions"] == []
    detail = client.get(f"/sessions/{session_id}", headers=headers["owner"]).json()
    assert detail["document"]["provenance"].get("suggestions_version") is None


# Mostrarlo todo: cualquier nivel y todas las familias.
SHOW_ALL = {
    "suggestions_min_level": "medium",
    "suggestions_families": "accidental,duration,pitch,delete,insertion",
}


def test_the_promoted_layer_is_loaded_and_suggests(tmp_path: Path) -> None:
    client, headers, app = _app(tmp_path, enabled=True, settings=SHOW_ALL)
    assert app.state.suggestion_model is not None
    assert app.state.suggestion_model.version == "sug-1"
    session_id = _transcribe(client, headers["owner"])
    findings = client.get(f"/sessions/{session_id}/findings", headers=headers["owner"]).json()
    by_rule = {f["rule_id"]: f for f in findings}
    assert set(by_rule) == {"measure.balance", "learned.accidental"}
    balance = by_rule["measure.balance"]["suggestions"]
    assert 1 <= len(balance) <= 3
    assert balance[0]["source"] == "learned" and balance[0]["response"] is None
    (fix,) = by_rule["learned.accidental"]["suggestions"]
    assert (fix["op"], fix["after"], fix["before"]) == (
        "SetAccidental",
        {"accidental": "b"},
        {"accidental": ""},
    )
    assert fix["confidence_level"] == "high" and fix["model_version"] == "sug-1"
    assert by_rule["learned.accidental"]["anchor"]["measure"] == 2
    detail = client.get(f"/sessions/{session_id}", headers=headers["owner"]).json()
    assert detail["document"]["provenance"]["suggestions_version"] == "sug-1"
    assert {f["rule_id"] for f in detail["findings"]} == set(by_rule)


def test_the_policy_defaults_to_high_accidentals(monkeypatch: pytest.MonkeyPatch) -> None:
    """La decisión del responsable (#244): la condición asistida solo muestra las
    sugerencias de alteración de confianza alta (ADR-0036, enmienda 19)."""
    for name in ("CADENZA_SUGGESTIONS_MIN_LEVEL", "CADENZA_SUGGESTIONS_FAMILIES"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(auth_secret_key=SECRET)
    assert (settings.suggestions_min_level, settings.suggestions_families) == (
        "high",
        "accidental",
    )
    monkeypatch.setenv("CADENZA_SUGGESTIONS_MIN_LEVEL", "medium")
    monkeypatch.setenv("CADENZA_SUGGESTIONS_FAMILIES", "accidental,duration")
    settings = Settings(auth_secret_key=SECRET)
    assert (settings.suggestions_min_level, settings.suggestions_families) == (
        "medium",
        "accidental,duration",
    )


def test_by_default_only_high_accidentals_are_shown(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="cadenza.api.suggestions"):
        client, headers, app = _app(tmp_path, enabled=True)
    assert app.state.suggestion_model is not None
    assert app.state.suggestion_model.version == "sug-1"
    assert "policy_min_level=high policy_families=accidental" in caplog.text
    session_id = _transcribe(client, headers["owner"])
    findings = client.get(f"/sessions/{session_id}/findings", headers=headers["owner"]).json()
    by_rule = {f["rule_id"]: f for f in findings}
    # El hallazgo de la regla sigue, sin sus candidatos de duración ni de inserción.
    assert set(by_rule) == {"measure.balance", "learned.accidental"}
    assert by_rule["measure.balance"]["suggestions"] == []
    (fix,) = by_rule["learned.accidental"]["suggestions"]
    assert (fix["op"], fix["confidence_level"]) == ("SetAccidental", "high")
    detail = client.get(f"/sessions/{session_id}", headers=headers["owner"]).json()
    assert detail["document"]["provenance"]["suggestions_version"] == "sug-1"


def test_learned_findings_of_a_family_not_allowed_are_not_emitted(tmp_path: Path) -> None:
    # Solo duración, y de confianza alta: la duración del artefacto no tiene umbral de
    # confianza alta, así que sus candidatos de `measure.balance` son `medium`.
    client, headers, _ = _app(
        tmp_path,
        enabled=True,
        settings={"suggestions_min_level": "high", "suggestions_families": "duration"},
    )
    session_id = _transcribe(client, headers["owner"])
    findings = client.get(f"/sessions/{session_id}/findings", headers=headers["owner"]).json()
    assert [(f["rule_id"], f["suggestions"]) for f in findings] == [("measure.balance", [])]


@pytest.mark.parametrize(
    "settings",
    [
        {"suggestions_min_level": "low"},
        {"suggestions_families": ""},
        {"suggestions_families": "accidental,tempo"},
    ],
)
def test_an_invalid_policy_validates_without_the_layer_and_logs_why(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, settings: dict[str, Any]
) -> None:
    with caplog.at_level(logging.WARNING, logger="cadenza.api.suggestions"):
        client, headers, app = _app(tmp_path, enabled=True, settings=settings)
    assert app.state.suggestion_model is None
    assert "reason=invalid_policy" in caplog.text
    session_id = _transcribe(client, headers["owner"])
    findings = client.get(f"/sessions/{session_id}/findings", headers=headers["owner"]).json()
    assert [(f["rule_id"], f["suggestions"]) for f in findings] == [("measure.balance", [])]


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"promote": False}, "no_promoted_version"),
        ({"tamper": True}, "invalid_artifact"),
        ({"feature_version": FEATURE_VERSION + 1}, "feature_version"),
    ],
)
def test_an_unusable_layer_validates_without_it_and_logs_why(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, kwargs: dict[str, Any], reason: str
) -> None:
    with caplog.at_level(logging.WARNING, logger="cadenza.api.suggestions"):
        client, headers, app = _app(tmp_path, enabled=True, **kwargs)
    assert app.state.suggestion_model is None
    assert f"reason={reason}" in caplog.text
    session_id = _transcribe(client, headers["owner"])
    findings = client.get(f"/sessions/{session_id}/findings", headers=headers["owner"]).json()
    assert [(f["rule_id"], f["suggestions"]) for f in findings] == [("measure.balance", [])]


def _learned(client: TestClient, headers: dict[str, str], session_id: str) -> dict[str, Any]:
    findings = client.get(f"/sessions/{session_id}/findings", headers=headers).json()
    return next(f for f in findings if f["rule_id"] == "learned.accidental")


def test_applying_a_suggestion_and_the_order_of_errors(tmp_path: Path) -> None:
    client, headers, _ = _app(tmp_path, enabled=True)
    owner = headers["owner"]
    session_id = _transcribe(client, owner)
    (fix,) = _learned(client, owner, session_id)["suggestions"]
    body = {"base_seq": 0, "op": fix["op"], "anchor": fix["anchor"], "after": fix["after"]}
    url = f"/sessions/{session_id}/edits"

    stale_seq = client.post(url, json={**body, "base_seq": 3, "suggestion_id": 999}, headers=owner)
    assert stale_seq.status_code == 409 and stale_seq.json()["detail"] != "stale_suggestion"
    stale = client.post(url, json={**body, "suggestion_id": 999}, headers=owner)
    assert (stale.status_code, stale.json()) == (409, {"detail": "stale_suggestion"})
    other = client.post(
        url, json={**body, "after": {"accidental": "#"}, "suggestion_id": fix["id"]}, headers=owner
    )
    assert other.status_code == 422

    applied = client.post(url, json={**body, "suggestion_id": fix["id"]}, headers=owner)
    assert applied.status_code == 201, applied.text
    edit = applied.json()
    assert edit["author"] == "ana" and edit["seq"] == 1
    again = client.post(
        url, json={**body, "base_seq": 1, "suggestion_id": fix["id"]}, headers=owner
    )
    assert (again.status_code, again.json()) == (409, {"detail": "stale_suggestion"})
    # La respuesta guardada se ve en los hallazgos de esa validación.
    at_zero = client.get(
        f"/sessions/{session_id}/findings", params={"at_seq": 0}, headers=owner
    ).json()
    learned = next(f for f in at_zero if f["rule_id"] == "learned.accidental")
    assert learned["suggestions"][0]["response"] == "accepted"
    # Deshacer es una edición normal.
    undo = client.post(f"/sessions/{session_id}/undo", json={"base_seq": 1}, headers=owner)
    assert undo.status_code == 200, undo.text


def test_rejecting_a_suggestion(tmp_path: Path) -> None:
    client, headers, _ = _app(tmp_path, enabled=True)
    owner = headers["owner"]
    session_id = _transcribe(client, owner)
    (fix,) = _learned(client, owner, session_id)["suggestions"]
    url = f"/sessions/{session_id}/suggestions/{fix['id']}/reject"

    assert client.post(url, headers=headers["researcher"]).status_code == 403
    missing = client.post(f"/sessions/{session_id}/suggestions/999/reject", headers=owner)
    assert (missing.status_code, missing.json()) == (404, {"detail": "suggestion not found"})
    rejected = client.post(url, headers=owner)
    assert rejected.status_code == 200
    assert rejected.json()["response"] == "rejected"
    assert client.post(url, headers=owner).status_code == 200
    # Rechazar no descarta el hallazgo.
    assert _learned(client, owner, session_id)["status"] == "active"
    # La revalidación del mismo estado hereda el rechazo en la sugerencia nueva.
    revalidated = client.post(f"/sessions/{session_id}/validate", headers=owner).json()
    learned = next(f for f in revalidated["findings"] if f["rule_id"] == "learned.accidental")
    assert learned["suggestions"][0]["id"] != fix["id"]
    assert learned["suggestions"][0]["response"] == "rejected"

    finalized = client.post(f"/sessions/{session_id}/finalize", headers=owner)
    assert finalized.status_code == 200
    assert client.post(url, headers=owner).status_code == 409


def test_rejecting_an_applied_suggestion_is_a_conflict(tmp_path: Path) -> None:
    client, headers, _ = _app(tmp_path, enabled=True)
    owner = headers["owner"]
    session_id = _transcribe(client, owner)
    (fix,) = _learned(client, owner, session_id)["suggestions"]
    body = {
        "base_seq": 0,
        "op": fix["op"],
        "anchor": fix["anchor"],
        "after": fix["after"],
        "suggestion_id": fix["id"],
    }
    assert client.post(f"/sessions/{session_id}/edits", json=body, headers=owner).status_code == 201
    response = client.post(f"/sessions/{session_id}/suggestions/{fix['id']}/reject", headers=owner)
    assert response.status_code == 409


def test_the_contract_grows_compatibly() -> None:
    from cadenza.api.schemas import EditEventCreate, FindingRead, ProvenancePayload

    assert EditEventCreate.model_fields["suggestion_id"].default is None
    assert FindingRead.model_fields["suggestions"].default_factory is not None
    assert ProvenancePayload.model_fields["suggestions_version"].default is None
    spec = json.loads(
        (Path(__file__).resolve().parents[3] / "docs" / "api" / "openapi.json").read_text(
            encoding="utf-8"
        )
    )
    assert "/sessions/{session_id}/suggestions/{suggestion_id}/reject" in spec["paths"]
    assert "SuggestionRead" in spec["components"]["schemas"]
    finding = spec["components"]["schemas"]["FindingRead"]
    assert "suggestions" not in finding.get("required", [])
