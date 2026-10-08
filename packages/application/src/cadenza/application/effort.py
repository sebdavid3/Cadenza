"""Funciones de apoyo y análisis de esfuerzo de corrección (#13)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from cadenza.domain import EditEvent


@dataclass(frozen=True)
class MeasureInterventionComparison:
    """Comparación de intervenciones en un compás entre lo reportado y el log de ediciones."""

    measure: str
    reported_count: int
    logged_count: int

    @property
    def difference(self) -> int:
        """Diferencia entre lo reportado y lo registrado (positivo = más reportadas)."""
        return self.reported_count - self.logged_count

    @property
    def matches(self) -> bool:
        """Indica si lo reportado coincide exactamente con el log de ediciones."""
        return self.reported_count == self.logged_count


def compute_interventions_from_edits(
    edits: Sequence[EditEvent | dict[str, Any]],
) -> dict[str, int]:
    """Calcula las intervenciones por compás a partir del log de `edit_events`.

    Cada edición en el log incrementa el conteo del compás señalado en su ancla.
    Las claves del resultado son cadenas representando el número de compás lógico
    (1-based) para compatibilidad con JSON y el DTO de esfuerzo.
    """
    counts: dict[str, int] = {}
    for edit in edits:
        if isinstance(edit, EditEvent):
            measure_num = edit.anchor.measure
        elif isinstance(edit, dict):
            anchor = edit.get("anchor") or {}
            measure_num = anchor.get("measure", 0)
        else:
            measure_num = getattr(edit, "anchor", {}).measure
        key = str(measure_num)
        counts[key] = counts.get(key, 0) + 1
    return counts


def contrast_interventions(
    reported: dict[str, int],
    edits: Sequence[EditEvent | dict[str, Any]],
) -> tuple[MeasureInterventionComparison, ...]:
    """Contrasta las intervenciones por compás reportadas frente al log de `edit_events`.

    Permite auditar si el cliente reportó fielmente las intervenciones
    observadas en el log append-only de la sesión.
    """
    logged = compute_interventions_from_edits(edits)
    all_measures = sorted(
        set(reported.keys()) | set(logged.keys()),
        key=lambda m: (0, int(m)) if m.isdigit() else (1, str(m)),
    )

    comparisons: list[MeasureInterventionComparison] = []
    for measure in all_measures:
        comparisons.append(
            MeasureInterventionComparison(
                measure=measure,
                reported_count=reported.get(measure, 0),
                logged_count=logged.get(measure, 0),
            )
        )
    return tuple(comparisons)
