"""La etapa del compás tras el OMR en la API (#237, ADR-0059 §4).

Con HOMR (sin motor inyectado), la API construye la etapa con los rasgos de
`CADENZA_OMR_METER_FEATURES`; con un motor inyectado (las pruebas), solo corre la etapa que se
inyecte, para que el doble de pruebas siga dando su partitura tal cual.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

import pytest
from cadenza.api import Settings, create_app
from cadenza.application import Role, User
from cadenza.omr import ALL_METER_FEATURES, MeterFeature, MeterStage
from cadenza.omr.testing import FakeOMREngine
from cadenza.persistence import (
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi.testclient import TestClient
from pydantic import ValidationError

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
)


def _settings(**overrides: Any) -> Settings:
    return Settings(auth_secret_key=secrets.token_urlsafe(32), **overrides)


def test_the_default_features_are_the_measured_ones() -> None:
    assert Settings().omr_meter_features == "numerator,symbol,implicit_tuplets"
    stage = Settings().build_meter_stage()
    assert stage is not None and stage.features == ALL_METER_FEATURES


def test_features_come_from_the_environment_and_none_turns_the_stage_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CADENZA_OMR_METER_FEATURES", "symbol")
    stage = Settings().build_meter_stage()
    assert stage is not None and stage.features == {MeterFeature.SYMBOL}

    monkeypatch.setenv("CADENZA_OMR_METER_FEATURES", "none")
    assert Settings().build_meter_stage() is None


def test_an_unknown_feature_stops_the_start() -> None:
    with pytest.raises(ValidationError, match="desconocidos"):
        Settings(omr_meter_features="numerador")


def test_with_homr_the_app_builds_the_stage_from_the_settings() -> None:
    app = create_app(
        create_session_factory(create_memory_engine()),
        settings=_settings(omr_meter_features="numerator"),
    )

    assert isinstance(app.state.meter_stage, MeterStage)
    assert app.state.meter_stage.features == {MeterFeature.NUMERATOR}


def test_an_injected_engine_runs_only_an_injected_stage() -> None:
    factory = create_session_factory(create_memory_engine())

    assert (
        create_app(factory, omr_engine=FakeOMREngine(), settings=_settings()).state.meter_stage
        is None
    )
    stage = MeterStage({MeterFeature.SYMBOL})
    app = create_app(factory, omr_engine=FakeOMREngine(), settings=_settings(), meter_stage=stage)
    assert app.state.meter_stage is stage


def test_the_transcription_goes_through_the_stage_and_keeps_it(tmp_path: Path) -> None:
    db_engine = create_memory_engine()
    create_schema(db_engine)
    factory = create_session_factory(db_engine)
    with factory() as db:
        SqlAlchemyUserRepository(db).add(
            User(id="u1", username="transcriptor1", password_hash="x", role=Role.TRANSCRIPTOR)
        )
        db.commit()
    app = create_app(
        factory,
        omr_engine=FakeOMREngine(),
        settings=_settings(artifacts_dir=tmp_path / "artifacts"),
        meter_stage=MeterStage({MeterFeature.SYMBOL}),
    )
    client = TestClient(app)
    token = app.state.token_service.create_access_token(user_id="u1", role=Role.TRANSCRIPTOR)
    client.headers["Authorization"] = f"Bearer {token}"

    response = client.post("/transcribe", files={"file": ("p.png", PNG_BYTES, "image/png")})

    assert response.status_code == 201
    session_id = response.json()["session_id"]
    detail = client.get(f"/sessions/{session_id}")
    assert detail.status_code == 200
    measures = detail.json()["document"]["score"]["parts"][0]["staves"][0]["measures"]
    assert {m["time_signature"]["symbol"] for m in measures} == {"common"}
    with factory() as db:
        stored = SqlAlchemySessionRepository(db).get(session_id)
    assert stored is not None
    assert stored.document["provenance"]["omr_stages"]["meter"]["features"] == ["symbol"]
