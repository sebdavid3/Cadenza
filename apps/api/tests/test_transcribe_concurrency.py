"""Tope de transcripciones simultáneas de la API (#165, ADR-0024)."""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import sqlite3
import threading
from pathlib import Path

import httpx
import pytest
from cadenza.api import Settings, create_app
from cadenza.api.transcription_slots import TranscriptionSlots, run_in_transcription_slot
from cadenza.application import Role, User
from cadenza.domain import ScoreDocument
from cadenza.omr import OMREngine
from cadenza.omr.testing import FakeOMREngine
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_engine_for_url,
    create_schema,
    create_session_factory,
)
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.types import Message

SECRET = secrets.token_hex(32)


class _BlockingEngine(OMREngine):
    """Doble que se queda calculando hasta que la prueba lo suelta."""

    def __init__(self) -> None:
        self._fake = FakeOMREngine()
        self.started = threading.Event()
        self.release = threading.Event()

    @property
    def engine_id(self) -> str:
        return "fake-blocking"

    def transcribe(self, image_path: Path) -> ScoreDocument:
        self.started.set()
        assert self.release.wait(10)
        return self._fake.transcribe(image_path)


def _app(db_path: Path, engine: OMREngine, max_concurrency: int) -> tuple[FastAPI, str]:
    db = create_engine_for_url(f"sqlite+pysqlite:///{db_path.as_posix()}")
    create_schema(db)
    session_factory = create_session_factory(db)
    with session_factory() as session:
        SqlAlchemyUserRepository(session).add(
            User(
                id="usr-tr",
                username="tr",
                password_hash="-",
                role=Role.TRANSCRIPTOR,
                active=True,
            )
        )
        session.commit()
    settings = Settings(auth_secret_key=SECRET, transcribe_max_concurrency=max_concurrency)
    app = create_app(session_factory, omr_engine=engine, settings=settings)
    token: str = app.state.token_service.create_access_token(
        user_id="usr-tr", role=Role.TRANSCRIPTOR
    )
    return app, token


def _upload() -> dict[str, tuple[str, bytes, str]]:
    return {"file": ("score.png", b"\x89PNG\r\n\x1a\n", "image/png")}


def _slot_is_free(slots: TranscriptionSlots) -> bool:
    if slots.semaphore.acquire(blocking=False):
        slots.semaphore.release()
        return True
    return False


def test_transcribe_answers_503_while_the_slots_are_busy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("cadenza.api.transcription_slots.SLOT_WAIT_SECONDS", 0.3)
    engine = _BlockingEngine()
    app, token = _app(tmp_path / "c.db", engine, max_concurrency=1)
    client = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    statuses: list[int] = []
    first = threading.Thread(
        target=lambda: statuses.append(client.post("/transcribe", files=_upload()).status_code)
    )
    first.start()
    try:
        assert engine.started.wait(10)

        busy = client.post("/transcribe", files=_upload())

        assert busy.status_code == 503
        assert busy.headers["Retry-After"] == "10"
        assert "ocupado" in busy.json()["detail"]
    finally:
        engine.release.set()
        first.join(10)
    assert statuses == [201]
    # Terminado el cálculo, el hueco vuelve a estar libre.
    assert client.post("/transcribe", files=_upload()).status_code == 201


def test_a_cancelled_request_still_saves_its_transcription(tmp_path: Path) -> None:
    # Si la petición se cancela mientras HOMR calcula (el cliente se va, el servidor se apaga),
    # el trabajo no puede quedarse con la sesión de base de datos de la petición, ya cerrada:
    # termina con la suya, confirma y libera el hueco.
    db_path = tmp_path / "c.db"
    engine = _BlockingEngine()
    app, token = _app(db_path, engine, max_concurrency=1)
    slots: TranscriptionSlots = app.state.transcription_slots
    request = httpx.Request(
        "POST",
        "http://testserver/transcribe",
        files=_upload(),
        headers={"Authorization": f"Bearer {token}"},
    )
    body = request.read()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/transcribe",
        "raw_path": b"/transcribe",
        "root_path": "",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in request.headers.items()],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    sent: list[Message] = []

    async def scenario() -> tuple[bool, bool]:
        delivered = asyncio.Event()

        async def receive() -> Message:
            if not delivered.is_set():
                delivered.set()
                return {"type": "http.request", "body": body, "more_body": False}
            await asyncio.Event().wait()
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            sent.append(message)

        task = asyncio.create_task(app(scope, receive, send))
        assert await asyncio.to_thread(engine.started.wait, 10)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        held_while_running = not _slot_is_free(slots)

        engine.release.set()
        for _ in range(250):
            if _slot_is_free(slots):
                return held_while_running, True
            await asyncio.sleep(0.02)
        return held_while_running, False

    held_while_running, freed_after = asyncio.run(scenario())

    assert not any(message["type"] == "http.response.start" for message in sent)
    assert held_while_running
    assert freed_after
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        (sessions,) = conn.execute("SELECT count(*) FROM sessions").fetchone()
    assert sessions == 1


def test_a_cancelled_request_keeps_its_slot_until_the_work_ends() -> None:
    async def scenario() -> tuple[bool, bool]:
        slots = TranscriptionSlots(1)
        started = threading.Event()
        release = threading.Event()

        def work() -> str:
            started.set()
            release.wait(5)
            return "ok"

        task = asyncio.create_task(run_in_transcription_slot(slots, work, wait_seconds=0.1))
        await asyncio.to_thread(started.wait, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        held_while_running = not _slot_is_free(slots)

        release.set()
        for _ in range(250):
            if _slot_is_free(slots):
                return held_while_running, True
            await asyncio.sleep(0.02)
        return held_while_running, False

    held_while_running, freed_after = asyncio.run(scenario())

    assert held_while_running
    assert freed_after


def test_a_request_cancelled_before_its_work_starts_frees_its_slot() -> None:
    # El trabajo espera en la cola del grupo de hilos (aquí, detrás de otro que ocupa el único
    # hilo): si la petición se cancela antes de que empiece, nunca se ejecutará y el hueco se
    # libera en ese momento.
    async def scenario() -> tuple[bool, bool]:
        slots = TranscriptionSlots(1)
        blocker_release = threading.Event()
        slots.executor.submit(blocker_release.wait, 5)
        ran = threading.Event()

        task = asyncio.create_task(run_in_transcription_slot(slots, ran.set, wait_seconds=0.1))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        freed = _slot_is_free(slots)
        blocker_release.set()
        await asyncio.sleep(0.2)
        return freed, ran.is_set()

    freed, ran = asyncio.run(scenario())

    assert freed
    assert not ran


def test_waiting_for_a_slot_gives_up_with_503() -> None:
    async def scenario() -> int:
        slots = TranscriptionSlots(1)
        assert slots.semaphore.acquire(blocking=False)
        try:
            await run_in_transcription_slot(slots, lambda: "nunca", wait_seconds=0.2)
        except HTTPException as exc:
            return exc.status_code
        return 0

    assert asyncio.run(scenario()) == 503
