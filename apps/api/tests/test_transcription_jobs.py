"""Transcripción en segundo plano, con su estado y su avance (#375, ADR-0063)."""

from __future__ import annotations

import gc
import logging
import queue
import secrets
import threading
import time
import weakref
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from cadenza.api import Settings, create_app
from cadenza.api.transcription_jobs import JobFailure, JobProgress, JobStage, TranscriptionJobs
from cadenza.api.transcription_slots import TranscriptionSlots
from cadenza.application import Role, TranscribeResult, User
from cadenza.domain import ScoreDocument
from cadenza.omr import OMREngine, OMRTranscriptionError
from cadenza.omr.progress import OMRProgress, Reading, report
from cadenza.omr.testing import FakeOMREngine
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_engine_for_url,
    create_schema,
    create_session_factory,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

SECRET = secrets.token_hex(32)
JOB_TIMEOUT = 10.0


class _SteppedEngine(OMREngine):
    """Motor falso que avisa por pentagrama, como HOMR, y espera a la prueba en cada aviso.

    `readings` son los pentagramas de cada lectura: uno, una página corriente; dos, una de voz y
    piano con su segunda lectura (#325). Cada `step()` deja pasar un aviso.
    """

    def __init__(self, *readings: int, fail: Exception | None = None) -> None:
        self._fake = FakeOMREngine()
        self._readings = readings
        self._fail = fail
        self._go: queue.Queue[None] = queue.Queue()
        self.calls: list[str] = []
        self.running = 0
        self.max_running = 0

    @property
    def engine_id(self) -> str:
        return "fake-stepped"

    def step(self, times: int = 1) -> None:
        for _ in range(times):
            self._go.put(None)

    def _announce(self, progress: OMRProgress) -> None:
        report(progress)
        assert self._go.get(timeout=JOB_TIMEOUT) is None

    def transcribe(self, image_path: Path) -> ScoreDocument:
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        self.calls.append(image_path.name)
        try:
            for kind, staffs in zip((Reading.FIRST, Reading.PIANO), self._readings, strict=False):
                self._announce(OMRProgress(kind))
                for staff in range(1, staffs + 1):
                    self._announce(OMRProgress(kind, staffs=staffs, staff=staff))
            if self._fail is not None:
                raise self._fail
            return self._fake.transcribe(image_path)
        finally:
            self.running -= 1


class _HeldMeterStage:
    """Etapa del compás que espera a la prueba: deja ver la revisión."""

    def __init__(self) -> None:
        self.release = threading.Event()

    def apply(self, document: ScoreDocument) -> ScoreDocument:
        assert self.release.wait(JOB_TIMEOUT)
        return document


@pytest.fixture(autouse=True)
def _artifacts_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Las imágenes subidas van al `./data/artifacts` por defecto: aquí, en el temporal."""
    monkeypatch.chdir(tmp_path)


def _db(path: Path) -> Any:
    db = create_engine_for_url(f"sqlite+pysqlite:///{path.as_posix()}")
    create_schema(db)
    factory = create_session_factory(db)
    with factory() as session:
        for user_id in ("usr-ana", "usr-bea"):
            SqlAlchemyUserRepository(session).add(
                User(
                    id=user_id,
                    username=user_id,
                    password_hash="-",
                    role=Role.TRANSCRIPTOR,
                    active=True,
                )
            )
        session.commit()
    return factory


def _app(
    factory: Any,
    engine: OMREngine,
    *,
    meter_stage: Any = None,
    **settings: Any,
) -> FastAPI:
    return create_app(
        factory,
        omr_engine=engine,
        meter_stage=meter_stage,
        settings=Settings(auth_secret_key=SECRET, **settings),
    )


def _client(app: FastAPI, user_id: str) -> TestClient:
    token = app.state.token_service.create_access_token(user_id=user_id, role=Role.TRANSCRIPTOR)
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


def _upload(name: str = "pagina.png") -> dict[str, tuple[str, bytes, str]]:
    return {"file": (name, b"\x89PNG\r\n\x1a\n", "image/png")}


def _submit(client: TestClient, name: str = "pagina.png", **data: Any) -> dict[str, Any]:
    response = client.post("/transcription-jobs", files=_upload(name), data=data)
    assert response.status_code == 202, response.text
    body: dict[str, Any] = response.json()
    return body


def _wait_for(
    client: TestClient, job_id: str, condition: Callable[[dict[str, Any]], bool]
) -> dict[str, Any]:
    deadline = time.monotonic() + JOB_TIMEOUT
    while True:
        response = client.get(f"/transcription-jobs/{job_id}")
        assert response.status_code == 200, response.text
        job: dict[str, Any] = response.json()
        if condition(job):
            return job
        assert time.monotonic() < deadline, f"el trabajo no llegó: {job}"
        time.sleep(0.01)


def _at(stage: str, **fields: Any) -> Callable[[dict[str, Any]], bool]:
    return lambda job: job["stage"] == stage and all(job[k] == v for k, v in fields.items())


def test_a_job_answers_at_once_and_reports_each_stage_until_its_session(tmp_path: Path) -> None:
    engine = _SteppedEngine(2, 3)
    meter = _HeldMeterStage()
    app = _app(_db(tmp_path / "j.db"), engine, meter_stage=meter)
    client = _client(app, "usr-ana")

    created = _submit(client, "TS-02.png", title="Lied")

    assert created["stage"] in {"queued", "detecting"}
    assert created["source_filename"] == "TS-02.png"
    assert created["title"] == "Lied"
    job_id = created["id"]
    detecting = _wait_for(client, job_id, _at("detecting", reading="first"))
    assert detecting["staff"] is None and detecting["started_at"] is not None
    engine.step()
    assert _wait_for(client, job_id, _at("reading", reading="first", staff=1, staffs=2))
    engine.step()
    assert _wait_for(client, job_id, _at("reading", reading="first", staff=2, staffs=2))
    # La segunda lectura, la del piano solo: vuelve a detectar y a contar sus pentagramas.
    engine.step()
    piano = _wait_for(client, job_id, _at("detecting", reading="piano"))
    assert piano["staffs"] is None
    for staff in (1, 2, 3):
        engine.step()
        assert _wait_for(client, job_id, _at("reading", reading="piano", staff=staff, staffs=3))
    engine.step()
    reviewing = _wait_for(client, job_id, _at("reviewing"))
    assert reviewing["reading"] is None and reviewing["staff"] is None
    meter.release.set()

    done = _wait_for(client, job_id, _at("done"))

    # La sesión se llama como el trabajo y es de quien lo subió.
    assert done["result"]["session_id"] == job_id
    assert done["failure"] is None and done["finished_at"] is not None
    session = client.get(f"/sessions/{job_id}")
    assert session.status_code == 200
    assert session.json()["title"] == "Lied"
    assert session.json()["owner_id"] == "usr-ana"


def test_the_queue_goes_in_order_one_at_a_time_and_says_how_many_are_ahead(
    tmp_path: Path,
) -> None:
    engine = _SteppedEngine(1)
    app = _app(_db(tmp_path / "j.db"), engine)
    ana, bea = _client(app, "usr-ana"), _client(app, "usr-bea")

    first = _submit(ana, "a.png")
    _wait_for(ana, first["id"], _at("detecting"))
    second = _submit(bea, "b.png")
    third = _submit(ana, "c.png")

    # Por delante cuentan los de todas las personas, también el que se transcribe.
    assert second["stage"] == "queued" and second["ahead"] == 1
    assert third["stage"] == "queued" and third["ahead"] == 2
    assert ana.get(f"/transcription-jobs/{third['id']}").json()["ahead"] == 2

    engine.step(2)
    _wait_for(ana, first["id"], _at("done"))
    _wait_for(bea, second["id"], _at("detecting"))
    assert ana.get(f"/transcription-jobs/{third['id']}").json()["ahead"] == 1
    engine.step(4)
    _wait_for(ana, third["id"], _at("done"))

    assert engine.calls[0].endswith(".png") and len(engine.calls) == 3
    assert [ana.get(f"/transcription-jobs/{job['id']}").status_code for job in (first, third)] == [
        200,
        200,
    ]
    assert engine.max_running == 1


def test_each_person_sees_only_their_jobs(tmp_path: Path) -> None:
    engine = _SteppedEngine(1)
    app = _app(_db(tmp_path / "j.db"), engine)
    ana, bea = _client(app, "usr-ana"), _client(app, "usr-bea")
    job = _submit(ana)
    try:
        # Un trabajo ajeno no existe para los demás (ADR-0012).
        assert bea.get(f"/transcription-jobs/{job['id']}").status_code == 404
        assert bea.delete(f"/transcription-jobs/{job['id']}").status_code == 404
        assert bea.get("/transcription-jobs").json() == []
        assert [own["id"] for own in ana.get("/transcription-jobs").json()] == [job["id"]]
    finally:
        engine.step(2)
    _wait_for(ana, job["id"], _at("done"))


def test_jobs_need_a_session(tmp_path: Path) -> None:
    app = _app(_db(tmp_path / "j.db"), FakeOMREngine())
    client = TestClient(app)

    assert client.post("/transcription-jobs", files=_upload()).status_code == 401
    assert client.get("/transcription-jobs").status_code == 401


def test_after_a_restart_a_job_is_unknown(tmp_path: Path) -> None:
    factory = _db(tmp_path / "j.db")
    engine = _SteppedEngine(1)
    before = _app(factory, engine)
    job = _submit(_client(before, "usr-ana"))
    _wait_for(_client(before, "usr-ana"), job["id"], _at("detecting"))

    # Otra API sobre la misma base: el registro estaba en la memoria de la anterior.
    after = _client(_app(factory, FakeOMREngine()), "usr-ana")

    missing = after.get(f"/transcription-jobs/{job['id']}")
    assert missing.status_code == 404
    assert "reinició" in missing.json()["detail"]
    assert after.get("/transcription-jobs").json() == []
    # Y no hay sesión: la web dice que se interrumpió.
    assert after.get(f"/sessions/{job['id']}").status_code == 404
    # La API de antes termina su trabajo antes de salir: no se cuela en otras pruebas.
    engine.step(2)
    _wait_for(_client(before, "usr-ana"), job["id"], _at("done"))


def test_each_person_has_a_cap_on_jobs_in_the_queue(tmp_path: Path) -> None:
    engine = _SteppedEngine(1)
    app = _app(_db(tmp_path / "j.db"), engine, transcribe_jobs_per_user=2)
    ana, bea = _client(app, "usr-ana"), _client(app, "usr-bea")
    jobs = [_submit(ana), _submit(ana)]

    refused = ana.post("/transcription-jobs", files=_upload())

    assert refused.status_code == 429
    assert "2 transcripciones" in refused.json()["detail"]
    # El tope es de cada persona.
    other = _submit(bea)
    # Al terminar una, se puede volver a subir.
    engine.step(2)
    _wait_for(ana, jobs[0]["id"], _at("done"))
    again = _submit(ana)
    engine.step(6)
    for client, job in ((ana, jobs[1]), (bea, other), (ana, again)):
        _wait_for(client, job["id"], _at("done"))


def test_the_whole_queue_has_a_cap(tmp_path: Path) -> None:
    engine = _SteppedEngine(1)
    app = _app(_db(tmp_path / "j.db"), engine, transcribe_jobs_max=2)
    ana, bea = _client(app, "usr-ana"), _client(app, "usr-bea")
    jobs = [(ana, _submit(ana)), (bea, _submit(bea))]

    full = bea.post("/transcription-jobs", files=_upload())

    assert full.status_code == 503
    assert full.headers["Retry-After"] == "60"
    assert "cola de transcripción está llena" in full.json()["detail"]
    engine.step(4)
    for client, job in jobs:
        _wait_for(client, job["id"], _at("done"))


@pytest.mark.parametrize(
    ("error", "failure"),
    [
        (OMRTranscriptionError("No staffs found in image"), "unreadable"),
        (RuntimeError("ONNX se cayó"), "internal"),
    ],
)
def test_a_failed_job_says_why(tmp_path: Path, error: Exception, failure: str) -> None:
    engine = _SteppedEngine(1, fail=error)
    app = _app(_db(tmp_path / "j.db"), engine)
    client = _client(app, "usr-ana")
    job = _submit(client)
    engine.step(2)

    failed = _wait_for(client, job["id"], _at("failed"))

    assert failed["failure"] == failure
    assert failed["result"] is None
    assert client.get(f"/sessions/{job['id']}").status_code == 404
    # El hueco y la cola quedan libres para el siguiente.
    ok = _SteppedEngine(1)
    app.state.omr_engine = ok
    following = _submit(client)
    ok.step(2)
    _wait_for(client, following["id"], _at("done"))


def test_a_queued_job_can_be_removed_but_not_one_being_transcribed(tmp_path: Path) -> None:
    engine = _SteppedEngine(1)
    app = _app(_db(tmp_path / "j.db"), engine)
    client = _client(app, "usr-ana")
    running = _submit(client, "a.png")
    _wait_for(client, running["id"], _at("detecting"))
    queued = _submit(client, "b.png")

    assert client.delete(f"/transcription-jobs/{queued['id']}").status_code == 204
    busy = client.delete(f"/transcription-jobs/{running['id']}")
    assert busy.status_code == 409

    engine.step(2)
    _wait_for(client, running["id"], _at("done"))
    # El quitado no se transcribe; uno terminado se olvida, y su sesión sigue.
    assert len(engine.calls) == 1
    assert client.get(f"/transcription-jobs/{queued['id']}").status_code == 404
    assert client.delete(f"/transcription-jobs/{running['id']}").status_code == 204
    assert client.get(f"/transcription-jobs/{running['id']}").status_code == 404
    assert client.get(f"/sessions/{running['id']}").status_code == 200


def test_the_upload_is_checked_before_queueing(tmp_path: Path) -> None:
    engine = _SteppedEngine(1)
    app = _app(_db(tmp_path / "j.db"), engine)
    client = _client(app, "usr-ana")

    not_an_image = client.post(
        "/transcription-jobs", files={"file": ("notas.txt", b"hola", "text/plain")}
    )
    bad_condition = client.post("/transcription-jobs", files=_upload(), data={"condition": "x"})
    bad_instrument = client.post(
        "/transcription-jobs", files=_upload(), data={"instruments": ["kazoo"]}
    )

    assert not_an_image.status_code == 415
    assert bad_condition.status_code == 422
    assert bad_instrument.status_code == 422
    assert client.get("/transcription-jobs").json() == []
    assert engine.calls == []


def test_the_time_of_each_stage_goes_to_the_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    engine = _SteppedEngine(1, 2)
    app = _app(_db(tmp_path / "j.db"), engine)
    client = _client(app, "usr-ana")
    caplog.set_level(logging.INFO, logger="cadenza.api.transcription_jobs")
    job = _submit(client)
    engine.step(5)
    _wait_for(client, job["id"], _at("done"))

    finished = [r.getMessage() for r in caplog.records if "transcription_job_finished" in r.message]

    assert len(finished) == 1
    line = finished[0]
    for stage in (
        "queued_ms=",
        "detecting_ms=",
        "reading_ms=",
        "piano_detecting_ms=",
        "piano_reading_ms=",
        "reviewing_ms=",
        "running_ms=",
    ):
        assert stage in line
    assert f"job_id={job['id']}" in line
    assert "outcome=done" in line and "staffs=1" in line and "piano_staffs=2" in line


def test_the_synchronous_transcription_is_unchanged(tmp_path: Path) -> None:
    app = _app(_db(tmp_path / "j.db"), FakeOMREngine())
    client = _client(app, "usr-ana")

    response = client.post("/transcribe", files=_upload())

    assert response.status_code == 201
    assert set(response.json()) == {
        "session_id",
        "document_id",
        "omr_engine",
        "findings_count",
        "condition",
        "test_score_id",
    }


def _result(session_id: str) -> TranscribeResult:
    return TranscribeResult(
        session_id=session_id, document_id="d", omr_engine="fake", findings_count=0
    )


def _wait_view(jobs: TranscriptionJobs, job_id: str, stage: JobStage) -> None:
    deadline = time.monotonic() + JOB_TIMEOUT
    while (view := jobs.get(job_id, "usr-ana")) is None or view.stage is not stage:
        assert time.monotonic() < deadline, view
        time.sleep(0.01)


class _Image:
    """Lo que retiene un trabajo en cola: la imagen subida."""


def test_a_finished_job_lets_go_of_its_image_while_the_worker_waits() -> None:
    jobs = TranscriptionJobs(
        TranscriptionSlots(1), max_per_user=5, max_total=5, clock=lambda: datetime.now(UTC)
    )
    image = _Image()
    kept = weakref.ref(image)

    def work(progress: JobProgress, image: _Image = image) -> TranscribeResult:
        return _result(progress.job_id)

    view = jobs.submit(owner_id="usr-ana", work=work, source_filename=None, title=None)
    del image, work
    _wait_view(jobs, view.id, JobStage.DONE)

    gc.collect()
    assert kept() is None


def test_the_worker_survives_a_job_that_kills_its_thread() -> None:
    jobs = TranscriptionJobs(
        TranscriptionSlots(1), max_per_user=5, max_total=5, clock=lambda: datetime.now(UTC)
    )

    def dies(progress: JobProgress) -> TranscribeResult:
        raise SystemExit("el hilo se va")

    broken = jobs.submit(owner_id="usr-ana", work=dies, source_filename=None, title=None)
    _wait_view(jobs, broken.id, JobStage.FAILED)
    # Ni colgado ni contando para los topes: fallido, y el siguiente se transcribe.
    assert (
        view := jobs.get(broken.id, "usr-ana")
    ) is not None and view.failure is JobFailure.INTERNAL
    following = jobs.submit(
        owner_id="usr-ana",
        work=lambda progress: _result(progress.job_id),
        source_filename=None,
        title=None,
    )
    _wait_view(jobs, following.id, JobStage.DONE)


def test_finished_jobs_are_forgotten_after_a_while() -> None:
    jobs = TranscriptionJobs(
        TranscriptionSlots(1),
        max_per_user=5,
        max_total=5,
        clock=lambda: datetime.now(UTC),
        keep_finished_seconds=0.2,
    )
    view = jobs.submit(
        owner_id="usr-ana",
        work=lambda progress: _result(progress.job_id),
        source_filename=None,
        title=None,
    )
    _wait_view(jobs, view.id, JobStage.DONE)
    assert [job.id for job in jobs.list("usr-ana")] == [view.id]

    time.sleep(0.3)

    assert jobs.get(view.id, "usr-ana") is None
    assert jobs.list("usr-ana") == []


def test_a_job_waits_in_the_queue_while_the_synchronous_transcription_has_the_slots(
    tmp_path: Path,
) -> None:
    engine = _SteppedEngine(1)
    app = _app(_db(tmp_path / "j.db"), engine, transcribe_max_concurrency=1)
    client = _client(app, "usr-ana")
    slots: TranscriptionSlots = app.state.transcription_slots
    assert slots.semaphore.acquire(blocking=False)  # POST /transcribe calculando
    try:
        job = _submit(client)
        time.sleep(0.2)
        waiting = client.get(f"/transcription-jobs/{job['id']}").json()
        # Espera en cola, la siguiente, sin 503 ni plazo.
        assert (waiting["stage"], waiting["ahead"]) == ("queued", 0)
    finally:
        slots.semaphore.release()
    _wait_for(client, job["id"], _at("detecting"))
    engine.step(2)
    _wait_for(client, job["id"], _at("done"))
