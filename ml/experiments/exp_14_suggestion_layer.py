"""Experimento 14: primera medición de la capa de sugerencias (#257, ADR-0036).

Entrena la capa con la partición `train` del corpus de correcciones de #255 y la mide en la
partición `test`, por el camino de producción: las reglas (`ValidationEngine`) y después la
capa con el filtro de admisibilidad de los casos de uso (`cadenza.application.suggest`:
`validate_after`, sin duplicados, tres por hallazgo), sobre el `ScoreIR` que leyó HOMR (la
predicción de `exp_12`). La verdad es la del corpus: la corrección del corrector ideal de
cada evento leído, de cada hueco y de cada compás.

Mide:
1. Validación cruzada de 5 pliegues agrupados por obra (registro RISM) dentro de `train`:
   cada pliegue entrena con los otros cuatro (eligiendo sus umbrales con su propia validación
   cruzada interna, como `train`) y se mide en el suyo; media y desviación de las métricas
   principales. Los pliegues usan la semilla del experimento, no la de la configuración.
2. Sugerencias a los posibles errores de las reglas: acierto de la primera y de las tres
   primeras (las admisibles que mostraría la web) frente a la verdad, sobre los hallazgos con
   sugerencias y sobre los que tienen el arreglo verdadero entre sus candidatos; la línea base
   es el orden de la propia regla, por el mismo filtro.
3. Errores que las reglas no ven: precisión y *recall* por compás con la definición de
   `exp_06` (`cadenza.learning.evaluate_measures`), con las reglas solas y con las reglas más
   los posibles errores propios de la capa que se mostrarían, y la cobertura por categoría
   (alteración, duración, altura, estructura y clave/armadura). Las correcciones reales por
   compás salen de los registros del corpus, que son las de `derive_edit_events` frente a la
   altura que suena (no frente al MEI tal cual, como `exp_06`; ver #255).
4. Antes y después: SER y OMR-NED frente a la verdad, con HOMR solo y con HOMR más las
   sugerencias aplicadas: las de confianza alta (la primera de cada hallazgo, si es `high`) y,
   aparte, todas las primeras. Se aplican como una persona, una tras otra, con el ancla
   traducida (ADR-0011) y `validate_after` sobre el estado al que llegan.
5. Daño, de las sugerencias elegidas y, aparte, de las que se llegaron a aplicar: por evento
   (cuántas estropearían un evento correcto, arreglarían mal uno con error, insertarían donde
   no falta nada o un evento distinto del que falta) y por atributo (cuántas cambiarían una
   alteración, una altura o una duración que no tenían error, o tocarían un evento que la
   verdad borra). Una sugerencia acierta si su familia y su valor (la altura o la duración
   resultantes, o el evento insertado) son los de la verdad.
6. Curva de aprendizaje: la capa entrenada con el 10, el 25, el 50 y el 100 % de las obras de
   `train` (submuestreo anidado con semilla, por obra para no partir una obra), medida en
   `test`; se informa cuántas correcciones tiene cada punto.
7. Sesiones del estudio: no hay todavía; el resultado lo dice y no inventa ninguna cifra.

Con `--min-level` o `--families`, todo lo anterior (la prueba, los pliegues y la curva) se
mide con la capa envuelta en la política de qué se muestra de la API (`SuggestionPolicy` y
`PolicySuggestionModel`, ADR-0036 enmienda 19): solo las sugerencias de ese nivel de
confianza y de esas familias, y los hallazgos de las reglas, aunque se queden sin ellas. Lo
que no se da no filtra; sin ninguna de las dos, se mide todo lo admisible, como en #287. La
línea base del orden de la regla y las métricas de la promoción (`evaluate`) no pasan por la
política: son las del modelo.

Decisiones de la medición:
- La SER se calcula sin aplicar la armadura (`apply_key_signature=False`): las alturas del
  `ScoreIR` son las que suenan, en la predicción y en la verdad; aplicándola, un Si natural
  leído donde suena Si bemol no contaría como error.
- El OMR-NED compara MusicXML exportados del `ScoreIR` (`Music21ScoreExporter`), la verdad
  y cada variante, para que el antes y el después pasen por el mismo camino; por eso no es el
  OMR-NED de `exp_12`, que compara el MusicXML de HOMR con el MEI.
- La capa se llama sin la red de producción: si falla o pierde hallazgos de las reglas, el
  experimento falla en vez de contarla como una capa que no sugiere nada. Las proporciones sin
  denominador son None, también las de `exp_06` que aquí se recalculan (`binary_metrics`).
- La SER y el OMR-NED medios se calculan sobre los incipits que tienen las tres variantes.
- Antes de medir se comprueba que los registros del corpus son los de la predicción y la
  verdad que se leen (en `test`, regenerándolos; en `train`, lo leído de cada evento): si no,
  la verdad no es la del corpus y el experimento falla.
- El artefacto entrenado se guarda en el directorio de salida y no se registra ni se
  promueve (ADR-0036 §9).

Sin el corpus, la partición, la muestra, alguna predicción o alguna verdad, el experimento
falla con un mensaje claro: no hay valores de reserva (CLAUDE.md §8).

Salidas (`--output-dir`, por defecto `results/`, sin versionar):
- `suggestion_layer_summary.json`: la medición completa, con `run_info`.
- `suggestion_layer_incipits.csv`: una fila por incipit de prueba.
- `suggestion_layer_artifact.json`: el artefacto de la capa entrenada con `train`.
- `exp_14_run_info.json`
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import statistics
import sys
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from cadenza.application import (
    SUGGESTION_FAMILIES,
    PolicySuggestionModel,
    SuggestionModel,
    SuggestionPolicy,
)
from cadenza.domain import ScoreIR, materialize
from cadenza.interchange import Music21ScoreExporter, read_score
from cadenza.learning import (
    SemanticMismatch,
    build_correction_records,
    derive_edit_events,
    is_structurally_equal,
    omr_ned_pair,
    score_ser_pair,
    semantic_note_pitches,
    with_sounding_pitches,
)
from cadenza.learning.suggestion_measurement import (
    POLICIES,
    IncipitCase,
    IncipitMeasurement,
    measure_incipit,
    principal_metrics,
    subsample_works,
    summarize,
)
from cadenza.learning.suggestions import (
    SuggestionsConfig,
    artifact_bytes,
    check_partition,
    evaluate,
    fold_of,
    load_suggestions_config,
    read_corpus,
    train,
    work_of,
)
from cadenza.validation import ValidationEngine
from cadenza.validation.learned import (
    FEATURE_VERSION,
    MODEL_TYPE,
    FrequencyBackoffModel,
    ScoreFeatures,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.experiments.common import (  # noqa: E402
    DATA_DIR,
    DEFAULT_SEED,
    METHODOLOGICAL_LIMITATIONS,
    RESULTS_DIR,
    get_run_info,
    sha256_of_file,
)

DEFAULT_CONFIG = REPO_ROOT / "configs" / "learning" / "suggestions.json"
FOLDS = 5
FRACTIONS = (0.1, 0.25, 0.5, 1.0)
SUMMARY_NAME = "suggestion_layer_summary.json"
CSV_NAME = "suggestion_layer_incipits.csv"
ARTIFACT_NAME = "suggestion_layer_artifact.json"
RUN_INFO_NAME = "exp_14_run_info.json"
VARIANTS = ("homr", "homr_with_high", "homr_with_first")
CSV_FIELDS = [
    "id",
    "work",
    "rule_findings",
    "learned_findings",
    "learned_correct",
    *(
        f"{policy}_{field}"
        for policy in POLICIES
        for field in ("selected", "applied", "damaged_events", "damaged_attributes")
    ),
    *(f"ser_{variant}" for variant in VARIANTS),
    *(f"omr_ned_{variant}" for variant in VARIANTS),
    "omr_ned_error",
]

LIMITATIONS: dict[str, str] = {
    **METHODOLOGICAL_LIMITATIONS,
    "ideal_corrector": (
        "La verdad es la del corrector ideal del corpus de #255: la alineación de coste mínimo "
        "entre lo que leyó HOMR y la altura que suena, no las correcciones de una persona. Una "
        "persona puede corregir lo mismo con otras operaciones."
    ),
    "non_independent_corrections": (
        "Las correcciones no son independientes: están anidadas en incipits y obras (los "
        "pliegues y la partición agrupan por obra, pero los compases y las notas de un incipit "
        "comparten clave, armadura y errores de lectura). Los errores estándar de Wald "
        "subestimarían la incertidumbre."
    ),
    "primus_not_our_pages": (
        "PrIMuS son incipits impresos de una sola voz, cortos y limpios. La capa puede rendir "
        "peor en páginas completas, en piano o en voz con piano (#239)."
    ),
    "current_rules": (
        "Las reglas son las de esta versión del código, no las de #245 y #246; con reglas "
        "nuevas cambian los candidatos y lo que las reglas no ven."
    ),
    "test_reuse": (
        "La partición de prueba es fija y se reutiliza en cada medición y promoción: comparar "
        "versiones una y otra vez sobre ella introduce un sesgo de selección (ADR-0036)."
    ),
    "omr_ned_through_export": (
        "El OMR-NED compara MusicXML exportados del ScoreIR (verdad y variantes), no el MusicXML "
        "de HOMR con el MEI: lo que el ScoreIR no representa no cuenta."
    ),
}


# --- Entradas ----------------------------------------------------------------------------


def _manifest(data_dir: Path) -> tuple[Path, dict[str, Any]]:
    path = data_dir / "primus" / "exp_12" / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"exp_14 necesita la muestra de exp_12 y su manifest ({path}): ejecuta antes "
            "`exp_12_correction_corpus.py sample`, `transcribe` y `build`, o indica `--data`."
        )
    manifest: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if not manifest.get("entries"):
        raise ValueError(f"La muestra {path} no tiene entradas")
    return path, manifest


def _split(split_path: Path, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not split_path.is_file():
        raise FileNotFoundError(
            f"exp_14 necesita la partición fija del corpus ({split_path}), la que escribe "
            "`exp_12_correction_corpus.py build`."
        )
    payload: dict[str, Any] = json.loads(split_path.read_text(encoding="utf-8"))
    side = {incipit: name for name in ("train", "test") for incipit in payload.get(name, ())}
    wrong = sorted(
        {str(r["incipit_id"]) for r in records if side.get(str(r["incipit_id"])) != r.get("split")}
    )
    if wrong:
        raise ValueError(
            f"La partición {split_path} no es la del corpus: {len(wrong)} incipits caen en otro "
            f"lado o no están ({', '.join(wrong[:5])})."
        )
    return payload


def _by_incipit(records: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        groups.setdefault(str(record["incipit_id"]), []).append(record)
    return groups


def _prediction(predictions: Path, incipit: str) -> ScoreIR:
    path = predictions / f"{incipit}.musicxml"
    if not path.is_file():
        raise ValueError(
            f"exp_14: falta la predicción de HOMR de {incipit} ({path}), que está en el corpus: "
            "el corpus y las predicciones no son de la misma ejecución de exp_12."
        )
    return read_score(path)


def _truth(root: Path, entry: Mapping[str, Any] | None, incipit: str) -> ScoreIR:
    """La verdad que suena, como la construye `exp_12`: el MEI con las alturas del `.semantic`."""
    if entry is None:
        raise ValueError(f"exp_14: {incipit} está en el corpus y no en la muestra de exp_12")
    gt_file = root / str(entry["ground_truth"])
    semantic_file = root / str(entry["semantic"])
    for path in (gt_file, semantic_file):
        if not path.is_file():
            raise ValueError(f"exp_14: falta la verdad de {incipit} ({path})")
    try:
        return with_sounding_pitches(
            read_score(gt_file),
            semantic_note_pitches(semantic_file.read_text(encoding="utf-8")),
        )
    except SemanticMismatch as exc:
        raise ValueError(
            f"exp_14: la verdad de {incipit} no es la del corpus (el .semantic no describe "
            f"las notas del MEI: {exc})"
        ) from exc


def _canonical(records: Sequence[Mapping[str, Any]]) -> list[str]:
    return [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in records]


def _check_test_records(
    incipit: str, predicted: ScoreIR, sounding: ScoreIR, records: Sequence[Mapping[str, Any]]
) -> None:
    edits = derive_edit_events(predicted, sounding, document_id=incipit)
    verified = is_structurally_equal(materialize(predicted, edits), sounding)
    again = build_correction_records(
        predicted,
        sounding,
        incipit_id=incipit,
        split=str(records[0]["split"]),
        verified=verified,
    )
    if _canonical(again) != _canonical(records):
        raise ValueError(
            f"exp_14: la predicción y la verdad de {incipit} no dan sus registros del corpus: "
            "la verdad no es la del corpus (¿otra ejecución de exp_12 u otro código?)."
        )


def _check_read(incipit: str, predicted: ScoreIR, records: Sequence[Mapping[str, Any]]) -> None:
    events = ScoreFeatures.of(predicted).events
    corpus_events = [r for r in records if r.get("record") == "event"]
    for record in corpus_events:
        a = record["anchor"]
        position = (a["part"], a["staff"], a["measure"], a["voice"], a["event_index"])
        view = events.get(position)
        if view is None or dict(view.read) != dict(record["read"]):
            raise ValueError(
                f"exp_14: la predicción de {incipit} no es la que leyó el corpus en {position}."
            )
    if len(corpus_events) != len(events):
        raise ValueError(
            f"exp_14: la predicción de {incipit} tiene {len(events)} eventos y el corpus "
            f"{len(corpus_events)}."
        )


# --- En paralelo ------------------------------------------------------------------------


def _worker_init() -> None:
    logging.getLogger("converter21").setLevel(logging.ERROR)
    try:
        from cadenza.omr.power import disable_power_throttling

        disable_power_throttling()  # un cálculo largo en segundo plano no se frena (EcoQoS)
    except ImportError:
        pass


def _map[T, R](function: Callable[[T], R], items: Iterable[T], workers: int) -> list[R]:
    """`map` en orden, en `workers` procesos si son más de uno. Una excepción de un elemento
    detiene el experimento, como en serie."""
    tasks = list(items)
    if workers <= 1 or len(tasks) <= 1:
        return [function(task) for task in tasks]
    with ProcessPoolExecutor(max_workers=workers, initializer=_worker_init) as pool:
        return list(pool.map(function, tasks, chunksize=max(1, len(tasks) // (workers * 8))))


LoadTask = tuple[str, str, tuple[Mapping[str, Any], ...], str, str, Mapping[str, Any] | None]


def _load(task: LoadTask) -> tuple[str, ScoreIR, ScoreIR | None]:
    """Lee la predicción de un incipit (y, en prueba, su verdad) y comprueba que dan sus
    registros del corpus."""
    incipit, side, rows, predictions, root, entry = task
    predicted = _prediction(Path(predictions), incipit)
    if side != "test":
        _check_read(incipit, predicted, rows)
        return incipit, predicted, None
    sounding = _truth(Path(root), entry, incipit)
    _check_test_records(incipit, predicted, sounding, rows)
    return incipit, predicted, sounding


def _omr_ned(task: tuple[str, str]) -> tuple[float | None, str]:
    """El OMR-NED de un par de MusicXML, o el error si musicdiff no lo puede comparar."""
    try:
        return omr_ned_pair(Path(task[0]), Path(task[1])).omr_ned, ""
    except Exception as exc:  # un par que musicdiff no lee se registra, no se imputa
        return None, f"{type(exc).__name__}: {exc}"


# --- Métricas ----------------------------------------------------------------------------


def _distribution(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "median": None, "stdev": None}
    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), 4),
        "median": round(statistics.median(values), 4),
        "stdev": round(statistics.stdev(values), 4) if len(values) > 1 else None,
    }


def _paired(before: Sequence[float | None], after: Sequence[float | None]) -> dict[str, Any]:
    pairs = [(b, a) for b, a in zip(before, after, strict=True) if b is not None and a is not None]
    deltas = [a - b for b, a in pairs]
    return {
        "n": len(pairs),
        "improved": sum(1 for d in deltas if d < 0),
        "worsened": sum(1 for d in deltas if d > 0),
        "unchanged": sum(1 for d in deltas if d == 0),
        "mean_delta": round(statistics.fmean(deltas), 4) if deltas else None,
    }


def _cv_summary(
    folds: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, int]]:
    """Media, desviación y con cuántos pliegues se calcula cada una (los que tienen la
    métrica: sin denominador, un pliegue no la tiene)."""
    names = list(folds[0]["metrics"]) if folds else []
    mean: dict[str, Any] = {}
    stdev: dict[str, Any] = {}
    counted: dict[str, int] = {}
    for name in names:
        values = [float(f["metrics"][name]) for f in folds if f["metrics"][name] is not None]
        mean[name] = round(statistics.fmean(values), 4) if values else None
        stdev[name] = round(statistics.stdev(values), 4) if len(values) > 1 else None
        counted[name] = len(values)
    return mean, stdev, counted


def variants_report(values: Mapping[str, Sequence[float | None]]) -> dict[str, Any]:
    """La SER o el OMR-NED de cada variante y su comparación con HOMR solo, todo sobre los
    mismos incipits: los que tienen medida en las tres variantes."""
    total = len(values[VARIANTS[0]])
    common = [i for i in range(total) if all(values[v][i] is not None for v in VARIANTS)]
    kept = {variant: [values[variant][i] for i in common] for variant in VARIANTS}
    out: dict[str, Any] = {
        "incipits_with_all_variants": len(common),
        "excluded_incipits": total - len(common),
    }
    for variant in VARIANTS:
        out[variant] = _distribution([v for v in kept[variant] if v is not None])
    out["paired_vs_homr"] = {
        variant: _paired(kept["homr"], kept[variant]) for variant in VARIANTS[1:]
    }
    return out


def _families(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        name: {
            "threshold": family.get("threshold"),
            "high_threshold": family.get("high_threshold"),
            "active": family.get("active"),
        }
        for name, family in artifact["families"].items()
    }


def _model(artifact: Mapping[str, Any], label: str) -> FrequencyBackoffModel:
    return FrequencyBackoffModel(artifact, version=label)


def display_policy_of(min_level: str | None, families: str | None) -> SuggestionPolicy | None:
    """La política de qué se muestra de la línea de órdenes, o None sin ninguna de las dos.
    Lo que no se da no filtra: cualquier nivel (`medium`) o todas las familias."""
    if min_level is None and families is None:
        return None
    return SuggestionPolicy.parse(
        "medium" if min_level is None else min_level,
        ",".join(SUGGESTION_FAMILIES) if families is None else families,
    )


def _policy_report(policy: SuggestionPolicy | None) -> dict[str, Any] | None:
    if policy is None:
        return None
    return {
        "min_level": policy.min_level,
        "families": sorted(policy.families),
        "scope": (
            "la prueba, los pliegues y la curva se miden con la capa envuelta en esta política "
            "(PolicySuggestionModel, ADR-0036 enmienda 19); la línea base del orden de la regla "
            "y promotion_metrics, sin ella"
        ),
    }


def _measure(
    cases: Sequence[IncipitCase],
    model: FrequencyBackoffModel,
    validator: ValidationEngine,
    policy: SuggestionPolicy | None = None,
) -> list[IncipitMeasurement]:
    shown: SuggestionModel = model if policy is None else PolicySuggestionModel(model, policy)
    return [measure_incipit(case, shown, validator) for case in cases]


def _corrections(records: Sequence[Mapping[str, Any]]) -> int:
    return sum(
        1
        for r in records
        if r.get("split") == "train"
        and r.get("verified")
        and r.get("record") in ("event", "insertion")
        and r.get("correction")
    )


def _export(score: ScoreIR, path: Path, exporter: Music21ScoreExporter) -> Path:
    path.write_text(exporter.to_musicxml(score), encoding="utf-8")
    return path


# --- El experimento ----------------------------------------------------------------------


def run(
    *,
    corpus_path: Path | None = None,
    split_path: Path | None = None,
    data_dir: Path = DATA_DIR,
    config_path: Path = DEFAULT_CONFIG,
    output_dir: Path | None = None,
    seed: int = DEFAULT_SEED,
    with_omr_ned: bool = True,
    workers: int = 1,
    display_policy: SuggestionPolicy | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    results = RESULTS_DIR if output_dir is None else output_dir
    corpus_path = corpus_path or RESULTS_DIR / "correction_corpus.jsonl"
    split_path = split_path or RESULTS_DIR / "correction_corpus_split.json"
    if not corpus_path.is_file():
        raise FileNotFoundError(
            f"exp_14 necesita el corpus de correcciones de exp_12 ({corpus_path}): ejecuta "
            "antes `exp_12_correction_corpus.py build` o indica `--corpus`."
        )
    records = read_corpus(corpus_path)
    split_payload = _split(split_path, records)
    manifest_path, manifest = _manifest(data_dir)
    root = manifest_path.parents[2]
    predictions = manifest_path.parent / "predictions"
    homr_info_file = predictions / "run_info.json"
    if not homr_info_file.is_file():
        raise ValueError(f"Faltan el motor y el dispositivo de las predicciones ({homr_info_file})")
    homr_info = json.loads(homr_info_file.read_text(encoding="utf-8"))
    config: SuggestionsConfig = load_suggestions_config(config_path)
    entries = {str(e["id"]): e for e in manifest["entries"]}

    # Los incipits medibles: los verificados del corpus (los únicos con etiquetas de confianza).
    groups = _by_incipit(records)
    verified = {
        incipit: rows for incipit, rows in groups.items() if all(r.get("verified") for r in rows)
    }
    cases: dict[str, list[IncipitCase]] = {"train": [], "test": []}
    truths: dict[str, ScoreIR] = {}
    tasks: list[LoadTask] = [
        (
            incipit,
            str(rows[0]["split"]),
            tuple(rows),
            str(predictions),
            str(root),
            entries.get(incipit),
        )
        for incipit, rows in sorted(verified.items())
    ]
    for (incipit, side, rows, *_), (_, predicted, sounding) in zip(
        tasks, _map(_load, tasks, workers), strict=True
    ):
        if sounding is not None:
            truths[incipit] = sounding
        cases[side].append(
            IncipitCase(incipit_id=incipit, work=work_of(rows[0]), score=predicted, records=rows)
        )
    print(f"[exp_14] leídos {len(tasks)} incipits verificados", flush=True)
    if not cases["test"]:
        raise ValueError(f"exp_14: el corpus {corpus_path} no tiene incipits verificados de prueba")

    validator = ValidationEngine()
    dataset_hash = sha256_of_file(corpus_path)

    # 1. El modelo de train, medido en test.
    artifact = train(records, config, dataset_hash=dataset_hash)
    check_partition(artifact, records)
    content = artifact_bytes(artifact)
    artifact_sha256 = hashlib.sha256(content).hexdigest()
    model = _model(artifact, f"exp_14:{artifact_sha256[:12]}")
    measured = _measure(cases["test"], model, validator, display_policy)
    test_summary = summarize(measured)
    print(f"[exp_14] medida la partición de prueba ({len(measured)} incipits)", flush=True)

    # 4 y 5. Antes y después de aplicar las sugerencias.
    exporter = Music21ScoreExporter()
    rows_csv: list[dict[str, Any]] = []
    ser: dict[str, list[float | None]] = {variant: [] for variant in VARIANTS}
    ned: dict[str, list[float | None]] = {variant: [] for variant in VARIANTS}
    applied_totals = {policy: {"applied": 0, "skipped": 0} for policy in POLICIES}
    ned_failures: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="exp_14_") as scratch:
        workdir = Path(scratch)
        # Los pares de OMR-NED de cada incipit: una variante igual a otra no se recalcula
        # (sin sugerencias aplicadas, «HOMR con sugerencias» es HOMR).
        pairs: list[tuple[str, str]] = []
        pair_of: list[dict[str, int]] = []
        for number, (case, measurement) in enumerate(zip(cases["test"], measured, strict=True)):
            truth = truths[case.incipit_id]
            variants: dict[str, ScoreIR] = {"homr": case.score}
            row: dict[str, Any] = {
                "id": case.incipit_id,
                "work": case.work,
                "rule_findings": measurement.counts["rule_findings"],
                "learned_findings": measurement.counts["learned_findings"],
                "learned_correct": measurement.counts["learned_correct"],
            }
            for policy in POLICIES:
                # Aplicadas en la medición, por el mismo camino (`apply_suggestions`).
                applied = measurement.applied[policy]
                variants[f"homr_with_{policy}"] = measurement.fixed[policy]
                applied_totals[policy]["applied"] += applied["suggestions"]
                applied_totals[policy]["skipped"] += measurement.skipped[policy]
                row[f"{policy}_selected"] = measurement.selected[policy]["suggestions"]
                row[f"{policy}_applied"] = applied["suggestions"]
                row[f"{policy}_damaged_events"] = applied["damaged_correct_events"]
                row[f"{policy}_damaged_attributes"] = applied["damaged_correct_attributes"]
            for variant, score in variants.items():
                value = score_ser_pair(truth, score, apply_key_signature=False).ser
                ser[variant].append(value)
                row[f"ser_{variant}"] = round(value, 4)
            if with_omr_ned:
                truth_file = _export(truth, workdir / f"{number}_truth.musicxml", exporter)
                index: dict[str, int] = {}
                distinct: list[tuple[ScoreIR, int]] = []
                for variant in VARIANTS:
                    score = variants[variant]
                    same = next((i for other, i in distinct if other == score), None)
                    if same is None:
                        path = _export(score, workdir / f"{number}_{variant}.musicxml", exporter)
                        pairs.append((str(path), str(truth_file)))
                        same = len(pairs) - 1
                        distinct.append((score, same))
                    index[variant] = same
                pair_of.append(index)
            rows_csv.append(row)
        if with_omr_ned:
            print(f"[exp_14] OMR-NED de {len(pairs)} pares", flush=True)
            computed = _map(_omr_ned, pairs, workers)
            for case, row, index in zip(cases["test"], rows_csv, pair_of, strict=True):
                errors = sorted({computed[i][1] for i in index.values() if computed[i][1]})
                if errors:
                    ned_failures[case.incipit_id] = "; ".join(errors)
                for variant in VARIANTS:
                    measured_ned = computed[index[variant]][0]
                    ned[variant].append(measured_ned)
                    row[f"omr_ned_{variant}"] = (
                        "" if measured_ned is None else round(measured_ned, 4)
                    )
                row["omr_ned_error"] = ned_failures.get(case.incipit_id, "")

    before_after: dict[str, Any] = {
        "incipits": len(cases["test"]),
        "truth": "la altura que suena (MEI con las alturas del .semantic), como el corpus",
        "applied": applied_totals,
        "ser": {
            **variants_report(ser),
            "definition": "score_ser_pair(verdad, variante, apply_key_signature=False)",
        },
        "omr_ned": (
            {
                **variants_report(ned),
                "failures_count": len(ned_failures),
                "failures": dict(sorted(ned_failures.items())),
                "definition": (
                    "omr_ned_pair (musicdiff) entre MusicXML exportados del ScoreIR de la "
                    "variante y de la verdad (Music21ScoreExporter); una variante idéntica a "
                    "otra del mismo incipit reutiliza su valor"
                ),
                "pairs_computed": len(pairs),
            }
            if with_omr_ned
            else None
        ),
    }

    # 1. Validación cruzada agrupada por obra dentro de train.
    folds: list[dict[str, Any]] = []
    train_records = [r for r in records if r.get("split") == "train"]
    for fold in range(FOLDS):
        relabelled = [
            {
                **r,
                "split": (
                    "test" if fold_of(work_of(r), seed=seed, folds=FOLDS) == fold else "train"
                ),
            }
            for r in train_records
        ]
        held = [
            case for case in cases["train"] if fold_of(case.work, seed=seed, folds=FOLDS) == fold
        ]
        fold_artifact = train(relabelled, config, dataset_hash=dataset_hash)
        check_partition(fold_artifact, relabelled)
        fold_summary = summarize(
            _measure(held, _model(fold_artifact, f"exp_14:cv{fold}"), validator, display_policy)
        )
        folds.append(
            {
                "fold": fold,
                "incipits": sorted(case.incipit_id for case in held),
                "works": len({case.work for case in held}),
                "families": _families(fold_artifact),
                "metrics": principal_metrics(fold_summary),
            }
        )
        print(f"[exp_14] pliegue {fold + 1}/{FOLDS}", flush=True)
    cv_mean, cv_stdev, cv_n = _cv_summary(folds)

    # 6. Curva de aprendizaje.
    train_works = sorted({case.work for case in cases["train"]})
    points: list[dict[str, Any]] = []
    for fraction in FRACTIONS:
        chosen = set(subsample_works(train_works, fraction, seed=seed))
        subset = [r for r in records if r.get("split") == "test" or work_of(r) in chosen]
        if fraction == 1.0:
            point_artifact = artifact
            point_summary = test_summary
        else:
            point_artifact = train(subset, config, dataset_hash=dataset_hash)
            check_partition(point_artifact, subset)
            point_summary = summarize(
                _measure(
                    cases["test"],
                    _model(point_artifact, f"exp_14:{fraction}"),
                    validator,
                    display_policy,
                )
            )
        points.append(
            {
                "fraction": fraction,
                "train_works": len(chosen),
                "train_incipits": len(point_artifact["training"]["train_incipits"]),
                "train_corrections": _corrections(subset),
                "train_examples": point_artifact["training"]["examples"],
                "families": _families(point_artifact),
                "metrics": principal_metrics(point_summary),
            }
        )
        print(f"[exp_14] curva de aprendizaje: {fraction:.0%}", flush=True)

    # Las métricas de #256 (`ml suggestions evaluate`), las de la promoción.
    promotion_metrics = evaluate(model, records, split="test")

    unverified = {
        side: sorted(
            incipit
            for incipit, rows in groups.items()
            if incipit not in verified and rows[0].get("split") == side
        )
        for side in ("train", "test")
    }
    missing = {
        side: sorted(set(split_payload.get(side, ())) - set(groups)) for side in ("train", "test")
    }
    summary: dict[str, Any] = {
        "experiment": "exp_14_suggestion_layer",
        "issue": 257,
        "measurement": "primera medición (A7): decide si la capa entra en el estudio (#244)",
        "simulated": False,
        "corpus": {
            side: {
                "measured_incipits": len(cases[side]),
                "measured_works": len({case.work for case in cases[side]}),
                "unverified_incipits_excluded": len(unverified[side]),
                "split_incipits_not_in_corpus": len(missing[side]),
            }
            for side in ("train", "test")
        },
        "model": {
            "artifact": ARTIFACT_NAME,
            "artifact_sha256": artifact_sha256,
            "model_type": MODEL_TYPE,
            "feature_version": FEATURE_VERSION,
            "families": _families(artifact),
            "training_examples": artifact["training"]["examples"],
            "promoted": False,
        },
        "rules_version": validator.rules_version,
        "display_policy": _policy_report(display_policy),
        "test": test_summary,
        "before_after": before_after,
        "promotion_metrics": promotion_metrics,
        "cross_validation": {
            "k": FOLDS,
            "grouped_by": "obra (registro RISM, cadenza.learning.suggestions.work_of)",
            "seed": seed,
            "scope": "partición train; cada pliegue entrena con los otros cuatro",
            "folds": folds,
            "mean": cv_mean,
            "n_folds": cv_n,
            "stdev": cv_stdev,
        },
        "learning_curve": {
            "subsampling": "obras de train al azar con la semilla, anidadas",
            "seed": seed,
            "measured_on": "partición test",
            "points": points,
        },
        "study_sessions": {
            "available": False,
            "sessions": 0,
            "acceptance_rate": None,
            "note": (
                "Todavía no hay sesiones del estudio (#253): esta medición no incluye la tasa "
                "de aceptación de las sugerencias (#258). La medición final la añadirá, "
                "descriptiva y sin generalizar."
            ),
        },
        "methodological_limitations": LIMITATIONS,
    }

    run_info = {
        **get_run_info("exp_14", seed=seed, manifest_path=manifest_path),
        "corpus_path": str(corpus_path).replace("\\", "/"),
        "corpus_sha256": dataset_hash,
        "split_path": str(split_path).replace("\\", "/"),
        "split_sha256": sha256_of_file(split_path),
        "artifact_sha256": artifact_sha256,
        "model_type": MODEL_TYPE,
        "feature_version": FEATURE_VERSION,
        "config_path": str(config_path).replace("\\", "/"),
        "config": dict(config.raw),
        "config_hash": config.config_hash,
        "homr": homr_info,
        "folds": FOLDS,
        "fractions": list(FRACTIONS),
        "omr_ned": with_omr_ned,
        "workers": workers,
        "display_policy": _policy_report(display_policy),
        "duration_seconds": round(time.monotonic() - started, 1),
    }
    summary["run_info"] = run_info

    # Todo se escribe al final, con todo medido: un fallo a medias no deja salidas.
    results.mkdir(parents=True, exist_ok=True)
    (results / ARTIFACT_NAME).write_bytes(content)
    with (results / CSV_NAME).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, restval="")
        writer.writeheader()
        writer.writerows(rows_csv)
    (results / SUMMARY_NAME).write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (results / RUN_INFO_NAME).write_text(
        json.dumps(run_info, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Primera medición de la capa de sugerencias (#257)"
    )
    parser.add_argument("--corpus", type=Path, default=None, help="correction_corpus.jsonl")
    parser.add_argument("--split", type=Path, default=None, help="correction_corpus_split.json")
    parser.add_argument("--data", type=Path, default=DATA_DIR, help="con primus/exp_12/")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=None, help="por defecto results/")
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Semilla de los pliegues y de la curva (por defecto {DEFAULT_SEED})",
    )
    parser.add_argument("--no-omr-ned", action="store_true", help="sin OMR-NED (depuración)")
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 2) - 1),
        help="procesos para leer las partituras y calcular el OMR-NED",
    )
    parser.add_argument(
        "--min-level",
        choices=("medium", "high"),
        default=None,
        help="política de qué se muestra: nivel de confianza mínimo (por defecto, cualquiera)",
    )
    parser.add_argument(
        "--families",
        default=None,
        help=(
            "política de qué se muestra: familias separadas por comas, de "
            f"{','.join(SUGGESTION_FAMILIES)} (por defecto, todas)"
        ),
    )
    args = parser.parse_args()
    try:
        display_policy = display_policy_of(args.min_level, args.families)
    except ValueError as exc:
        parser.error(str(exc))

    _worker_init()
    summary = run(
        corpus_path=args.corpus,
        split_path=args.split,
        data_dir=args.data,
        config_path=args.config,
        output_dir=args.output_dir,
        seed=args.seed,
        with_omr_ned=not args.no_omr_ned,
        workers=args.workers,
        display_policy=display_policy,
    )
    test = summary["test"]
    ranking = test["rule_suggestions"]
    measures = test["rule_blind_measures"]
    print(
        f"[exp_14] prueba: {summary['corpus']['test']['measured_incipits']} incipits; "
        f"primera sugerencia {ranking['top1']['over_true_candidate']}, tres primeras "
        f"{ranking['top3']['over_true_candidate']}"
    )
    print(
        f"[exp_14] compases: reglas {measures['rules']['global_metrics']}, reglas + capa "
        f"{measures['rules_and_layer']['global_metrics']}"
    )
    print(f"[exp_14] daño: {test['damage']}")
    print(f"[exp_14] SER: {summary['before_after']['ser']}")
    print(f"[exp_14] validación cruzada (media): {summary['cross_validation']['mean']}")


if __name__ == "__main__":
    main()
