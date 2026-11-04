"""Experimento 2: comparación de estrategias de aprendizaje activo sobre correcciones reales.

Fase 7, Issue #24, D18, D21.
Evalúa las estrategias de adquisición de Cadenza sobre el pool de muestras `TrainingSample`
derivadas de errores reales de HOMR frente al Ground Truth de PrIMuS:

Estrategias evaluadas:
1. `UncertaintyAcquisition` (priorización por densidad de errores del validador neuro-simbólico)
2. `DiversityAcquisition` (cobertura voraz furthest-point en espacio de features)
3. `HybridAcquisition` (apuesta principal: trade-off entre densidad de error y diversidad)
4. `RandomAcquisition` (control experimental pasivo con semilla fija)

Criterio de comparación definido de antemano (a priori):
- **1. Densidad media de error (`mean_error_density`):** capacidad de capturar fallos.
- **2. Magnitud de corrección acumulada (`total_correction_magnitude`):** impacto de cambio.
- **3. Dispersión media entre pares (`mean_pairwise_spread`):** no-redundancia en features.
- **4. Cobertura de operaciones (`op_coverage_ratio`, `op_entropy`):** variedad y balance.
- **5. Similitud de Jaccard (`jaccard_overlap`):** independencia entre selecciones.

Salidas:
- `results/al_strategies_comparison.csv`
- `results/al_strategies_summary.json`
- `results/exp_02_run_info.json`
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cadenza.domain import CONTENT_EDIT_OPS
from cadenza.learning import (
    AcquisitionStrategy,
    DiversityAcquisition,
    HybridAcquisition,
    RandomAcquisition,
    TrainingSample,
    UncertaintyAcquisition,
    dataset_hash,
    feature_distance,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.experiments.common import (  # noqa: E402
    DEFAULT_SEED,
    METHODOLOGICAL_LIMITATIONS,
    RESULTS_DIR,
    build_real_training_pool,
    sample_size_justification,
    write_run_info,
)

DATA_DIR = REPO_ROOT / "data"
EVALUATION_BUDGETS = (10, 20, 50)
CANONICAL_BUDGET = 20

# Criterio formal de comparación definido a priori (Issue #24, Criterio 2)
PRIOR_COMPARISON_CRITERIA: dict[str, str] = {
    "1_mean_error_density": (
        "Densidad de error promedio de las muestras seleccionadas. Mide la eficacia de la "
        "estrategia para priorizar regiones donde el validador neuro-simbólico detectó fallos."
    ),
    "2_correction_impact": (
        "Magnitud total y media de corrección capturada (semitonos modificados, "
        "beats rectificados). Mide el volumen de discrepancia con el ground truth "
        "absorbido dentro del presupuesto."
    ),
    "3_pairwise_spread": (
        "Distancia euclídea promedio entre pares de vectores de características seleccionados. "
        "Mide la no-redundancia y cobertura del espacio de estados musicales."
    ),
    "4_operation_coverage_and_entropy": (
        "Número de tipos de operaciones EditOp presentes (de 7 posibles) y entropía de "
        "Shannon H(op). Mide el balance multivariable del lote para evitar sobreajuste "
        "a una sola corrección (p. ej. solo notas)."
    ),
    "5_jaccard_dissimilarity": (
        "Índice de Jaccard J(A, B) = |A inter B| / |A union B| entre conjuntos seleccionados. "
        "Verifica que la estrategia híbrida no degenere trivialmente en incertidumbre pura "
        "ni diversidad pura."
    ),
}


def _pairwise_spread(samples: Sequence[TrainingSample]) -> float:
    """Calcula la distancia euclídea media entre todos los pares del lote."""
    if len(samples) < 2:
        return 0.0
    distances: list[float] = []
    for i, s1 in enumerate(samples):
        for s2 in samples[i + 1 :]:
            distances.append(feature_distance(s1, s2))
    return float(sum(distances) / len(distances)) if distances else 0.0


def _operation_metrics(samples: Sequence[TrainingSample]) -> tuple[dict[str, int], float]:
    """Calcula la distribución de operaciones y la entropía de Shannon."""
    if not samples:
        return {}, 0.0
    counts: dict[str, int] = {}
    for s in samples:
        counts[s.op.value] = counts.get(s.op.value, 0) + 1
    total = len(samples)
    entropy = 0.0
    for c in counts.values():
        p = c / total
        if p > 0.0:
            entropy -= p * math.log2(p)
    return counts, round(entropy, 4)


def _jaccard_similarity(
    samples_a: Sequence[TrainingSample],
    samples_b: Sequence[TrainingSample],
) -> float:
    """Calcula la similitud de Jaccard entre dos selecciones de lote."""
    set_a = {s.key() for s in samples_a}
    set_b = {s.key() for s in samples_b}
    union = set_a | set_b
    if not union:
        return 1.0
    return round(len(set_a & set_b) / len(union), 4)


@dataclass(frozen=True, slots=True)
class StrategyBatchEvaluation:
    strategy_id: str
    budget: int
    count: int
    mean_error_density: float
    mean_correction_magnitude: float
    total_correction_magnitude: float
    mean_pairwise_spread: float
    op_counts: dict[str, int]
    op_coverage_ratio: float
    op_entropy: float
    batch_dataset_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy_id,
            "budget": self.budget,
            "count": self.count,
            "mean_error_density": round(self.mean_error_density, 4),
            "mean_correction_magnitude": round(self.mean_correction_magnitude, 4),
            "total_correction_magnitude": round(self.total_correction_magnitude, 4),
            "mean_pairwise_spread": round(self.mean_pairwise_spread, 4),
            "op_counts": self.op_counts,
            "op_coverage_ratio": round(self.op_coverage_ratio, 4),
            "op_entropy": round(self.op_entropy, 4),
            "batch_dataset_hash": self.batch_dataset_hash,
        }


def evaluate_strategy(
    strategy: AcquisitionStrategy,
    pool: Sequence[TrainingSample],
    budget: int,
) -> tuple[list[TrainingSample], StrategyBatchEvaluation]:
    """Evalúa una estrategia para un presupuesto dado según los criterios a priori."""
    selected = strategy.select(pool, budget)
    n = len(selected)
    if n == 0:
        return [], StrategyBatchEvaluation(
            strategy_id=strategy.strategy_id,
            budget=budget,
            count=0,
            mean_error_density=0.0,
            mean_correction_magnitude=0.0,
            total_correction_magnitude=0.0,
            mean_pairwise_spread=0.0,
            op_counts={},
            op_coverage_ratio=0.0,
            op_entropy=0.0,
            batch_dataset_hash=dataset_hash(selected),
        )

    mean_err = sum(s.error_density for s in selected) / n
    total_mag = sum(s.correction_magnitude for s in selected)
    mean_mag = total_mag / n
    spread = _pairwise_spread(selected)
    op_counts, entropy = _operation_metrics(selected)
    # Las siete operaciones de contenido: las de marcas no entran en el dataset (ADR-0039).
    coverage = len(op_counts) / len(CONTENT_EDIT_OPS)

    eval_result = StrategyBatchEvaluation(
        strategy_id=strategy.strategy_id,
        budget=budget,
        count=n,
        mean_error_density=mean_err,
        mean_correction_magnitude=mean_mag,
        total_correction_magnitude=total_mag,
        mean_pairwise_spread=spread,
        op_counts=op_counts,
        op_coverage_ratio=coverage,
        op_entropy=entropy,
        batch_dataset_hash=dataset_hash(selected),
    )
    return selected, eval_result


def _measured_interpretation(
    canonical_evals: dict[str, dict[str, Any]],
    jaccard_matrix: dict[str, dict[str, float]],
    *,
    pool_size: int,
) -> str:
    """Resume los criterios a priori con los valores medidos en esta ejecución."""

    def best(metric: str) -> str:
        top = max(e[metric] for e in canonical_evals.values())
        tied = [s for s, e in canonical_evals.items() if e[metric] == top]
        return f"{', '.join(repr(s) for s in tied)} ({top:.3f})"

    hybrid = jaccard_matrix.get("hybrid", {})
    caveat = (
        f" El pool no supera el presupuesto: todas las estrategias seleccionan las "
        f"{pool_size} muestras y empatan, así que la comparación no discrimina."
        if pool_size <= CANONICAL_BUDGET
        else ""
    )
    return (
        f"Presupuesto B={CANONICAL_BUDGET} sobre {pool_size} muestras.{caveat} "
        f"Mayor densidad media de error: {best('mean_error_density')}. "
        f"Mayor magnitud de corrección total: {best('total_correction_magnitude')}. "
        f"Mayor dispersión media entre pares: {best('mean_pairwise_spread')}. "
        f"Mayor entropía de operaciones: {best('op_entropy')}. "
        f"Jaccard híbrida-incertidumbre: {hybrid.get('uncertainty', 0.0):.3f}; "
        f"híbrida-diversidad: {hybrid.get('diversity', 0.0):.3f}."
    )


def run(
    manifest_path: Path | None = None,
    predictions_dir: Path | None = None,
    limit: int | None = None,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Punto de entrada de exp_02: solo datos reales, sin valores de reserva (CLAUDE.md §8.1)."""
    manifest = manifest_path or (DATA_DIR / "manifest.json")
    if not manifest.is_file():
        raise FileNotFoundError(
            f"exp_02 requiere el corpus PrIMuS descargado y su manifiesto ({manifest}). "
            "Genéralo con `ml/experiments/corpus.py fetch` y `manifest` (ver ml/README.md)."
        )
    pool = build_real_training_pool(manifest, predictions_dir=predictions_dir, limit=limit)
    if not pool:
        raise ValueError(
            f"exp_02 no obtuvo ninguna muestra real a partir de {manifest}: faltan las "
            "predicciones de HOMR (`exp_04`) o ningún par predicción-verdad es legible."
        )
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    corpus_name = str(manifest_data.get("corpus", "corpus"))
    entries = list(manifest_data.get("entries", []))
    summary = _evaluate_pool(pool, seed=seed, manifest_path=manifest)
    return {
        "experiment": "exp_02_active_learning",
        "mode": f"real_data_{corpus_name}",
        "simulated": False,
        **summary,
        "sample_size_justification": sample_size_justification(
            corpus_name,
            counts={
                "entries_considered": len(entries if limit is None else entries[:limit]),
                "scores_with_edits": len({sample.document_id for sample in pool}),
                "derived_edits_count": len(pool),
            },
            worst_case={"derived_edits": len(pool)},
        ),
    }


def _evaluate_pool(
    pool: Sequence[TrainingSample],
    *,
    seed: int,
    manifest_path: Path | None,
) -> dict[str, Any]:
    """Compara las estrategias sobre un pool dado y escribe el CSV de selecciones y el run_info."""
    strategies: tuple[AcquisitionStrategy, ...] = (
        UncertaintyAcquisition(),
        DiversityAcquisition(),
        HybridAcquisition(),
        RandomAcquisition(seed=seed),
    )

    # 1. Evaluación canónica para B=20 y generación de filas para CSV
    canonical_selected: dict[str, list[TrainingSample]] = {}
    canonical_evals: dict[str, dict[str, Any]] = {}
    csv_rows: list[dict[str, Any]] = []

    for strat in strategies:
        selected, ev = evaluate_strategy(strat, pool, CANONICAL_BUDGET)
        canonical_selected[strat.strategy_id] = selected
        canonical_evals[strat.strategy_id] = ev.to_dict()

        for rank, sample in enumerate(selected, start=1):
            csv_rows.append(
                {
                    "strategy": strat.strategy_id,
                    "rank": rank,
                    "document_id": sample.document_id,
                    "measure": sample.anchor.measure,
                    "voice": sample.anchor.voice,
                    "op": sample.op.value,
                    "error_density": round(sample.error_density, 4),
                    "correction_magnitude": round(sample.correction_magnitude, 4),
                }
            )

    # 2. Matriz de similitud de Jaccard entre estrategias para B=20
    jaccard_matrix: dict[str, dict[str, float]] = {}
    strat_ids = [s.strategy_id for s in strategies]
    for s1 in strat_ids:
        jaccard_matrix[s1] = {}
        for s2 in strat_ids:
            jaccard_matrix[s1][s2] = _jaccard_similarity(
                canonical_selected[s1], canonical_selected[s2]
            )

    # 3. Evaluación paramétrica para presupuestos B in (10, 20, 50)
    budget_comparison: dict[str, list[dict[str, Any]]] = {}
    for b in EVALUATION_BUDGETS:
        budget_comparison[f"budget_{b}"] = []
        for strat in strategies:
            _, ev = evaluate_strategy(strat, pool, b)
            budget_comparison[f"budget_{b}"].append(ev.to_dict())

    # 4. Escritura de CSV
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "al_strategies_comparison.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "strategy",
            "rank",
            "document_id",
            "measure",
            "voice",
            "op",
            "error_density",
            "correction_magnitude",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)

    run_info = write_run_info("exp_02", seed=seed, manifest_path=manifest_path)

    summary_payload: dict[str, Any] = {
        "seed": seed,
        "pool_size": len(pool),
        "prior_comparison_criteria": PRIOR_COMPARISON_CRITERIA,
        "canonical_budget": CANONICAL_BUDGET,
        "canonical_evaluations": canonical_evals,
        "jaccard_similarity_matrix": jaccard_matrix,
        "parametric_evaluations_by_budget": budget_comparison,
        "scientific_interpretation": _measured_interpretation(
            canonical_evals, jaccard_matrix, pool_size=len(pool)
        ),
        "methodological_limitations": METHODOLOGICAL_LIMITATIONS,
        "run_info": run_info,
        "csv_output": str(csv_path),
    }

    return summary_payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Experimento 2: Comparación de AL sobre datos reales"
    )
    parser.add_argument("--manifest", type=Path, default=DATA_DIR / "manifest.json")
    parser.add_argument("--predictions", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    result = run(
        manifest_path=args.manifest,
        predictions_dir=args.predictions,
        limit=args.limit,
        seed=args.seed,
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = RESULTS_DIR / "al_strategies_summary.json"
    out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    mode_s = result["mode"]
    pool_s = result["pool_size"]
    bud_s = result["canonical_budget"]
    print(f"[exp_02] Modo={mode_s} Pool={pool_s} Presupuesto={bud_s}")
    for strat_id, metrics in result["canonical_evaluations"].items():
        print(
            f"[exp_02] {strat_id:12s} "
            f"Error={metrics['mean_error_density']:.3f} "
            f"Magnitud={metrics['mean_correction_magnitude']:.3f} "
            f"Spread={metrics['mean_pairwise_spread']:.3f} "
            f"Entropía={metrics['op_entropy']:.3f}"
        )
    print(f"[exp_02] Escrito: {out_file}")


if __name__ == "__main__":
    main()
