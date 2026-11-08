"""Experimento 10: Protocolo de medición de esfuerzo con participantes (HITL).

Fase 7, Issue #33, D38, Objetivo Específico 5 de la tesis; fidelidad residual y NASA-TLX, #250.

Compara cuantitativa y cualitativamente la condición asistida (con hallazgos del
validador musical) frente a la línea base no asistida (sin validador):
1. **Condición Asistida (`assisted`):**
   El validador identifica inconsistencias métricas/tonales; la UI guía al transcriptor.
2. **Condición No Asistida (`unassisted`):**
   Transcripción sin asistencia algorítmica; el usuario revisa secuencialmente.

Genera salidas tabulares reproducibles para análisis estadístico (ANOVA, GLMM, NASA-TLX):
- `results/effort_study_sessions.csv`
- `results/effort_study_by_measure.csv`
- `results/effort_study_summary.json`
- `results/exp_10_run_info.json`

Solo exporta sesiones reales de una base de datos (`--db-url`). Sin base, o con una base sin
sesiones del estudio, falla: no hay datos de reserva (CLAUDE.md §8.1, #271). Los datos
sintéticos de `--smoke` solo prueban la exportación, van marcados como simulados y nunca se
escriben en `results/`.

Con una base real, además (#250, protocolo §3.2 y §3.3):
- **Fidelidad residual:** SER y OMR-NED del estado final de cada sesión (su documento con todo
  el log aplicado) frente a la verdad de su `test_score_id` en el banco del estudio (#247). Sin
  el banco regenerado, o con otra verdad que la del manifiesto, falla.
- **NASA-TLX:** se lee de un CSV con una fila por participante y bloque (`--nasa-tlx`), y se une
  a cada sesión por su participante y el bloque que le da la matriz del manifiesto. Sin dato, la
  celda queda vacía, nunca a 0.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

from cadenza.domain import EventKind, ScoreDocument, ScoreIR, materialize
from cadenza.interchange import Music21ScoreExporter, read_score
from cadenza.learning import (
    MetricsExtraMissing,
    omr_ned_pair,
    score_ser_pair,
    without_time_symbols,
)
from cadenza.learning.evaluation import resolve_pitch_with_key_signature
from cadenza.persistence import (
    EditEventRecord,
    EffortMetricsRecord,
    FindingRecord,
    SqlAlchemyEditEventRepository,
    UserRecord,
    create_engine_for_url,
    create_schema,
    create_session_factory,
)
from cadenza.persistence import (
    Session as SessionRecord,
)
from cadenza.validation.rules.support import onsets, voices_of
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ml.experiments.common import (
    DEFAULT_SEED,
    REPO_ROOT,
    RESULTS_DIR,
    get_run_info,
)

SYNTHETIC_WARNING = (
    "Datos sintéticos: no hay sesiones de un estudio real. "
    "No citar como resultado del estudio con participantes (#96, #271)."
)

STUDY_MANIFEST = REPO_ROOT / "docs" / "experimentos" / "banco_de_partituras.json"
REGENERATE_BANK = "uv run --no-sync python -P scripts/build_study_bank.py"

# Las seis subescalas del NASA-TLX (protocolo §3.3), en el orden del formulario. Todas van de 0 a
# 100 y más es más carga: el rendimiento, como en el formulario original, 0 = perfecto y
# 100 = fracaso.
TLX_SCALES = ("mental", "physical", "temporal", "performance", "effort", "frustration")
TLX_PAIRS = 15  # Comparaciones por parejas de las seis subescalas: los pesos suman 15.


@dataclass(frozen=True, slots=True)
class EffortSessionRow:
    """Fila de datos a nivel de sesión para análisis estadístico."""

    session_id: str
    participant_id: str
    condition: str
    test_score_id: str
    # El bloque de la sesión en la matriz del protocolo (§2.4); vacío si el participante o la
    # partitura no están en ella.
    block: int | None
    duration_ms: int
    duration_s: float
    time_to_first_edit_ms: int | None
    total_measures: int
    total_interventions: int
    edits_count: int
    findings_count: int
    time_per_measure_s: float
    interventions_per_measure: float
    # NASA-TLX del participante en ese bloque (§3.3). Sin dato, la celda queda vacía.
    nasa_tlx_mental: float | None
    nasa_tlx_physical: float | None
    nasa_tlx_temporal: float | None
    nasa_tlx_performance: float | None
    nasa_tlx_effort: float | None
    nasa_tlx_frustration: float | None
    nasa_tlx_raw: float | None
    nasa_tlx_weighted: float | None
    status: str
    created_at: str
    # Fidelidad residual frente a la verdad (§3.2.7, #250). Vacía en los datos sintéticos; el
    # OMR-NED también si musicdiff no puede leer el par (el error queda en su columna).
    residual_ser: float | None = None
    residual_omr_ned: float | None = None
    residual_omr_ned_error: str = ""
    # Del registro que acumula la web (#188, ADR-0050). None en los datos sintéticos, que no
    # los simulan, y en los registros sueltos de `POST /effort`: la celda queda vacía.
    content_interventions: int | None = None
    mark_interventions: int | None = None
    meter_interventions: int | None = None
    findings_dismissed: int | None = None
    findings_restored: int | None = None
    suggestions_applied: int | None = None
    suggestions_rejected: int | None = None

    def to_csv_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MeasureInterventionRow:
    """Fila desagregada por compás para modelos de efectos mixtos."""

    session_id: str
    participant_id: str
    condition: str
    test_score_id: str
    measure_number: int
    interventions_count: int

    def to_csv_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class NasaTlx:
    """Un cuestionario NASA-TLX: las seis subescalas y, si se recogieron, sus pesos."""

    scales: dict[str, float]
    weights: dict[str, int] | None = None

    @property
    def raw(self) -> float:
        """Raw TLX: la media de las seis subescalas."""
        return round(sum(self.scales.values()) / len(TLX_SCALES), 2)

    @property
    def weighted(self) -> float | None:
        """TLX ponderado: cada subescala por las veces que se eligió en las 15 parejas."""
        if self.weights is None:
            return None
        total = sum(self.scales[scale] * self.weights[scale] for scale in TLX_SCALES)
        return round(total / TLX_PAIRS, 2)


# ---------------------------------------------------------------------------
# El estudio: la matriz, la verdad de cada partitura y el NASA-TLX.
# ---------------------------------------------------------------------------


def load_study_manifest(path: Path = STUDY_MANIFEST) -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return manifest


def study_assignments(manifest: Mapping[str, Any]) -> dict[str, dict[str, tuple[int, str]]]:
    """De cada participante, el bloque y la condición de cada partitura (protocolo §2.4)."""

    matrix: dict[str, list[dict[str, str]]] = manifest["estudio"]["matriz"]
    return {
        participant: {
            assignment["partitura"]: (block, assignment["condicion"])
            for block, assignment in enumerate(blocks, start=1)
        }
        for participant, blocks in matrix.items()
    }


def _study_scores(assignments: Mapping[str, Mapping[str, tuple[int, str]]]) -> list[str]:
    return sorted({score for per_score in assignments.values() for score in per_score})


def load_truths(manifest: Mapping[str, Any], bank_dir: Path) -> dict[str, ScoreIR]:
    """La verdad de cada partitura evaluada del banco, comprobada contra su sha256.

    Falla con un mensaje claro si falta el banco o una verdad no es la del manifiesto
    (`CLAUDE.md` §8.1): sin ella no hay fidelidad residual que medir.
    """

    wanted = set(_study_scores(study_assignments(manifest)))
    entries = [entry for entry in manifest["partituras"] if entry["id"] in wanted]
    problems: list[str] = []
    paths: dict[str, Path] = {}
    for entry in entries:
        path = bank_dir / entry["salida"]["verdad"]
        if not path.is_file():
            problems.append(f"falta {path.name}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]["verdad"]:
            problems.append(f"{path.name} no tiene el sha256 del manifiesto")
        else:
            paths[entry["id"]] = path
    if problems or len(paths) != len(wanted):
        raise ValueError(
            f"Sin la verdad del banco del estudio en {bank_dir} no hay fidelidad residual "
            f"({'; '.join(problems) or 'faltan partituras en el manifiesto'}). Regenéralo con "
            f"`{REGENERATE_BANK}` o indica la carpeta con --bank-dir."
        )
    return {score_id: read_score(path) for score_id, path in paths.items()}


def _tlx_number(raw: str | None, what: str, line: int) -> float:
    try:
        value = float((raw or "").strip().replace(",", "."))
    except ValueError:
        raise ValueError(f"NASA-TLX, línea {line}: {what} no es un número ({raw!r}).") from None
    if not 0.0 <= value <= 100.0:
        raise ValueError(f"NASA-TLX, línea {line}: {what} = {value} no está entre 0 y 100.")
    return value


def load_nasa_tlx(path: Path) -> dict[tuple[str, int], NasaTlx]:
    """Lee el CSV del NASA-TLX: una fila por participante y bloque (protocolo §3.3, #244).

    Columnas: `participant_id`, `block` (1 a 4) y las seis subescalas de 0 a 100 (`mental`,
    `physical`, `temporal`, `performance`, `effort`, `frustration`). Si se hicieron las
    comparaciones por parejas, `weight_<subescala>` con las veces que se eligió cada una (suman
    15); si no, esas columnas faltan o van vacías. Un cuestionario que no se recogió no lleva
    fila: su celda queda vacía. Un valor que falta o se sale de rango es un error, no un 0.
    """

    if not path.is_file():
        raise ValueError(f"No existe el CSV del NASA-TLX: {path}")
    result: dict[tuple[str, int], NasaTlx] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or ())
        missing = {"participant_id", "block", *TLX_SCALES} - columns
        if missing:
            raise ValueError(
                f"Al CSV del NASA-TLX le faltan columnas: {', '.join(sorted(missing))}."
            )
        for line, row in enumerate(reader, start=2):
            participant = (row["participant_id"] or "").strip()
            try:
                block = int((row["block"] or "").strip())
            except ValueError:
                raise ValueError(f"NASA-TLX, línea {line}: el bloque no es un número.") from None
            if not participant or not 1 <= block <= 4:
                raise ValueError(f"NASA-TLX, línea {line}: participante o bloque inválidos.")
            if (participant, block) in result:
                raise ValueError(
                    f"NASA-TLX, línea {line}: {participant}, bloque {block}, repetido."
                )
            scales = {scale: _tlx_number(row[scale], scale, line) for scale in TLX_SCALES}
            raw_weights = {
                scale: (row.get(f"weight_{scale}") or "").strip() for scale in TLX_SCALES
            }
            weights: dict[str, int] | None = None
            if any(raw_weights.values()):
                try:
                    weights = {scale: int(value) for scale, value in raw_weights.items()}
                except ValueError:
                    raise ValueError(
                        f"NASA-TLX, línea {line}: los pesos van todos o ninguno, y son enteros."
                    ) from None
                if min(weights.values()) < 0 or sum(weights.values()) != TLX_PAIRS:
                    raise ValueError(
                        f"NASA-TLX, línea {line}: los pesos suman {sum(weights.values())}, "
                        f"y deben sumar {TLX_PAIRS}."
                    )
            result[(participant, block)] = NasaTlx(scales=scales, weights=weights)
    return result


# ---------------------------------------------------------------------------
# Compases y fidelidad residual.
# ---------------------------------------------------------------------------


def measure_count(score: ScoreIR) -> int:
    """Los compases de la partitura: los del pentagrama que más tiene, en todas las partes."""
    counts = [len(staff.measures) for part in score.parts for staff in part.staves]
    return max(1, max(counts, default=0))


def ser_normalized(score: ScoreIR) -> ScoreIR:
    """La partitura con los eventos de cada compás en un orden que no depende de la voz.

    El número de voz y el orden de las notas de un acorde cambian la secuencia de símbolos de
    la SER aunque lo que se ve sea igual (protocolo §2.3, riesgos): se ordenan por dónde
    empiezan, los silencios antes que las notas, por altura (con la armadura) y por figura.
    """

    parts = []
    for part in score.parts:
        staves = []
        for staff in part.staves:
            fifths = 0
            measures = []
            for measure in staff.measures:
                if measure.key_signature is not None:
                    fifths = measure.key_signature.fifths
                keyed = []
                for events in voices_of(measure).values():
                    for event, onset in zip(events, onsets(events), strict=True):
                        pitch = resolve_pitch_with_key_signature(event.pitch, fifths) or ""
                        key = (
                            onset,
                            event.kind is EventKind.NOTE,
                            pitch,
                            event.duration_beats or Fraction(0),
                        )
                        keyed.append((key, event))
                ordered = tuple(event for _, event in sorted(keyed, key=lambda item: item[0]))
                measures.append(replace(measure, events=ordered))
            staves.append(replace(staff, measures=tuple(measures)))
        parts.append(replace(part, staves=tuple(staves)))
    return replace(score, parts=tuple(parts))


def residual_fidelity(final: ScoreIR, truth: ScoreIR) -> tuple[float, float | None, str]:
    """SER y OMR-NED del estado final frente a la verdad, y el error de musicdiff si lo hubo.

    La SER se calcula con los eventos de cada compás normalizados (`ser_normalized`); el
    OMR-NED compara con musicdiff la notación tal cual, sin el símbolo del compás, como
    `exp_14` y `exp_15` (ADR-0044 §1). Sin el extra `metrics` falla, no se imputa.
    """

    ser = score_ser_pair(ser_normalized(truth), ser_normalized(final)).ser
    exporter = Music21ScoreExporter()
    with tempfile.TemporaryDirectory(prefix="exp10-ned-") as work:
        folder = Path(work)
        truth_file = folder / "truth.musicxml"
        final_file = folder / "final.musicxml"
        try:
            truth_file.write_text(
                exporter.to_musicxml(without_time_symbols(truth)), encoding="utf-8"
            )
            final_file.write_text(
                exporter.to_musicxml(without_time_symbols(final)), encoding="utf-8"
            )
            return ser, omr_ned_pair(final_file, truth_file).omr_ned, ""
        except MetricsExtraMissing:
            raise
        except Exception as exc:  # un par que musicdiff no lee se registra, no se imputa
            return ser, None, f"{type(exc).__name__}: {exc}"


def final_score(db: DbSession, session: SessionRecord) -> ScoreIR:
    """El estado al que llega la sesión: su documento con todo el log aplicado."""
    document = ScoreDocument.from_primitive(session.document)
    edits = SqlAlchemyEditEventRepository(db).list_events(session.id)
    return materialize(document.score, edits)


# ---------------------------------------------------------------------------
# Datos sintéticos (`--smoke`): solo prueban la exportación.
# ---------------------------------------------------------------------------


def generate_synthetic_study_dataset(
    seed: int = DEFAULT_SEED,
) -> tuple[list[EffortSessionRow], list[MeasureInterventionRow]]:
    """Genera datos sintéticos siguiendo el diseño experimental de Cuadrado Latino.

    8 participantes seudónimos (P01..P08) x 4 partituras de prueba (TS-01..TS-04).
    Cada participante realiza 4 sesiones contrabalanceadas (2 asistidas, 2 no asistidas).
    """
    rng = random.Random(seed)
    participants = [f"P{i:02d}" for i in range(1, 9)]
    test_scores: list[tuple[str, int]] = [
        ("TS-01", 4),  # Monofónica básica (4 compases)
        ("TS-02", 8),  # Con armaduras y alteraciones (8 compases)
        ("TS-03", 8),  # Rítmica sincopada / ligaduras (8 compases)
        ("TS-04", 12),  # Polifonía / dos pentagramas pianoform (12 compases)
    ]

    session_rows: list[EffortSessionRow] = []
    measure_rows: list[MeasureInterventionRow] = []

    for p_idx, p_id in enumerate(participants):
        for s_idx, (score_id, n_measures) in enumerate(test_scores):
            session_id = f"sess-study-{p_id.lower()}-{score_id.lower()}"
            # Contrabalanceo 2x2: alternancia por participante y partitura
            is_assisted = (p_idx + s_idx) % 2 == 0
            condition = "assisted" if is_assisted else "unassisted"

            if is_assisted:
                # Condición asistida: tiempo e intervenciones reducidas gracias al validador
                base_time_per_m = rng.uniform(7.5, 11.5)
                interv_rate = rng.uniform(0.5, 1.1)
                time_to_first = rng.randint(2500, 5000)
                findings = rng.randint(1, 4)
                low, high = 18.0, 46.0
            else:
                # Condición no asistida: mayor tiempo de inspección y esfuerzo cognitivo
                base_time_per_m = rng.uniform(15.0, 24.0)
                interv_rate = rng.uniform(1.4, 2.3)
                time_to_first = rng.randint(6000, 14000)
                findings = 0
                low, high = 42.0, 78.0

            tlx = NasaTlx(scales={scale: round(rng.uniform(low, high), 1) for scale in TLX_SCALES})
            duration_s = round(base_time_per_m * n_measures, 2)
            duration_ms = int(duration_s * 1000)

            total_interventions = 0
            for m in range(1, n_measures + 1):
                # Mayor probabilidad de intervención en compases complejos
                p_err = interv_rate * 0.4
                interv_count = rng.choices([0, 1, 2, 3], weights=[1.0, p_err, p_err * 0.4, 0.1])[0]
                total_interventions += interv_count
                measure_rows.append(
                    MeasureInterventionRow(
                        session_id=session_id,
                        participant_id=p_id,
                        condition=condition,
                        test_score_id=score_id,
                        measure_number=m,
                        interventions_count=interv_count,
                    )
                )

            edits_count = total_interventions + rng.randint(0, 2)
            time_per_m_s = round(duration_s / n_measures, 2)
            interv_per_m = round(total_interventions / n_measures, 2)

            session_rows.append(
                EffortSessionRow(
                    session_id=session_id,
                    participant_id=p_id,
                    condition=condition,
                    test_score_id=score_id,
                    block=s_idx + 1,
                    duration_ms=duration_ms,
                    duration_s=duration_s,
                    time_to_first_edit_ms=time_to_first,
                    total_measures=n_measures,
                    total_interventions=total_interventions,
                    edits_count=edits_count,
                    findings_count=findings,
                    time_per_measure_s=time_per_m_s,
                    interventions_per_measure=interv_per_m,
                    nasa_tlx_mental=tlx.scales["mental"],
                    nasa_tlx_physical=tlx.scales["physical"],
                    nasa_tlx_temporal=tlx.scales["temporal"],
                    nasa_tlx_performance=tlx.scales["performance"],
                    nasa_tlx_effort=tlx.scales["effort"],
                    nasa_tlx_frustration=tlx.scales["frustration"],
                    nasa_tlx_raw=tlx.raw,
                    nasa_tlx_weighted=None,
                    status="finalized",
                    created_at=datetime.now(UTC).isoformat(),
                )
            )

    return session_rows, measure_rows


# ---------------------------------------------------------------------------
# Datos reales.
# ---------------------------------------------------------------------------


def _study_sessions(
    db: DbSession, scores: list[str] | None = None
) -> list[tuple[SessionRecord, UserRecord]]:
    """Las sesiones finalizadas del estudio, por orden de creación.

    Solo las de las partituras evaluadas (`scores`, por defecto las de la matriz del
    manifiesto: el calentamiento no se evalúa) y de cuentas de transcriptor que no son del
    registro público (ADR-0022): ni las pruebas del investigador ni las del registro. Una
    partitura sin finalizar no entra en el análisis (protocolo §3.4, #244).
    """
    wanted = (
        scores if scores is not None else _study_scores(study_assignments(load_study_manifest()))
    )
    stmt = (
        select(SessionRecord, UserRecord)
        .join(UserRecord, SessionRecord.owner_id == UserRecord.id)
        .where(UserRecord.self_registered.is_(False))
        .where(UserRecord.role == "transcriptor")
        .where(SessionRecord.status == "finalized")
        .where(SessionRecord.test_score_id.in_(wanted))
        .order_by(SessionRecord.created_at)
    )
    return [(sess, user) for sess, user in db.execute(stmt).all()]


def _session_effort(db: DbSession, session_id: str) -> EffortMetricsRecord | None:
    """El registro que acumula la web (uno por sesión, ADR-0050) si midió algún tramo o, si no,
    el registro suelto más reciente de `POST /effort` (#13).

    Un registro acumulado sin tramos no es una medición: lo crea también un descarte o una
    restauración (`add_finding_action`) aunque ningún tramo de tiempo llegara al servidor.
    """
    records = db.scalars(
        select(EffortMetricsRecord)
        .where(EffortMetricsRecord.session_id == session_id)
        .order_by(EffortMetricsRecord.created_at.desc(), EffortMetricsRecord.id.desc())
    ).all()
    accumulated = next((r for r in records if r.accumulated), None)
    if accumulated is not None and accumulated.segments:
        return accumulated
    return next((r for r in records if not r.accumulated), None)


def finalized_sessions_without_effort(db: DbSession, scores: list[str] | None = None) -> list[str]:
    """Sesiones del estudio finalizadas sin ningún registro de esfuerzo: no se midieron y no
    entran en las filas, pero el resumen las nombra para que no se pierdan en silencio."""
    return [
        sess.id for sess, _ in _study_sessions(db, scores) if _session_effort(db, sess.id) is None
    ]


def _class_total(by_class: dict[str, Any], name: str) -> int:
    return sum(int(count) for count in (by_class.get(name) or {}).values())


def extract_study_data_from_db(
    db: DbSession,
    *,
    assignments: Mapping[str, Mapping[str, tuple[int, str]]] | None = None,
    truths: Mapping[str, ScoreIR] | None = None,
    nasa_tlx: Mapping[tuple[str, int], NasaTlx] | None = None,
) -> tuple[list[EffortSessionRow], list[MeasureInterventionRow]]:
    """Extrae las sesiones de estudio y métricas persistidas en la base de datos.

    Solo las sesiones finalizadas de las cuentas del estudio con un registro de esfuerzo: sin
    él no hay medición (`finalized_sessions_without_effort`). Con `truths`, mide la fidelidad
    residual; con `nasa_tlx`, une el cuestionario por participante y bloque. Sin ellos, esas
    celdas quedan vacías.
    """
    plan = assignments if assignments is not None else study_assignments(load_study_manifest())
    session_rows: list[EffortSessionRow] = []
    measure_rows: list[MeasureInterventionRow] = []

    for sess, user in _study_sessions(db, _study_scores(plan)):
        effort = _session_effort(db, sess.id)
        if effort is None:
            continue

        duration_ms = effort.duration_ms
        time_to_first = effort.time_to_first_edit_ms
        interventions = effort.interventions or {}
        accumulated = bool(effort.accumulated)
        by_class = effort.interventions_by_class or {}
        score_id = sess.test_score_id or "unspecified"

        # El estado final de la sesión: sus compases y su fidelidad residual.
        final = final_score(db, sess)
        total_measures = measure_count(final)
        residual_ser: float | None = None
        residual_ned: float | None = None
        residual_error = ""
        if truths is not None:
            residual_ser, residual_ned, residual_error = residual_fidelity(final, truths[score_id])

        assignment = plan.get(user.username, {}).get(score_id)
        block = assignment[0] if assignment is not None else None
        tlx = nasa_tlx.get((user.username, block)) if nasa_tlx and block is not None else None

        total_interv = sum(int(v) for v in interventions.values())
        for m_str, count in interventions.items():
            try:
                m_num = int(m_str)
            except ValueError:
                m_num = 1
            measure_rows.append(
                MeasureInterventionRow(
                    session_id=sess.id,
                    participant_id=user.username,
                    condition=sess.condition,
                    test_score_id=score_id,
                    measure_number=m_num,
                    interventions_count=int(count),
                )
            )

        # Contar ediciones
        edits_count = (
            db.scalar(
                select(func.count(EditEventRecord.id)).where(EditEventRecord.session_id == sess.id)
            )
            or 0
        )

        # Contar hallazgos activos
        findings_count = (
            db.scalar(
                select(func.count(FindingRecord.id)).where(
                    FindingRecord.session_id == sess.id,
                    FindingRecord.status == "active",
                )
            )
            or 0
        )

        duration_s = round(duration_ms / 1000.0, 2)
        time_per_m = round(duration_s / total_measures, 2)
        interv_per_m = round(total_interv / total_measures, 2)

        def scale(name: str, tlx: NasaTlx | None = tlx) -> float | None:
            return tlx.scales[name] if tlx is not None else None

        session_rows.append(
            EffortSessionRow(
                session_id=sess.id,
                participant_id=user.username,
                condition=sess.condition,
                test_score_id=score_id,
                block=block,
                duration_ms=duration_ms,
                duration_s=duration_s,
                time_to_first_edit_ms=time_to_first,
                total_measures=total_measures,
                total_interventions=total_interv,
                edits_count=int(edits_count),
                findings_count=int(findings_count),
                time_per_measure_s=time_per_m,
                interventions_per_measure=interv_per_m,
                nasa_tlx_mental=scale("mental"),
                nasa_tlx_physical=scale("physical"),
                nasa_tlx_temporal=scale("temporal"),
                nasa_tlx_performance=scale("performance"),
                nasa_tlx_effort=scale("effort"),
                nasa_tlx_frustration=scale("frustration"),
                nasa_tlx_raw=tlx.raw if tlx is not None else None,
                nasa_tlx_weighted=tlx.weighted if tlx is not None else None,
                status=sess.status,
                created_at=sess.created_at.isoformat() if sess.created_at else "",
                residual_ser=residual_ser,
                residual_omr_ned=residual_ned,
                residual_omr_ned_error=residual_error,
                content_interventions=_class_total(by_class, "content") if accumulated else None,
                mark_interventions=_class_total(by_class, "mark") if accumulated else None,
                meter_interventions=_class_total(by_class, "meter") if accumulated else None,
                findings_dismissed=effort.findings_dismissed if accumulated else None,
                findings_restored=effort.findings_restored if accumulated else None,
                suggestions_applied=effort.suggestions_applied if accumulated else None,
                suggestions_rejected=effort.suggestions_rejected if accumulated else None,
            )
        )

    return session_rows, measure_rows


def _mean(values: list[float | None]) -> float | None:
    """La media de los valores que hay; sin ninguno, vacía (no 0)."""
    present = [value for value in values if value is not None]
    return round(sum(present) / len(present), 4) if present else None


def _reduction(assisted: float | None, unassisted: float | None) -> float | None:
    if assisted is None or unassisted is None or unassisted <= 0:
        return None
    return round((1.0 - (assisted / unassisted)) * 100.0, 2)


def compute_summary_statistics(
    session_rows: list[EffortSessionRow],
) -> dict[str, Any]:
    """Calcula estadísticas descriptivas agregadas comparando assisted vs unassisted.

    Una media sin datos (sin NASA-TLX, sin fidelidad o sin sesiones de una condición) queda
    vacía, y la reducción que dependa de ella también: nunca 0.
    """

    def condition_summary(rows: list[EffortSessionRow]) -> dict[str, Any]:
        return {
            "sessions_count": len(rows),
            "mean_duration_s": _mean([r.duration_s for r in rows]),
            "mean_time_per_measure_s": _mean([r.time_per_measure_s for r in rows]),
            "mean_interventions_per_measure": _mean([r.interventions_per_measure for r in rows]),
            "nasa_tlx_count": sum(r.nasa_tlx_raw is not None for r in rows),
            "mean_nasa_tlx_raw": _mean([r.nasa_tlx_raw for r in rows]),
            "mean_nasa_tlx_weighted": _mean([r.nasa_tlx_weighted for r in rows]),
            "residual_count": sum(r.residual_ser is not None for r in rows),
            "mean_residual_ser": _mean([r.residual_ser for r in rows]),
            "mean_residual_omr_ned": _mean([r.residual_omr_ned for r in rows]),
        }

    assisted = condition_summary([r for r in session_rows if r.condition == "assisted"])
    unassisted = condition_summary([r for r in session_rows if r.condition == "unassisted"])

    return {
        "study_protocol": "Cadenza HITL Effort Measurement Protocol (Within-Subjects Latin Square)",
        "protocol_version": "1.0",
        "total_sessions": len(session_rows),
        "total_participants": len({r.participant_id for r in session_rows}),
        "conditions": {"assisted": assisted, "unassisted": unassisted},
        "effort_reduction": {
            "time_per_measure_reduction_percent": _reduction(
                assisted["mean_time_per_measure_s"], unassisted["mean_time_per_measure_s"]
            ),
            "interventions_per_measure_reduction_percent": _reduction(
                assisted["mean_interventions_per_measure"],
                unassisted["mean_interventions_per_measure"],
            ),
            "cognitive_workload_reduction_percent": _reduction(
                assisted["mean_nasa_tlx_raw"], unassisted["mean_nasa_tlx_raw"]
            ),
        },
    }


def _matrix_checks(
    session_rows: list[EffortSessionRow],
    assignments: Mapping[str, Mapping[str, tuple[int, str]]],
    nasa_tlx: Mapping[tuple[str, int], NasaTlx] | None,
) -> dict[str, Any]:
    """Lo que no cuadra con la matriz o con el NASA-TLX, para que no se pierda en silencio."""

    outside = [r.session_id for r in session_rows if r.block is None]
    mismatched = [
        r.session_id
        for r in session_rows
        if r.block is not None and assignments[r.participant_id][r.test_score_id][1] != r.condition
    ]
    matched = {(r.participant_id, r.block) for r in session_rows if r.block is not None}
    unmatched_tlx = sorted(
        f"{participant}#{block}"
        for participant, block in (nasa_tlx or {})
        if (participant, block) not in matched
    )
    return {
        "sessions_outside_matrix": outside,
        "sessions_with_condition_not_in_matrix": mismatched,
        "nasa_tlx_rows_without_session": unmatched_tlx,
        "residual_omr_ned_errors": [r.session_id for r in session_rows if r.residual_omr_ned_error],
    }


def run_effort_study_export(
    *,
    db_url: str | None = None,
    output_dir: Path | str | None = None,
    smoke: bool = False,
    seed: int = DEFAULT_SEED,
    bank_dir: Path | str | None = None,
    nasa_tlx_csv: Path | str | None = None,
) -> dict[str, Any]:
    """Ejecuta la exportación y análisis del estudio de esfuerzo a formato tabular.

    Lanza `ValueError` sin `db_url` (salvo con `smoke`), si la base no tiene sesiones del
    estudio, si falta el banco con la verdad (`bank_dir`, por defecto el del manifiesto), si el
    CSV del NASA-TLX no es válido o si `smoke` escribiría en `results/`.
    """
    if smoke:
        # Los datos sintéticos nunca van a `results/`, donde pasarían por el estudio (#271).
        if output_dir is None or _is_results_dir(Path(output_dir)):
            raise ValueError(
                "--smoke genera datos sintéticos y no escribe en results/: indica con "
                "--output-dir otra carpeta."
            )
    elif not db_url:
        raise ValueError(
            "Sin --db-url no hay sesiones del estudio que exportar. Para probar la exportación "
            "con datos sintéticos, usa --smoke con un --output-dir fuera de results/."
        )
    out_dir = Path(output_dir) if output_dir is not None else RESULTS_DIR

    session_rows: list[EffortSessionRow] = []
    measure_rows: list[MeasureInterventionRow] = []

    synthetic = smoke
    unmeasured: list[str] = []
    checks: dict[str, Any] = {}
    sources: dict[str, Any] = {}
    if smoke:
        session_rows, measure_rows = generate_synthetic_study_dataset(seed=seed)
    else:
        assert db_url is not None
        manifest = load_study_manifest()
        assignments = study_assignments(manifest)
        scores = _study_scores(assignments)
        engine = create_engine_for_url(db_url)
        create_schema(engine)
        factory = create_session_factory(engine)
        with factory() as db:
            if not _study_sessions(db, scores):
                # Sin sesiones del estudio no se inventan: un resultado es una medición (#96, #271).
                raise ValueError(
                    "La base de datos no tiene sesiones del estudio finalizadas y medidas (las "
                    "cuentas del registro público no cuentan): no hay nada que exportar."
                )
            bank = Path(bank_dir) if bank_dir is not None else REPO_ROOT / manifest["salida"]
            truths = load_truths(manifest, bank)
            tlx = load_nasa_tlx(Path(nasa_tlx_csv)) if nasa_tlx_csv is not None else None
            session_rows, measure_rows = extract_study_data_from_db(
                db, assignments=assignments, truths=truths, nasa_tlx=tlx
            )
            unmeasured = finalized_sessions_without_effort(db, scores)
        if not session_rows:
            raise ValueError(
                "La base de datos no tiene sesiones del estudio finalizadas y medidas (las "
                "cuentas del registro público no cuentan): no hay nada que exportar."
            )
        checks = _matrix_checks(session_rows, assignments, tlx)
        sources = {
            "bank_dir": str(bank),
            "nasa_tlx_csv": str(nasa_tlx_csv) if nasa_tlx_csv is not None else None,
        }
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Exportar esfuerzo a nivel de sesión CSV
    sessions_csv_path = out_dir / "effort_study_sessions.csv"
    if session_rows:
        fieldnames = list(session_rows[0].to_csv_dict().keys())
        with sessions_csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in session_rows:
                writer.writerow(r.to_csv_dict())

    # 2. Exportar esfuerzo desagregado por compás CSV
    measures_csv_path = out_dir / "effort_study_by_measure.csv"
    if measure_rows:
        m_fieldnames = list(measure_rows[0].to_csv_dict().keys())
        with measures_csv_path.open("w", newline="", encoding="utf-8") as f:
            m_writer = csv.DictWriter(f, fieldnames=m_fieldnames)
            m_writer.writeheader()
            for m in measure_rows:
                m_writer.writerow(m.to_csv_dict())

    # 3. Exportar resumen estadístico JSON
    summary = compute_summary_statistics(session_rows)
    # Sin base de datos de un estudio real, las sesiones son sintéticas: sirven para
    # probar la exportación, no como resultado del estudio con participantes (#96).
    summary["data_source"] = "synthetic" if synthetic else "database"
    summary["simulated"] = synthetic
    # Finalizadas sin registro de esfuerzo: no se midieron y no están en las filas (ADR-0050).
    summary["finalized_sessions_without_effort"] = unmeasured
    summary.update(checks)
    summary.update(sources)
    if synthetic:
        summary["simulation_warning"] = SYNTHETIC_WARNING
    summary_json_path = out_dir / "effort_study_summary.json"
    with summary_json_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # 4. Registrar información de ejecución, junto a lo exportado y con su procedencia
    run_info = get_run_info("exp_10_effort_study", seed=seed)
    run_info["data_source"] = summary["data_source"]
    run_info["simulated"] = synthetic
    run_info.update(sources)
    if synthetic:
        run_info["simulation_warning"] = SYNTHETIC_WARNING
    (out_dir / "exp_10_run_info.json").write_text(
        json.dumps(run_info, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return summary


def _is_results_dir(path: Path) -> bool:
    """Si `path` es `results/` del repositorio (o la carpeta de resultados en uso) o está dentro."""
    target = path.resolve()
    for candidate in (RESULTS_DIR, REPO_ROOT / "results"):
        resolved = candidate.resolve()
        if target == resolved or resolved in target.parents:
            return True
    return False


def add_study_arguments(parser: argparse.ArgumentParser) -> None:
    """Las opciones del banco y del NASA-TLX, compartidas con `ml export-effort`."""
    parser.add_argument(
        "--bank-dir",
        default=None,
        help=(
            "Carpeta del banco del estudio con la verdad de cada partitura (por defecto, "
            "banco_estudio/; se regenera con scripts/build_study_bank.py)"
        ),
    )
    parser.add_argument(
        "--nasa-tlx",
        default=None,
        help=(
            "CSV del NASA-TLX: participant_id, block, las seis subescalas de 0 a 100 y, si se "
            "recogieron, weight_<subescala> (protocolo §6.2)"
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Exp 10: Exportación y análisis de esfuerzo con participantes (HITL)."
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="URL de la base de datos con las sesiones del estudio (obligatoria salvo con --smoke)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directorio de destino de los reportes CSV y JSON (por defecto, results/)",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help=(
            "Prueba la exportación con datos sintéticos, marcados como simulados; "
            "exige un --output-dir fuera de results/"
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Semilla determinista",
    )
    add_study_arguments(parser)
    args = parser.parse_args()

    try:
        summary = run_effort_study_export(
            db_url=args.db_url,
            output_dir=args.output_dir,
            smoke=args.smoke,
            seed=args.seed,
            bank_dir=args.bank_dir,
            nasa_tlx_csv=args.nasa_tlx,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
