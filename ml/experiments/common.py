"""Utilidades comunes y trazabilidad de ejecuciones experimentales (Fase 7, Issue #24).

Proporciona:
- `get_run_info`: captura metadatos deterministas (semilla, commit, entorno, hash del manifiesto).
- `write_run_info`: persiste `run_info.json` en `results/`.
- `build_real_training_pool`: construye el pool de `TrainingSample`s a partir del diff
  HOMR↔Ground Truth y los hallazgos reales del validador sobre PrIMuS.
- `sample_size_justification`: justificación muestral con los recuentos de cada ejecución.
- Limitaciones metodológicas comunes, sin cifras de ninguna ejecución concreta (#139).
- `rules_catalog_info` y `guard_rules_catalog`: la versión de las reglas de cada medición y
  la guarda que impide sobrescribir la de otra versión del catálogo (ADR-0040 §3, §15.6).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cadenza.domain import (
    Provenance,
    ScoreDocument,
    build_anchor_index,
)
from cadenza.interchange import read_score
from cadenza.learning import (
    DatasetBuilder,
    TrainingSample,
    derive_edit_events,
)
from cadenza.validation import RULES_CATALOG_VERSION, ValidationEngine

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RESULTS_DIR = REPO_ROOT / "results"
DEFAULT_SEED = 20260920

Z_95 = 1.96

# Limitaciones metodológicas documentadas (Issue #24, Criterio 6). Sin cifras: los
# recuentos de cada ejecución van en su propio resultado (CLAUDE.md §8.1, #139).
METHODOLOGICAL_LIMITATIONS: dict[str, str] = {
    "monophonic_printed": (
        "El corpus PrIMuS está compuesto por incipits impresos monofónicos (un pentagrama, "
        "música clásica de los fondos RISM codificada con Verovio). Los resultados no se "
        "extrapolan directamente a polifonía densa de varios pentagramas "
        "(piano/partitura general) ni a manuscritos históricos."
    ),
    "validator_syntactic_blindness": (
        "El catálogo de validación opera sobre restricciones universales de teoría musical "
        "(balance rítmico de compás, tesitura por clave, armadura y alteraciones, ligaduras, "
        "colisiones de voz). Errores de transcripción OMR que sustituyen una nota correcta "
        "por otra altura válida dentro de la escala y el compás son sintácticamente impecables, "
        "por lo que ningún validador formal de reglas puede detectarlos sin acceso a la "
        "imagen original. Esto fundamenta la necesidad del bucle HITL y el aprendizaje activo."
    ),
    "segmentation_failures": (
        "Cuando HOMR no encuentra pentagramas en una imagen ('Exception: No staffs found'), "
        "se informan por separado la métrica sobre los éxitos y la métrica penalizada, que "
        "imputa a cada fallo la distancia máxima; el número de fallos de cada ejecución "
        "figura en su resultado."
    ),
}


SE_ASSUMPTIONS = (
    "Errores estándar de Wald bajo independencia de las observaciones. Los compases y las "
    "ediciones están anidados en partituras, así que el error real puede ser mayor; con una "
    "proporción observada de cero o uno el SE de Wald es nulo y no es informativo."
)


def _proportion_estimate(cases: int, n: int) -> dict[str, Any] | None:
    """Proporción observada y su error estándar binomial, SE = sqrt(p̂(1 - p̂) / N)."""
    if n <= 0:
        return None
    proportion = cases / n
    se = math.sqrt(proportion * (1.0 - proportion) / n)
    return {
        "cases": cases,
        "n": n,
        "proportion": round(proportion, 4),
        "standard_error": round(se, 4),
        "margin_95": round(Z_95 * se, 4),
    }


def sample_size_justification(
    corpus: str,
    counts: Mapping[str, int],
    proportions: Mapping[str, tuple[int, int]] | None = None,
    worst_case: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Justificación del tamaño de muestra con los recuentos de esta ejecución (#24, #139).

    `counts` son los N medidos; `proportions` asocia a cada proporción observada su par
    (casos, N), y `worst_case` a cada población su N, para el error estándar de peor caso
    de cualquier proporción estimada sobre ella, 0.5 / sqrt(N). Todo se deriva de los
    recuentos recibidos: nada se escribe a mano (CLAUDE.md §8.1). Son errores estándar de
    Wald bajo independencia; `SE_ASSUMPTIONS` explica sus límites en la propia salida.
    """
    estimates: dict[str, Any] = {}
    statements: list[str] = []
    for name, (cases, n) in (proportions or {}).items():
        estimates[name] = _proportion_estimate(cases, n)
        if n > 0:
            p = cases / n
            se = math.sqrt(p * (1.0 - p) / n)
            statements.append(
                f"{name}: p̂ = {cases}/{n} = {p:.4f} con N = {n}, "
                f"SE = sqrt(p̂(1 - p̂)/N) ≈ {se:.4f} (±{Z_95 * se * 100:.2f} % al 95 %)."
            )
    for name, n in (worst_case or {}).items():
        if n <= 0:
            estimates[name] = None
            continue
        se = 0.5 / math.sqrt(n)
        estimates[name] = {
            "n": n,
            "worst_case_standard_error": round(se, 4),
            "margin_95": round(Z_95 * se, 4),
        }
        statements.append(
            f"{name}: con N = {n}, el error estándar de cualquier proporción es como mucho "
            f"0.5/sqrt(N) ≈ {se:.4f} (±{Z_95 * se * 100:.2f} % al 95 %)."
        )
    return {
        "corpus": corpus,
        **counts,
        "standard_errors": estimates,
        "statistical_power": (
            " ".join(statements)
            if statements
            else "Sin observaciones: no se puede estimar ningún error estándar."
        ),
        "assumptions": SE_ASSUMPTIONS,
    }


def sha256_of_file(path: Path) -> str:
    """Calcula el digest SHA-256 de un archivo en disco."""
    if not path.is_file():
        return ""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_git_commit() -> str:
    """Obtiene el hash del commit actual de forma tolerante a fallos."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        pass
    return os.environ.get("GIT_COMMIT", "unknown")


def get_git_branch() -> str:
    """Obtiene el nombre de la rama git actual."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        pass
    return os.environ.get("GIT_BRANCH", "unknown")


def rules_catalog_info(validator: ValidationEngine) -> dict[str, Any]:
    """La versión de las reglas con que se mide: la lista de identificadores (`rules_version`)
    y la versión del catálogo (`RULES_CATALOG_VERSION`), que cambia aunque los identificadores
    no cambien (ADR-0040 §3). Cada cifra de `exp_06` y `exp_14` lleva las dos."""
    return {
        "rules_version": validator.rules_version,
        "rules_catalog_version": RULES_CATALOG_VERSION,
    }


def guard_rules_catalog(summary_path: Path, catalog_version: int = RULES_CATALOG_VERSION) -> None:
    """No sobrescribe una medición de otra versión del catálogo de reglas (ADR-0040 §15.6).

    Las mediciones con el catálogo nuevo se documentan junto a las anteriores, así que no las
    reemplazan: si en la salida ya hay un resumen de otra versión (sin `rules_catalog_version`,
    la 1, anterior a #246), el experimento falla antes de medir y pide otro `--output-dir`.
    """
    if not summary_path.is_file():
        return
    try:
        previous = json.loads(summary_path.read_text(encoding="utf-8")).get(
            "rules_catalog_version", 1
        )
    except (OSError, ValueError, AttributeError):
        previous = None
    if previous != catalog_version:
        raise ValueError(
            f"{summary_path} es una medición del catálogo de reglas {previous} y esta es del "
            f"{catalog_version}: indica otro --output-dir para no sobrescribirla (ADR-0040 §15.6)"
        )


def get_run_info(
    experiment_name: str,
    seed: int = DEFAULT_SEED,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Genera el diccionario canónico de información de ejecución (run_info)."""
    manifest_info: dict[str, Any] = {}
    if manifest_path is not None and manifest_path.is_file():
        try:
            rel_path = str(manifest_path.relative_to(REPO_ROOT)).replace("\\", "/")
        except ValueError:
            rel_path = str(manifest_path).replace("\\", "/")
        manifest_info = {
            "manifest_path": rel_path,
            "manifest_sha256": sha256_of_file(manifest_path),
        }

    return {
        "experiment": experiment_name,
        "seed": seed,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "git_commit": get_git_commit(),
        "git_branch": get_git_branch(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        **manifest_info,
    }


def write_run_info(
    experiment_name: str,
    seed: int = DEFAULT_SEED,
    manifest_path: Path | None = None,
    output_filename: str | None = None,
) -> dict[str, Any]:
    """Genera y escribe `run_info.json` en `results/`."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    info = get_run_info(experiment_name, seed=seed, manifest_path=manifest_path)
    filename = output_filename or f"{experiment_name}_run_info.json"
    target = RESULTS_DIR / filename
    target.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    return info


def build_real_training_pool(
    manifest_path: Path,
    predictions_dir: Path | None = None,
    limit: int | None = None,
) -> tuple[TrainingSample, ...]:
    """Construye el pool de entrenamiento a partir de predicciones y Ground Truth reales de PrIMuS.

    Para cada par disponible:
    1. Lee `score_pred` y `score_gt`.
    2. Construye el `ScoreDocument` de predicción y corre `ValidationEngine.validate`.
    3. Deriva la secuencia de `EditEvent`s deterministas mediante `derive_edit_events`.
    4. Invoca `DatasetBuilder.build` con estado `finalized` e `image_sha256` real.
    """
    if not manifest_path.is_file():
        return ()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    corpus_name = str(manifest.get("corpus", "corpus"))

    if predictions_dir is None:
        predictions_dir = root / corpus_name / "predictions"

    entries = list(manifest.get("entries", []))
    if limit is not None:
        entries = entries[:limit]

    validator = ValidationEngine()
    builder = DatasetBuilder()
    all_samples: list[TrainingSample] = []

    for entry in entries:
        eid = entry["id"]
        pred_file = predictions_dir / f"{eid}.musicxml"
        gt_file = root / entry["ground_truth"]

        if not pred_file.is_file() or not gt_file.is_file():
            continue

        try:
            score_pred = read_score(pred_file)
            score_gt = read_score(gt_file)
        except Exception:
            continue

        anchors = build_anchor_index(score_pred)
        document = ScoreDocument(
            id=eid,
            score=score_pred,
            anchors=anchors,
            provenance=Provenance(
                omr_engine="homr",
                rules_version=validator.rules_version,
                source_image_hash=entry.get("image_sha256"),
            ),
        )
        findings = validator.validate(document)
        edits = derive_edit_events(score_pred, score_gt, document_id=eid)

        samples = builder.build(
            document=document,
            edits=edits,
            findings=findings,
            status="finalized",
            image_sha256=entry.get("image_sha256"),
        )
        all_samples.extend(samples)

    return tuple(all_samples)
