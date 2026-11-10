"""Transcripciones en segundo plano: una cola en memoria, de una en una y con su avance (#375,
ADR-0063).

`POST /transcription-jobs` deja el trabajo en la cola y responde enseguida; un hilo propio los
transcribe en orden de llegada, de todas las personas, cada uno con un hueco de transcripción
(ADR-0024), así que comparten turno con `POST /transcribe`. Mientras HOMR lee, el trabajo anota
en qué está con lo que el motor avisa (`cadenza.omr.progress`): detectando los pentagramas,
leyendo el pentagrama X de N de cada lectura (la segunda, la del piano solo, #325) y, cuando el
motor termina, revisando (la etapa del compás y las reglas). Al acabar queda la sesión creada, con
el mismo identificador que el trabajo, o el motivo del fallo.

El registro vive en la memoria del proceso: sin tabla ni migración. Si la API se reinicia, lo que
estaba en curso desaparece y su identificador deja de existir (404); por eso supone un único
proceso de la API, como el despliegue (ADR-0063 §5). Los terminados se guardan un rato
(`KEEP_FINISHED_SECONDS`) para que la persona vea cómo acabaron aunque vuelva más tarde.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from cadenza.application import TranscribeResult
from cadenza.domain import ScoreDocument
from cadenza.omr import OMREngine, OMRTranscriptionError
from cadenza.omr.progress import OMRProgress, Reading, listening

from .transcription_slots import TranscriptionSlots

logger = logging.getLogger("cadenza.api.transcription_jobs")

KEEP_FINISHED_SECONDS = 3600.0
"""Cuánto se guarda un trabajo terminado (listo o fallido) antes de olvidarlo."""


class JobStage(StrEnum):
    """En qué está un trabajo, en el orden en que pasa por cada etapa."""

    QUEUED = "queued"
    DETECTING = "detecting"
    READING = "reading"
    REVIEWING = "reviewing"
    DONE = "done"
    FAILED = "failed"


FINISHED_STAGES = frozenset({JobStage.DONE, JobStage.FAILED})


class JobFailure(StrEnum):
    """Por qué falló un trabajo, para que la web lo diga con sus palabras."""

    UNREADABLE = "unreadable"
    """El motor no reconoció ninguna partitura en la imagen."""
    INTERNAL = "internal"
    """Otro error del servidor."""


class JobLimitReached(Exception):
    """La persona ya tiene el máximo de trabajos en cola o en curso."""

    def __init__(self, limit: int) -> None:
        super().__init__(limit)
        self.limit = limit


class JobQueueFull(Exception):
    """La cola de todas las personas está llena."""


@dataclass(frozen=True)
class JobView:
    """Lo que se ve de un trabajo en un momento dado."""

    id: str
    owner_id: str
    stage: JobStage
    ahead: int | None
    reading: Reading | None
    staff: int | None
    staffs: int | None
    result: TranscribeResult | None
    failure: JobFailure | None
    source_filename: str | None
    title: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobProgress:
    """Lo que el trabajo en marcha recibe para anotar su avance."""

    def __init__(self, jobs: TranscriptionJobs, job_id: str) -> None:
        self._jobs = jobs
        self.job_id = job_id

    def omr(self, progress: OMRProgress) -> None:
        """Un aviso del motor (`cadenza.omr.progress`)."""
        self._jobs._on_omr_progress(self.job_id, progress)

    def reviewing(self) -> None:
        """El motor terminó: quedan la etapa del compás, las reglas y guardar la sesión."""
        self._jobs._enter(self.job_id, JobStage.REVIEWING, mark="reviewing")


JobWork = Callable[[JobProgress], TranscribeResult]


@dataclass
class _Job:
    id: str
    owner_id: str
    work: JobWork | None
    source_filename: str | None
    title: str | None
    created_at: datetime
    stage: JobStage = JobStage.QUEUED
    reading: Reading | None = None
    staff: int | None = None
    staffs: int | None = None
    result: TranscribeResult | None = None
    failure: JobFailure | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    finished_monotonic: float | None = None
    # Cuándo empezó cada etapa (reloj monótono), para el registro (#269).
    marks: list[tuple[str, float]] = field(default_factory=list)
    read_staffs: dict[Reading, int] = field(default_factory=dict)


class ReportingEngine(OMREngine):
    """El motor de un trabajo: transcribe como `inner` y le anota al trabajo lo que avisa."""

    def __init__(self, inner: OMREngine, progress: JobProgress) -> None:
        self._inner = inner
        self._progress = progress

    @property
    def engine_id(self) -> str:
        return self._inner.engine_id

    def transcribe(self, image_path: Path) -> ScoreDocument:
        with listening(self._progress.omr):
            document = self._inner.transcribe(image_path)
        self._progress.reviewing()
        return document


class TranscriptionJobs:
    """La cola de trabajos de la API, con un hilo que los transcribe de uno en uno.

    `max_per_user` acota los trabajos en cola o en curso de cada persona y `max_total`, los de
    todas: cada trabajo en cola guarda su imagen en memoria hasta que se transcribe.
    """

    def __init__(
        self,
        slots: TranscriptionSlots,
        *,
        max_per_user: int,
        max_total: int,
        clock: Callable[[], datetime],
        keep_finished_seconds: float = KEEP_FINISHED_SECONDS,
    ) -> None:
        self._slots = slots
        self.max_per_user = max_per_user
        self.max_total = max_total
        self._clock = clock
        self._keep_finished_seconds = keep_finished_seconds
        self._lock = threading.Condition()
        self._jobs: dict[str, _Job] = {}
        self._queue: deque[str] = deque()
        self._running: str | None = None
        self._worker: threading.Thread | None = None

    # --- Lo que piden las rutas -------------------------------------------------------------

    def submit(
        self,
        *,
        owner_id: str,
        work: JobWork,
        source_filename: str | None,
        title: str | None,
    ) -> JobView:
        """Pone un trabajo al final de la cola; con un tope superado, no lo pone."""

        with self._lock:
            self._prune()
            active = [job for job in self._jobs.values() if job.stage not in FINISHED_STAGES]
            if len(active) >= self.max_total:
                raise JobQueueFull()
            if sum(job.owner_id == owner_id for job in active) >= self.max_per_user:
                raise JobLimitReached(self.max_per_user)
            job = _Job(
                id=str(uuid.uuid4()),
                owner_id=owner_id,
                work=work,
                source_filename=source_filename,
                title=title,
                created_at=self._clock(),
            )
            job.marks.append(("queued", time.monotonic()))
            self._jobs[job.id] = job
            self._queue.append(job.id)
            view = self._view(job)
            self._ensure_worker()
            self._lock.notify_all()
        logger.info(
            "transcription_job_queued job_id=%s user_id=%s ahead=%d",
            job.id,
            owner_id,
            view.ahead or 0,
        )
        return view

    def get(self, job_id: str, owner_id: str) -> JobView | None:
        """El trabajo, si existe y es de `owner_id`; si no, None (ADR-0012)."""

        with self._lock:
            self._prune()
            job = self._jobs.get(job_id)
            if job is None or job.owner_id != owner_id:
                return None
            return self._view(job)

    def list(self, owner_id: str) -> list[JobView]:
        """Los trabajos de `owner_id`, del más antiguo al más reciente."""

        with self._lock:
            self._prune()
            own = [job for job in self._jobs.values() if job.owner_id == owner_id]
            own.sort(key=lambda job: job.created_at)
            return [self._view(job) for job in own]

    def discard(self, job_id: str, owner_id: str) -> bool | None:
        """Quita un trabajo en cola (no se transcribirá) o uno terminado (se olvida).

        Devuelve True si se quitó, False si se está transcribiendo (no se puede interrumpir) y
        None si no existe o no es de `owner_id`.
        """

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.owner_id != owner_id:
                return None
            if job.stage not in FINISHED_STAGES and job.stage is not JobStage.QUEUED:
                return False
            if job.stage is JobStage.QUEUED:
                self._queue.remove(job_id)
                logger.info("transcription_job_cancelled job_id=%s user_id=%s", job_id, owner_id)
            del self._jobs[job_id]
            return True

    # --- El hilo de trabajo -----------------------------------------------------------------

    def _ensure_worker(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = threading.Thread(
            target=self._work_forever, name="transcripcion-en-cola", daemon=True
        )
        self._worker.start()

    def _work_forever(self) -> None:
        # Nada de lo que haga un trabajo mata el hilo, ni siquiera un `SystemExit` dentro de una
        # dependencia: los demás trabajos siguen. (En un hilo que no es el principal, salir del
        # proceso no es cosa suya; Ctrl+C llega al hilo principal.)
        while True:
            try:
                self._work_one()
            except BaseException:
                logger.exception("transcription_jobs_worker_failed")

    def _work_one(self) -> None:
        """Espera un trabajo, le busca hueco y lo transcribe. Sus variables mueren al volver:
        la imagen del trabajo no se queda en memoria mientras el hilo espera al siguiente."""

        with self._lock:
            while not self._queue:
                self._lock.wait()
        # Un hueco de transcripción, como `POST /transcribe` (ADR-0024), pero sin plazo: el
        # trabajo sigue en cola, el primero, hasta que lo hay.
        self._slots.semaphore.acquire()
        try:
            with self._lock:
                if not self._queue:
                    return
                job = self._jobs[self._queue.popleft()]
                self._running = job.id
                job.stage = JobStage.DETECTING
                job.started_at = self._clock()
                job.marks.append(("detecting", time.monotonic()))
                # La imagen y lo demás salen del registro: solo las retiene esta vuelta.
                work, job.work = job.work, None
            self._run(job, work)
        finally:
            with self._lock:
                self._running = None
            self._slots.semaphore.release()

    def _run(self, job: _Job, work: JobWork | None) -> None:
        result: TranscribeResult | None = None
        failure: JobFailure | None = JobFailure.INTERNAL
        try:
            assert work is not None
            result = work(JobProgress(self, job.id))
            failure = None
        except OMRTranscriptionError as exc:
            failure = JobFailure.UNREADABLE
            logger.info("transcription_job_unreadable job_id=%s error=%s", job.id, exc)
        except Exception:
            logger.exception("transcription_job_failed job_id=%s", job.id)
        finally:
            # También ante un BaseException: el trabajo nunca se queda a medias.
            with self._lock:
                job.result = result
                job.failure = failure
                job.stage = JobStage.DONE if failure is None else JobStage.FAILED
                job.reading = job.staff = job.staffs = None
                job.finished_at = self._clock()
                job.finished_monotonic = time.monotonic()
                job.marks.append(("end", job.finished_monotonic))
        try:
            self._log_finished(job)
        except Exception:  # pragma: no cover - el registro nunca tumba la cola
            logger.exception("transcription_job_log_failed job_id=%s", job.id)

    def _log_finished(self, job: _Job) -> None:
        """Lo que tardó cada etapa, en milisegundos, en una línea del registro (#269)."""

        durations: dict[str, float] = {}
        for (name, start), (_, end) in zip(job.marks, job.marks[1:], strict=False):
            durations[name] = durations.get(name, 0.0) + (end - start) * 1000.0
        started = next((t for name, t in job.marks if name == "detecting"), None)
        running_ms = (job.marks[-1][1] - started) * 1000.0 if started is not None else 0.0
        stages = " ".join(
            f"{name}_ms={durations.get(name, 0.0):.0f}"
            for name in (
                "queued",
                "detecting",
                "reading",
                "piano_detecting",
                "piano_reading",
                "reviewing",
            )
        )
        logger.info(
            "transcription_job_finished job_id=%s user_id=%s outcome=%s failure=%s %s "
            "running_ms=%.0f staffs=%s piano_staffs=%s session_id=%s",
            job.id,
            job.owner_id,
            job.stage.value,
            job.failure.value if job.failure else "-",
            stages,
            running_ms,
            job.read_staffs.get(Reading.FIRST, "-"),
            job.read_staffs.get(Reading.PIANO, "-"),
            job.result.session_id if job.result else "-",
        )

    # --- El avance ----------------------------------------------------------------------------

    def _on_omr_progress(self, job_id: str, progress: OMRProgress) -> None:
        piano = progress.reading is Reading.PIANO
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if progress.staffs is None:
                # Empieza una lectura: se detectan sus pentagramas. La primera ya se contaba
                # desde que el trabajo salió de la cola.
                if piano and job.reading is not Reading.PIANO:
                    job.marks.append(("piano_detecting", time.monotonic()))
                job.stage = JobStage.DETECTING
                job.reading = progress.reading
                job.staff = job.staffs = None
                return
            if job.stage is not JobStage.READING or job.reading is not progress.reading:
                job.marks.append(("piano_reading" if piano else "reading", time.monotonic()))
            job.stage = JobStage.READING
            job.reading = progress.reading
            job.staffs = progress.staffs
            job.staff = progress.staff
            job.read_staffs[progress.reading] = progress.staffs

    def _enter(self, job_id: str, stage: JobStage, *, mark: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.stage = stage
            job.reading = job.staff = job.staffs = None
            job.marks.append((mark, time.monotonic()))

    # --- Auxiliares, con el cerrojo tomado --------------------------------------------------

    def _view(self, job: _Job) -> JobView:
        ahead: int | None = None
        if job.stage is JobStage.QUEUED:
            ahead = self._queue.index(job.id) + (1 if self._running is not None else 0)
        return JobView(
            id=job.id,
            owner_id=job.owner_id,
            stage=job.stage,
            ahead=ahead,
            reading=job.reading,
            staff=job.staff,
            staffs=job.staffs,
            result=job.result,
            failure=job.failure,
            source_filename=job.source_filename,
            title=job.title,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )

    def _prune(self) -> None:
        now = time.monotonic()
        stale = [
            job.id
            for job in self._jobs.values()
            if job.finished_monotonic is not None
            and now - job.finished_monotonic >= self._keep_finished_seconds
        ]
        for job_id in stale:
            del self._jobs[job_id]
