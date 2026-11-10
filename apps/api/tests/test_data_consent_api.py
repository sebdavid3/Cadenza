"""Permiso de uso de los datos al registrarse y desde «Tu cuenta» (#378, ADR-0064)."""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime
from pathlib import Path

from cadenza.api import Settings, create_app
from cadenza.application import DATA_CONSENT_VERSION, Role, User
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

SECRET = secrets.token_hex(32)
PASSWORD = secrets.token_urlsafe(12)
NOW = datetime(2026, 11, 9, 18, 30, tzinfo=UTC)
WEB_CONSENT = Path(__file__).resolve().parents[3] / "apps/web/src/pages/consent/consent.ts"


def _app(*, enabled: bool = True) -> FastAPI:
    engine = create_memory_engine()
    create_schema(engine)
    settings = Settings(
        auth_secret_key=SECRET,
        registration_enabled=enabled,
        cors_origins=["https://cadenza.test"],
    )
    app = create_app(create_session_factory(engine), settings=settings)
    app.state.clock = lambda: NOW
    return app


def _token(app: FastAPI, user_id: str) -> str:
    token: str = app.state.token_service.create_access_token(
        user_id=user_id, role=Role.TRANSCRIPTOR
    )
    return token


def _register(client: TestClient, username: str, **extra: object) -> dict[str, object]:
    response = client.post(
        "/auth/register", json={"username": username, "password": PASSWORD, **extra}
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def test_registering_with_the_permission_records_when_and_which_text() -> None:
    app = _app()
    client = TestClient(app)

    user = _register(client, "ana", data_consent_version=DATA_CONSENT_VERSION)

    assert user["data_consent"] is True
    assert user["data_consent_version"] == DATA_CONSENT_VERSION
    assert user["data_consent_at"] is not None
    assert str(user["data_consent_at"]).startswith("2026-11-09T18:30")
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {_token(app, str(user['id']))}"})
    assert me.json()["data_consent"] is True
    # El permiso no cambia que las cuentas del registro queden fuera del estudio.
    assert me.json()["self_registered"] is True


def test_registering_without_the_permission_creates_the_account_without_it() -> None:
    client = TestClient(_app())

    user = _register(client, "luis")

    assert user["data_consent"] is False
    assert user["data_consent_at"] is None
    assert user["data_consent_version"] is None


def test_a_permission_for_another_text_is_refused_and_creates_nothing() -> None:
    client = TestClient(_app())

    refused = client.post(
        "/auth/register",
        json={"username": "eva", "password": PASSWORD, "data_consent_version": "2020-01-01"},
    )

    assert refused.status_code == 409
    assert refused.json()["detail"] == "stale_data_consent"
    # El nombre sigue libre: no se creó la cuenta.
    assert _register(client, "eva")["username"] == "eva"


def test_with_the_registration_closed_nothing_changes() -> None:
    client = TestClient(_app(enabled=False))

    response = client.post(
        "/auth/register",
        json={
            "username": "ana",
            "password": PASSWORD,
            "data_consent_version": DATA_CONSENT_VERSION,
        },
    )

    assert response.status_code == 404


def test_the_permission_is_given_and_withdrawn_from_the_account() -> None:
    app = _app()
    client = TestClient(app)
    user = _register(client, "ana")
    headers = {"Authorization": f"Bearer {_token(app, str(user['id']))}"}

    given = client.put(
        "/auth/data-consent",
        json={"granted": True, "version": DATA_CONSENT_VERSION},
        headers=headers,
    )
    assert given.status_code == 200
    assert given.json()["data_consent"] is True

    withdrawn = client.put("/auth/data-consent", json={"granted": False}, headers=headers)
    assert withdrawn.status_code == 200
    assert withdrawn.json()["data_consent"] is False
    assert withdrawn.json()["data_consent_at"] is None
    assert client.get("/auth/me", headers=headers).json()["data_consent"] is False


def test_giving_it_needs_the_current_text_and_a_session() -> None:
    app = _app()
    client = TestClient(app)
    user = _register(client, "ana")
    headers = {"Authorization": f"Bearer {_token(app, str(user['id']))}"}

    stale = client.put(
        "/auth/data-consent", json={"granted": True, "version": "2020-01-01"}, headers=headers
    )
    missing = client.put("/auth/data-consent", json={"granted": True}, headers=headers)
    extra = client.put("/auth/data-consent", json={"granted": False, "otro": 1}, headers=headers)
    anonymous = client.put("/auth/data-consent", json={"granted": False})

    assert stale.status_code == 409
    assert missing.status_code == 409
    assert extra.status_code == 422
    assert anonymous.status_code == 401
    assert client.get("/auth/me", headers=headers).json()["data_consent"] is False


def test_accounts_created_by_a_researcher_can_give_it_too() -> None:
    app = _app(enabled=False)
    with app.state.session_factory() as db:
        SqlAlchemyUserRepository(db).add(
            User(id="usr-p", username="participante", password_hash="-", role=Role.TRANSCRIPTOR)
        )
        db.commit()
    client = TestClient(app, headers={"Authorization": f"Bearer {_token(app, 'usr-p')}"})

    assert client.get("/auth/me").json()["data_consent"] is False
    given = client.put(
        "/auth/data-consent", json={"granted": True, "version": DATA_CONSENT_VERSION}
    )

    assert given.status_code == 200
    assert given.json()["data_consent"] is True


def test_a_permission_for_an_older_text_is_no_longer_current() -> None:
    app = _app(enabled=False)
    with app.state.session_factory() as db:
        SqlAlchemyUserRepository(db).add(
            User(
                id="usr-v",
                username="veterana",
                password_hash="-",
                role=Role.TRANSCRIPTOR,
                data_consent_at=NOW,
                data_consent_version="2020-01-01",
            )
        )
        db.commit()
    client = TestClient(app, headers={"Authorization": f"Bearer {_token(app, 'usr-v')}"})

    me = client.get("/auth/me").json()

    assert me["data_consent"] is False
    assert me["data_consent_version"] == "2020-01-01"


def test_the_web_shows_the_same_version_of_the_text() -> None:
    # El texto vive en la web; si cambia, cambian las dos versiones (ADR-0064).
    source = WEB_CONSENT.read_text(encoding="utf-8")
    match = re.search(r'export const DATA_CONSENT_VERSION = "([^"]+)";', source)

    assert match is not None
    assert match.group(1) == DATA_CONSENT_VERSION


def test_changing_the_password_or_the_account_keeps_the_permission() -> None:
    app = _app()
    client = TestClient(app)
    user = _register(client, "ana", data_consent_version=DATA_CONSENT_VERSION)
    headers = {"Authorization": f"Bearer {_token(app, str(user['id']))}"}
    new_password = secrets.token_urlsafe(12)

    changed = client.post(
        "/auth/password",
        json={"current_password": PASSWORD, "new_password": new_password},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    with app.state.session_factory() as db:
        SqlAlchemyUserRepository(db).add(
            User(id="inv-1", username="investigadora", password_hash="-", role=Role.INVESTIGADOR)
        )
        db.commit()
    researcher = app.state.token_service.create_access_token(
        user_id="inv-1", role=Role.INVESTIGADOR
    )
    edited = client.patch(
        f"/users/{user['id']}",
        json={"active": True},
        headers={"Authorization": f"Bearer {researcher}"},
    )
    assert edited.status_code == 200, edited.text

    me = client.get("/auth/me", headers=headers).json()
    assert me["data_consent"] is True
    assert me["data_consent_version"] == DATA_CONSENT_VERSION
