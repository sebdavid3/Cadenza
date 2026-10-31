"""Experimento 13: latencia de una edición frente al log y al tamaño de la partitura (#275).

Mide, contra la API en el mismo proceso (`TestClient` de FastAPI sobre SQLite en un directorio
temporal, o sobre la base que se pase con `--database-url`), lo que tarda una corrección de
altura (`SetPitch`) desde que se envía hasta que la vista tiene todo lo necesario para mostrar
el estado nuevo. Se cruzan dos factores:

- **Ediciones previas en el log:** 0, 50 y 200 (configurable). Se siembran con el caso de uso
  `append_edit` antes de medir; las ediciones medidas se suman al log, de modo que la
  repetición `i` corre con `n + i` ediciones previas (se registra).
- **Tamaño de la partitura:** el íncipit de las pruebas de la API (`incipit.musicxml`, 4
  compases) y una página completa compuesta repitiendo sus compases hasta `--page-measures`
  (48 por defecto, unos 12 sistemas de 4 compases). La composición es sintética; la API, el
  exportador y la base de datos son los reales.

Y dos maneras de cargar el estado nuevo:

- `five_requests`: lo que hacía la web antes de #275. `POST /edits` y, después, el detalle de
  la sesión, el MusicXML, los posibles errores y el mapa de tiempos (cinco peticiones, aquí
  seguidas: el cliente de pruebas no las solapa). Solo reproduce el servidor anterior si se
  ejecuta contra el código anterior a #275: con #275, el `POST` ya exporta y calcula los
  tiempos, y el `GET /export` siguiente sale de la caché, así que en esa API mide un híbrido
  que no existe. La comparación de antes y después es `five_requests` contra el código
  anterior frente a `single_trip` contra el nuevo, en el mismo equipo.
- `single_trip`: lo que hace la web con #275. Solo `POST /edits`, cuya respuesta trae el
  estado nuevo. Si la API no lo devuelve (una versión anterior), se registra como no
  disponible en lugar de medir otra cosa.

Cada configuración descarta la primera repetición (calentamiento: importaciones, cachés del
proceso) y la registra aparte. La cabecera `Server-Timing`, si la API la envía, se guarda por
petición. No mide la red ni el dibujado en el navegador: es la parte del servidor. La medición
contra el servidor de producción queda fuera de este script.

No hay valores de reserva (CLAUDE.md §8): si falta el íncipit o una petición falla, el script
termina con un error y no escribe ningún resultado.

Salidas (en `--output`, por defecto `results/`):
- `edit_latency_summary.json`
- `exp_13_run_info.json`
"""

from __future__ import annotations

import argparse
import json
import secrets
import statistics
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

from cadenza.api import Settings, create_app
from cadenza.application import Role, User
from cadenza.application import append_edit as append_edit_use_case
from cadenza.domain import (
    Anchor,
    EditOp,
    EventKind,
    Provenance,
    ScoreDocument,
    ScoreIR,
    build_anchor_index,
)
from cadenza.interchange import musicxml_to_score_ir
from cadenza.omr import OMREngine
from cadenza.persistence import (
    SqlAlchemyEditEventRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
    create_engine_for_url,
    create_schema,
    create_session_factory,
)
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.experiments.common import DEFAULT_SEED, RESULTS_DIR, get_run_info  # noqa: E402

EXPERIMENT = "exp_13_edit_latency"
SUMMARY_FILENAME = "edit_latency_summary.json"
RUN_INFO_FILENAME = "exp_13_run_info.json"
INCIPIT_PATH = REPO_ROOT / "apps" / "api" / "tests" / "fixtures" / "incipit.musicxml"
DEFAULT_EDIT_COUNTS = (0, 50, 200)
DEFAULT_RUNS = 20
DEFAULT_PAGE_MEASURES = 48
FLOWS = ("five_requests", "single_trip")
# Las dos alturas entre las que alterna cada nota corregida: siempre válidas en clave de Sol.
_PITCHES = ("C5", "D5")
_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
)

Clock = Callable[[], float]


class SingleTripUnavailable(RuntimeError):
    """La API no devuelve el estado nuevo con la edición (anterior a #275)."""


def load_incipit(path: Path = INCIPIT_PATH) -> ScoreIR:
    """Lee el íncipit de las pruebas de la API; sin él no hay nada que medir."""
    if not path.is_file():
        raise FileNotFoundError(f"No existe el íncipit de referencia: {path}")
    return musicxml_to_score_ir(path.read_text(encoding="utf-8"))


def tile_score(score: ScoreIR, measures: int) -> ScoreIR:
    """Una página: repite los compases del primer pentagrama hasta tener `measures`.

    Las copias se numeran seguidas y, salvo la primera vuelta, no repiten la clave, la armadura
    ni el compás: una página real los declara una vez.
    """
    if measures < 1:
        raise ValueError("la página necesita al menos un compás")
    part = score.parts[0]
    staff = part.staves[0]
    source = staff.measures
    if not source:
        raise ValueError("la partitura no tiene compases que repetir")
    tiled = []
    for index in range(measures):
        measure = source[index % len(source)]
        if index >= len(source):
            measure = replace(measure, clef=None, key_signature=None, time_signature=None)
        tiled.append(replace(measure, number=index + 1))
    new_staff = replace(staff, measures=tuple(tiled))
    return replace(score, parts=(replace(part, staves=(new_staff,)),))


def note_targets(score: ScoreIR) -> list[dict[str, Any]]:
    """Las notas que se corrigen: las de la primera voz que no son de acorde, en orden."""
    targets: list[dict[str, Any]] = []
    for part_index, part in enumerate(score.parts):
        for staff_index, staff in enumerate(part.staves):
            for measure in staff.measures:
                positions: dict[int, int] = {}
                for event in measure.events:
                    position = positions.get(event.voice, 0)
                    positions[event.voice] = position + 1
                    if event.kind is EventKind.NOTE and not event.is_chord and event.pitch:
                        targets.append(
                            {
                                "anchor": {
                                    "part": part_index,
                                    "staff": staff_index,
                                    "measure": measure.number,
                                    "voice": event.voice,
                                    "event_index": position,
                                    "staff_id": staff.id,
                                },
                                "pitch": event.pitch,
                            }
                        )
    if not targets:
        raise ValueError("la partitura no tiene notas que corregir")
    return targets


class EditPlanner:
    """Genera ediciones válidas: recorre las notas y alterna cada una entre dos alturas."""

    def __init__(self, score: ScoreIR) -> None:
        self._targets = note_targets(score)
        self._pitches = {index: str(t["pitch"]) for index, t in enumerate(self._targets)}
        self._next = 0

    def next_edit(self) -> tuple[dict[str, Any], str]:
        """El ancla y la altura nueva de la próxima edición."""
        index = self._next % len(self._targets)
        self._next += 1
        current = self._pitches[index]
        pitch = _PITCHES[1] if current == _PITCHES[0] else _PITCHES[0]
        self._pitches[index] = pitch
        return dict(self._targets[index]["anchor"]), pitch


class _FixedScoreEngine(OMREngine):
    """Motor de la medición: devuelve la partitura que se le fije, sin leer la imagen."""

    def __init__(self) -> None:
        self.score: ScoreIR | None = None

    @property
    def engine_id(self) -> str:
        return "exp13-fixed"

    def transcribe(self, image_path: Path) -> ScoreDocument:
        if self.score is None:
            raise RuntimeError("no se fijó la partitura que devuelve el motor")
        return ScoreDocument(
            id=f"exp13-{secrets.token_hex(8)}",
            score=self.score,
            anchors=build_anchor_index(self.score),
            provenance=Provenance(omr_engine=self.engine_id, model_version="exp13", device="cpu"),
        )


def parse_server_timing(header: str | None) -> dict[str, float]:
    """`db;dur=1.5, export;dur=20` → {"db": 1.5, "export": 20.0}; sin cabecera, {}."""
    stages: dict[str, float] = {}
    if not header:
        return stages
    for item in header.split(","):
        parts = [p.strip() for p in item.split(";")]
        name = parts[0]
        if not name:
            continue
        for param in parts[1:]:
            key, _, value = param.partition("=")
            if key.strip() == "dur":
                try:
                    stages[name] = stages.get(name, 0.0) + float(value)
                except ValueError:
                    continue
    return stages


def latency_stats(samples: Sequence[float]) -> dict[str, Any]:
    """Recuento, media, mediana, p95, mínimo y máximo, en milisegundos."""
    if not samples:
        return {"count": 0}
    ordered = sorted(samples)

    def percentile(p: float) -> float:
        k = (len(ordered) - 1) * (p / 100.0)
        low = int(k)
        high = min(low + 1, len(ordered) - 1)
        return ordered[low] + (ordered[high] - ordered[low]) * (k - low)

    return {
        "count": len(ordered),
        "mean_ms": round(statistics.mean(ordered), 2),
        "median_ms": round(statistics.median(ordered), 2),
        "p95_ms": round(percentile(95.0), 2),
        "min_ms": round(ordered[0], 2),
        "max_ms": round(ordered[-1], 2),
    }


class EditLatencyBench:
    """La API en el proceso con una base propia, una cuenta y su token."""

    def __init__(self, database_url: str, work_dir: Path) -> None:
        self._db_engine = create_engine_for_url(database_url)
        create_schema(self._db_engine)
        self._factory = create_session_factory(self._db_engine)
        self._user = User(
            id=f"exp13-{secrets.token_hex(4)}",
            username=f"exp13-{secrets.token_hex(4)}",
            password_hash="no-se-usa",
            role=Role.TRANSCRIPTOR,
            active=True,
        )
        with self._factory() as db:
            SqlAlchemyUserRepository(db).add(self._user)
            db.commit()
        self.engine = _FixedScoreEngine()
        app = create_app(
            self._factory,
            omr_engine=self.engine,
            settings=Settings(
                auth_secret_key=secrets.token_urlsafe(48),
                artifacts_dir=work_dir / "artifacts",
            ),
        )
        token = app.state.token_service.create_access_token(
            user_id=self._user.id, role=Role.TRANSCRIPTOR
        )
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {token}"}

    def close(self) -> None:
        """Cierra el cliente y las conexiones (en Windows, para poder borrar la base)."""
        self.client.close()
        self._db_engine.dispose()

    def create_session(self, score: ScoreIR) -> str:
        self.engine.score = score
        response = self.client.post(
            "/transcribe",
            files={"file": ("page.png", _PNG_BYTES, "image/png")},
            headers=self.headers,
        )
        if response.status_code != 201:
            raise RuntimeError(f"POST /transcribe respondió {response.status_code}")
        return str(response.json()["session_id"])

    def seed_edits(self, session_id: str, planner: EditPlanner, count: int) -> int:
        """Siembra `count` ediciones con el caso de uso, sin la API; devuelve el `seq` final."""
        seq = 0
        for _ in range(count):
            anchor, pitch = planner.next_edit()
            with self._factory() as db:
                edit = append_edit_use_case(
                    session_id,
                    anchor=Anchor.from_primitive(anchor),
                    op=EditOp.SET_PITCH,
                    session_repository=SqlAlchemySessionRepository(db),
                    edit_repository=SqlAlchemyEditEventRepository(db),
                    current_user=self._user,
                    base_seq=seq,
                    after={"pitch": pitch},
                )
                db.commit()
            seq = edit.seq
        return seq

    def _request(
        self,
        name: str,
        method: str,
        path: str,
        clock: Clock,
        *,
        json_body: Any = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], Any]:
        headers = {**self.headers, "X-Request-ID": f"exp13-{secrets.token_hex(6)}"}
        start = clock()
        response = self.client.request(method, path, json=json_body, params=params, headers=headers)
        elapsed_ms = (clock() - start) * 1000.0
        if response.status_code >= 400:
            raise RuntimeError(f"{method} {path} respondió {response.status_code}")
        record = {
            "name": name,
            "ms": round(elapsed_ms, 3),
            "bytes": len(response.content),
            "server_timing": parse_server_timing(response.headers.get("server-timing")),
        }
        return record, response

    def edit_cycle(
        self,
        session_id: str,
        planner: EditPlanner,
        base_seq: int,
        flow: str,
        clock: Clock = time.perf_counter,
    ) -> tuple[dict[str, Any], int]:
        """Una edición y la carga del estado nuevo según `flow`; devuelve la muestra y el `seq`."""
        anchor, pitch = planner.next_edit()
        body = {
            "base_seq": base_seq,
            "op": "SetPitch",
            "anchor": anchor,
            "before": None,
            "after": {"pitch": pitch},
        }
        base = f"/sessions/{session_id}"
        start = clock()
        post, response = self._request("post_edit", "POST", f"{base}/edits", clock, json_body=body)
        saved = response.json()
        requests = [post]
        if flow == "single_trip":
            if "musicxml" not in saved or "current_score" not in saved:
                raise SingleTripUnavailable("la respuesta de POST /edits no trae el estado nuevo")
        elif flow == "five_requests":
            for name, path, params in (
                ("detail", base, None),
                ("export_musicxml", f"{base}/export", {"format": "musicxml"}),
                ("findings", f"{base}/findings", {"latest_only": True, "include_dismissed": True}),
                ("timing", f"{base}/timing", None),
            ):
                record, _ = self._request(name, "GET", path, clock, params=params)
                requests.append(record)
        else:
            raise ValueError(f"flujo desconocido: {flow}")
        total_ms = (clock() - start) * 1000.0
        return {"total_ms": round(total_ms, 3), "requests": requests}, int(saved["seq"])


@contextmanager
def _database(database_url: str | None) -> Iterator[tuple[str, Path]]:
    with tempfile.TemporaryDirectory(prefix="cadenza-exp13-") as tmp:
        work = Path(tmp)
        url = database_url or f"sqlite+pysqlite:///{(work / 'exp13.db').as_posix()}"
        yield url, work


def _stage_summary(samples: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Estadística por etapa de `Server-Timing`, sumando las de las peticiones de cada muestra."""
    per_stage: dict[str, list[float]] = {}
    for sample in samples:
        totals: dict[str, float] = {}
        for request in sample["requests"]:
            for stage, value in request["server_timing"].items():
                totals[stage] = totals.get(stage, 0.0) + value
        for stage, value in totals.items():
            per_stage.setdefault(stage, []).append(value)
    return {stage: latency_stats(values) for stage, values in sorted(per_stage.items())}


def measure_configuration(
    bench: EditLatencyBench,
    score: ScoreIR,
    *,
    edit_count: int,
    flow: str,
    runs: int,
    clock: Clock = time.perf_counter,
) -> dict[str, Any]:
    """Una sesión nueva con `edit_count` ediciones y `runs` ediciones medidas (más una de
    calentamiento, que se registra aparte)."""
    session_id = bench.create_session(score)
    planner = EditPlanner(score)
    seq = bench.seed_edits(session_id, planner, edit_count)
    try:
        warmup, seq = bench.edit_cycle(session_id, planner, seq, flow, clock)
    except SingleTripUnavailable as exc:
        return {"available": False, "reason": str(exc)}
    samples: list[dict[str, Any]] = []
    for index in range(runs):
        sample, seq = bench.edit_cycle(session_id, planner, seq, flow, clock)
        sample["prior_edits"] = edit_count + 1 + index
        samples.append(sample)
    totals = [s["total_ms"] for s in samples]
    return {
        "available": True,
        "seeded_edits": edit_count,
        "requests_per_edit": len(samples[0]["requests"]) if samples else 0,
        "response_bytes_per_edit": (
            sum(r["bytes"] for r in samples[0]["requests"]) if samples else 0
        ),
        "warmup_ms": warmup["total_ms"],
        "stats": latency_stats(totals),
        "server_timing_stats": _stage_summary(samples),
        "samples": samples,
    }


def run_experiment(
    *,
    output_dir: Path | None = None,
    database_url: str | None = None,
    sizes: Sequence[str] = ("incipit", "page"),
    edit_counts: Sequence[int] = DEFAULT_EDIT_COUNTS,
    flows: Sequence[str] = FLOWS,
    runs: int = DEFAULT_RUNS,
    page_measures: int = DEFAULT_PAGE_MEASURES,
    label: str | None = None,
    clock: Clock = time.perf_counter,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Mide todas las configuraciones y escribe el resumen y su `run_info`."""
    if runs < 1:
        raise ValueError("runs debe ser al menos 1")
    if any(count < 0 for count in edit_counts):
        raise ValueError("el número de ediciones no puede ser negativo")
    unknown = [flow for flow in flows if flow not in FLOWS]
    if unknown:
        raise ValueError(f"flujos desconocidos: {unknown}")

    incipit = load_incipit()
    scores = {"incipit": incipit, "page": tile_score(incipit, page_measures)}
    unknown_sizes = [size for size in sizes if size not in scores]
    if unknown_sizes:
        raise ValueError(f"tamaños desconocidos: {unknown_sizes}")

    configurations: dict[str, Any] = {}
    with _database(database_url) as (url, work_dir):
        bench = EditLatencyBench(url, work_dir)
        try:
            for size in sizes:
                score = scores[size]
                for count in edit_counts:
                    for flow in flows:
                        key = f"{size}/{count}_edits/{flow}"
                        configurations[key] = measure_configuration(
                            bench, score, edit_count=count, flow=flow, runs=runs, clock=clock
                        )
        finally:
            bench.close()

    summary: dict[str, Any] = {
        "experiment": EXPERIMENT,
        "simulated": False,
        "label": label,
        "protocol": {
            "sizes": {
                size: {
                    "measures": len(scores[size].parts[0].staves[0].measures),
                    "notes": len(note_targets(scores[size])),
                }
                for size in sizes
            },
            "page_composition": (
                f"íncipit de las pruebas de la API repetido hasta {page_measures} compases "
                "(composición sintética)"
            ),
            "edit_counts": list(edit_counts),
            "flows": list(flows),
            "runs": runs,
            "database": "sqlite (archivo temporal)" if database_url is None else "--database-url",
            "client": "fastapi.testclient.TestClient en el mismo proceso (sin red)",
            "note": (
                "Cada configuración usa una sesión nueva; la primera edición medida es de "
                "calentamiento y se registra aparte. Las ediciones medidas se suman al log."
            ),
        },
        "configurations": configurations,
    }
    out_dir = output_dir or RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / SUMMARY_FILENAME).write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    run_info = get_run_info(EXPERIMENT, seed=seed)
    run_info["label"] = label
    run_info["protocol"] = summary["protocol"]
    (out_dir / RUN_INFO_FILENAME).write_text(
        json.dumps(run_info, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Latencia de una edición en la API (#275).")
    parser.add_argument("--output", type=Path, default=None, help="Directorio de resultados.")
    parser.add_argument("--database-url", default=None, help="Base de pruebas (SQLAlchemy).")
    parser.add_argument("--sizes", default="incipit,page")
    parser.add_argument("--edits", default=",".join(str(n) for n in DEFAULT_EDIT_COUNTS))
    parser.add_argument("--flows", default=",".join(FLOWS))
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--page-measures", type=int, default=DEFAULT_PAGE_MEASURES)
    parser.add_argument("--label", default=None, help="Nombre de la variante medida.")
    args = parser.parse_args()

    summary = run_experiment(
        output_dir=args.output,
        database_url=args.database_url,
        sizes=[s for s in args.sizes.split(",") if s],
        edit_counts=[int(n) for n in args.edits.split(",") if n],
        flows=[f for f in args.flows.split(",") if f],
        runs=args.runs,
        page_measures=args.page_measures,
        label=args.label,
    )
    for key, config in summary["configurations"].items():
        if not config["available"]:
            print(f"[exp_13] {key}: no disponible ({config['reason']})")
            continue
        stats = config["stats"]
        print(
            f"[exp_13] {key}: n={stats['count']} mediana={stats['median_ms']} ms "
            f"p95={stats['p95_ms']} ms peticiones={config['requests_per_edit']} "
            f"bytes={config['response_bytes_per_edit']}"
        )


if __name__ == "__main__":
    main()
