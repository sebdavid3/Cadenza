"""Un sustituto suelto en un JSON responde 422 y no 500 (#295).

`"\\ud800"` es un escape JSON válido, pero su carácter no se puede codificar en UTF-8. El
manejador de errores de validación de FastAPI repite la entrada en la respuesta y fallaba al
codificarla, en cualquier endpoint JSON. La respuesta conserva la forma de FastAPI.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

import pytest
from cadenza.api import Settings, create_app
from cadenza.application import Role, User
from cadenza.omr.testing import FakeOMREngine
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
LONE_SURROGATE = "\ud800"
JSON_HEADERS = {"Content-Type": "application/json"}


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    engine = create_memory_engine()
    create_schema(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as db:
        SqlAlchemyUserRepository(db).add(
            User(id="u1", username="transcriptor1", password_hash="x", role=Role.TRANSCRIPTOR)
        )
        db.commit()
    app = create_app(
        session_factory,
        omr_engine=FakeOMREngine(),
        settings=Settings(
            auth_secret_key="secret-key-at-least-32-bytes-long-for-testing",
            artifacts_dir=tmp_path / "artifacts",
            registration_enabled=True,
            cors_origins=["http://localhost:5173"],
        ),
    )
    token = app.state.token_service.create_access_token(user_id="u1", role=Role.TRANSCRIPTOR)
    test_client = TestClient(app, raise_server_exceptions=False)
    test_client.headers["Authorization"] = f"Bearer {token}"
    return test_client


def _post_json(client: TestClient, url: str, body: dict[str, Any]) -> Any:
    # `json.dumps` escapa el sustituto como `\ud800`, igual que un navegador con `JSON.stringify`.
    return client.post(url, content=json.dumps(body).encode("ascii"), headers=JSON_HEADERS)


def test_lone_surrogate_in_register_returns_422(client: TestClient) -> None:
    response = _post_json(
        client,
        "/auth/register",
        {"username": LONE_SURROGATE, "password": secrets.token_urlsafe(16)},
    )

    assert response.status_code == 422
    (error,) = [e for e in response.json()["detail"] if e["loc"] == ["body", "username"]]
    assert error["input"] == LONE_SURROGATE


def test_lone_surrogate_as_key_returns_422(client: TestClient) -> None:
    response = _post_json(client, "/auth/register", {LONE_SURROGATE: "x"})

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_lone_surrogate_in_edit_returns_422(client: TestClient) -> None:
    created = client.post("/transcribe", files={"file": ("score.png", PNG_BYTES, "image/png")})
    session_id = created.json()["session_id"]

    response = _post_json(
        client,
        f"/sessions/{session_id}/edits",
        {"base_seq": 0, "op": LONE_SURROGATE, "anchor": {}},
    )

    assert response.status_code == 422
    locs = [error["loc"] for error in response.json()["detail"]]
    assert ["body", "op"] in locs


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ({"pitch": LONE_SURROGATE}, {"pitch": "D4"}),
        (None, {"pitch": "D4", f"x{LONE_SURROGATE}": 1}),
    ],
    ids=["en-before", "en-clave-de-after"],
)
def test_lone_surrogate_repeated_by_an_invalid_edit_returns_422(
    client: TestClient, before: dict[str, Any] | None, after: dict[str, Any]
) -> None:
    """`before` y `after` admiten cualquier valor; el 422 de `InvalidEdit` los repite."""

    created = client.post("/transcribe", files={"file": ("score.png", PNG_BYTES, "image/png")})
    session_id = created.json()["session_id"]
    detail = client.get(f"/sessions/{session_id}").json()
    anchor = detail["anchor_index"]["entries"][0]["anchor"]

    response = _post_json(
        client,
        f"/sessions/{session_id}/edits",
        {"base_seq": 0, "op": "SetPitch", "anchor": anchor, "before": before, "after": after},
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_validation_error_keeps_utf8_when_it_can(client: TestClient) -> None:
    """Sin sustitutos, el 422 de validación no cambia: UTF-8 sin escapar."""

    response = _post_json(client, "/auth/register", {"username": ["Íncipit"]})

    assert response.status_code == 422
    assert "Íncipit".encode() in response.content
