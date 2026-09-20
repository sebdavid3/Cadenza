"""Métricas de evaluación simbólica: SER y distancia de edición normalizada."""

from __future__ import annotations

from collections.abc import Sequence


def _levenshtein(reference: Sequence[str], hypothesis: Sequence[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row, ref in enumerate(reference, start=1):
        current = [row]
        for column, hyp in enumerate(hypothesis, start=1):
            cost = 0 if ref == hyp else 1
            current.append(
                min(previous[column] + 1, current[column - 1] + 1, previous[column - 1] + cost)
            )
        previous = current
    return previous[-1]


def symbol_error_rate(reference: Sequence[str], hypothesis: Sequence[str]) -> float:
    """Fracción de símbolos incorrectos respecto a la referencia (acotada a 1.0)."""

    if not reference:
        return 0.0 if not hypothesis else 1.0
    return min(1.0, _levenshtein(reference, hypothesis) / len(reference))


def normalized_edit_distance(reference: Sequence[str], hypothesis: Sequence[str]) -> float:
    """Distancia de edición normalizada por la longitud máxima (OMR-NED simplificada)."""

    denominator = max(len(reference), len(hypothesis))
    if denominator == 0:
        return 0.0
    return _levenshtein(reference, hypothesis) / denominator
