"""La transacción de cada petición se confirma antes de enviar la respuesta (#166)."""

from __future__ import annotations

import secrets

from cadenza.api import Settings, create_app
from cadenza.persistence import create_memory_engine, create_schema
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from starlette.types import Message, Receive, Scope, Send

SECRET = secrets.token_hex(32)
ORIGIN = "http://localhost:5173"


def _settings() -> Settings:
    return Settings(auth_secret_key=SECRET, registration_enabled=True, cors_origins=[ORIGIN])


def _register_body() -> dict[str, str]:
    return {"username": f"u{secrets.token_hex(4)}", "password": secrets.token_urlsafe(12)}


def test_the_transaction_is_committed_before_the_response_starts() -> None:
    events: list[str] = []

    class RecordingSession(Session):
        def commit(self) -> None:
            events.append("commit")
            super().commit()

    engine = create_memory_engine()
    create_schema(engine)
    factory: sessionmaker[Session] = sessionmaker(
        bind=engine, expire_on_commit=False, class_=RecordingSession
    )
    app = create_app(factory, settings=_settings())

    # Envoltorio ASGI que anota cuándo empieza a salir la respuesta hacia el cliente. Se mide el
    # orden de los eventos y no la visibilidad de la fila: en SQLite, el RELEASE SAVEPOINT del
    # repositorio confirma por su cuenta (pysqlite no emite BEGIN), y en PostgreSQL no.
    async def spy_app(scope: Scope, receive: Receive, send: Send) -> None:
        async def spy_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                events.append("response")
            await send(message)

        await app(scope, receive, spy_send)

    response = TestClient(spy_app).post("/auth/register", json=_register_body())

    assert response.status_code == 201
    # El último commit va antes de que empiece la respuesta, y después ya no hay ninguno.
    assert "commit" in events
    assert events[-1] == "response"
    assert events.count("response") == 1


def test_a_failed_commit_is_an_error_not_a_success() -> None:
    class SessionThatCannotCommit(Session):
        def commit(self) -> None:
            raise OperationalError("COMMIT", {}, Exception("disco lleno"))

    engine = create_memory_engine()
    create_schema(engine)
    factory: sessionmaker[Session] = sessionmaker(
        bind=engine, expire_on_commit=False, class_=SessionThatCannotCommit
    )
    app = create_app(factory, settings=_settings())
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/auth/register", json=_register_body())

    # Antes, el 201 ya había salido cuando fallaba el commit: el cliente daba la cuenta por creada.
    assert response.status_code == 500
