"""Utilidades comunes y trazabilidad de ejecuciones experimentales (Fase 7, Issue #24).

Proporciona:
- `get_run_info`: captura metadatos deterministas (semilla, commit, entorno, hash del manifiesto).
- `write_run_info`: persiste `run_info.json` en `results/`.
- `build_real_training_pool`: construye el pool de `TrainingSample`s a partir del diff
  HOMR↔Ground Truth y los hallazgos reales del validador sobre PrIMuS.
- Constantes de justificación estadística y limitaciones metodológicas.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
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
from cadenza.validation import ValidationEngine

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RESULTS_DIR = REPO_ROOT / "results"
DEFAULT_SEED = 20260920

# Justificación del tamaño de muestra (Issue #24, Criterio 4)
SAMPLE_SIZE_JUSTIFICATION: dict[str, Any] = {
    "corpus": "primus",
    "subset": "package_aa (primeros 100 incipits estratificados)",
    "incipits_count": 100,
    "successful_transcriptions": 91,
    "failed_transcriptions": 9,
    "total_measures": 359,
    "measures_with_errors": 201,
    "derived_edits_count": 544,
    "statistical_power": (
        "Con N=359 compases observados y N=544 ediciones reales, el error estándar del "
        "estimador de proporciones para una tasa esperada p ≈ 0.40 es "
        "SE = sqrt(0.40 * 0.60 / 359) ≈ 0.0258 (margen de error de ±5.07% con 95% de confianza). "
        "Para el lote de 544 ediciones de entrenamiento, el error estándar es "
        "SE ≈ sqrt(0.50 * 0.50 / 544) ≈ 0.0214 (±4.20% al 95% de confianza). "
        "Esta muestra aporta suficiente potencia estadística para validar hipótesis "
        "de reducción de esfuerzo y comparaciones de aprendizaje activo "
        "sin sobrecargar el tiempo de cómputo."
    ),
    "scaling_note": (
        "El corpus completo descargado cuenta con 43,594 incipits en package_aa y "
        "19,899 en package_ab. El job offline 'python -m ml build-dataset' implementado "
        "en el Issue #22 permite procesar lotes adicionales a gran escala según "
        "la disponibilidad de recursos de cómputo."
    ),
}

# Limitaciones metodológicas documentadas (Issue #24, Criterio 6)
METHODOLOGICAL_LIMITATIONS: dict[str, str] = {
    "monophonic_printed": (
        "El corpus PrIMuS está compuesto por incipits impresos monofónicos (1 pentagrama, "
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
        "9 de los 100 incipits de HOMR fallaron en la etapa de segmentación de pentagramas "
        "('Exception: No staffs found'). Se reportan explícitamente tanto la métrica sobre "
        "éxitos (91) como la métrica penalizada que incluye los fallos imputando OMR-NED=1.0."
    ),
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
