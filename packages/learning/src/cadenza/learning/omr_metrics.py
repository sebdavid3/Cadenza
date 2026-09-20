"""Métrica oficial OMR-NED (Sheet Music Benchmark) vía `musicdiff`.

Vive detrás del extra opcional ``cadenza-learning[metrics]``. El núcleo de
aprendizaje no importa `musicdiff` salvo que se invoque alguna de estas
funciones. `musicdiff` compara notación visible (no solo sonido), lo que la hace
idónea para evaluar OMR.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class MetricsExtraMissing(RuntimeError):
    """Falta el extra `metrics` (musicdiff) para calcular OMR-NED."""


@dataclass(frozen=True, slots=True)
class OmrNedResult:
    """Resultado de OMR-NED para un par predicho/ground-truth."""

    predicted: str
    ground_truth: str
    predicted_symbols: int
    ground_truth_symbols: int
    edit_distance: int
    omr_ned: float

    def to_primitive(self) -> dict[str, object]:
        return {
            "predicted": self.predicted,
            "ground_truth": self.ground_truth,
            "predicted_symbols": self.predicted_symbols,
            "ground_truth_symbols": self.ground_truth_symbols,
            "edit_distance": self.edit_distance,
            "omr_ned": self.omr_ned,
        }


def _load_musicdiff() -> Any:
    try:
        import musicdiff
    except ImportError as exc:  # pragma: no cover - depende del extra opcional
        raise MetricsExtraMissing(
            "OMR-NED requiere el extra 'metrics' de cadenza-learning. "
            "Instálalo con: uv sync (incluye cadenza-learning[metrics])."
        ) from exc
    return musicdiff


def _pair_metrics_fn(musicdiff: Any) -> Any:
    """Localiza la función de OMR-NED por par (pública o interna de 5.x)."""

    function = getattr(musicdiff, "diff_omr_ned_metrics", None)
    if function is None:
        function = getattr(musicdiff, "_diff_omr_ned_metrics", None)
    if function is None:  # pragma: no cover - depende de la versión
        raise MetricsExtraMissing(
            "musicdiff no expone una función de OMR-NED por par en esta versión."
        )
    return function


def _detail(musicdiff: Any, detail: Any | None) -> Any:
    if detail is not None:
        return detail
    return musicdiff.DetailLevel.Default


def omr_ned_pair(
    predicted: Path, ground_truth: Path, *, detail: Any | None = None
) -> OmrNedResult:
    """Calcula OMR-NED entre un archivo predicho y su ground truth."""

    musicdiff = _load_musicdiff()
    metrics = _pair_metrics_fn(musicdiff)(
        str(predicted), str(ground_truth), _detail(musicdiff, detail)
    )
    if metrics is None:
        raise ValueError(f"no se pudo interpretar el par: {predicted} / {ground_truth}")
    return OmrNedResult(
        predicted=str(predicted),
        ground_truth=str(ground_truth),
        predicted_symbols=int(metrics.pred_numsyms),
        ground_truth_symbols=int(metrics.gt_numsyms),
        edit_distance=int(metrics.omr_edit_distance),
        omr_ned=float(metrics.omr_ned),
    )


def omr_ned_batch(
    predicted_dir: Path,
    ground_truth_dir: Path,
    output_dir: Path,
    *,
    detail: Any | None = None,
) -> float:
    """Calcula el OMR-NED agregado de dos carpetas de archivos homónimos.

    Devuelve la puntuación global y escribe el desglose por categoría en
    ``output_dir/output.csv`` (formato de musicdiff).
    """

    musicdiff = _load_musicdiff()
    output_dir.mkdir(parents=True, exist_ok=True)
    overall, _csv_path = musicdiff.diff_ml_training(
        str(predicted_dir), str(ground_truth_dir), str(output_dir), _detail(musicdiff, detail)
    )
    return float(overall)
