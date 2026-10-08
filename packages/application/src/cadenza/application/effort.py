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
    *,
    active_only: bool = False,
) -> dict[str, int]:
    """Calcula las intervenciones por compás a partir del log de `edit_events`.

    Cada edición en el log incrementa el conteo del compás señalado en su ancla.
    Las claves del resultado son cadenas representando el número de compás lógico
    (1-based) para compatibilidad con JSON y el DTO de esfuerzo.

    Si `active_only=True`, discrimina correcciones activas descartando
    eventos compensatorios y ediciones revertidas (#35).
    """
    reverted_ids: set[str] = set()
    if active_only:
        for e in edits:
            reverts_id = (
                e.reverts_edit_id
                if isinstance(e, EditEvent)
                else (e.get("reverts_edit_id") if isinstance(e, dict) else None)
            )
            if reverts_id:
                reverted_ids.add(str(reverts_id))

    counts: dict[str, int] = {}
    for edit in edits:
        if isinstance(edit, EditEvent):
            if active_only and (edit.is_reversion or edit.id in reverted_ids):
                continue
            measure_num = edit.anchor.measure
        elif isinstance(edit, dict):
            edit_id = str(edit.get("id", ""))
            is_rev = bool(edit.get("reverts_edit_id"))
            if active_only and (is_rev or edit_id in reverted_ids):
                continue
            anchor = edit.get("anchor") or {}
            measure_num = anchor.get("measure", 0)
        else:
            if active_only and (
                getattr(edit, "is_reversion", False) or getattr(edit, "id", "") in reverted_ids
            ):
                continue
            measure_num = getattr(edit, "anchor", {}).measure
        key = str(measure_num)
        counts[key] = counts.get(key, 0) + 1
    return counts


def count_reversions_from_edits(
    edits: Sequence[EditEvent | dict[str, Any]],
) -> dict[str, int]:
    """Calcula el conteo de eventos compensatorios (reversiones/deshacer) por compás (#35)."""
    counts: dict[str, int] = {}
    for edit in edits:
        is_reversion = False
        measure_num = 0
        if isinstance(edit, EditEvent):
            is_reversion = edit.is_reversion
            measure_num = edit.anchor.measure
        elif isinstance(edit, dict):
            is_reversion = bool(edit.get("reverts_edit_id"))
            anchor = edit.get("anchor") or {}
            measure_num = anchor.get("measure", 0)
        else:
            is_reversion = getattr(edit, "is_reversion", False)
            measure_num = getattr(edit, "anchor", {}).measure
        if is_reversion:
            key = str(measure_num)
            counts[key] = counts.get(key, 0) + 1
    return counts


def contrast_interventions(
    reported: dict[str, int],
    edits: Sequence[EditEvent | dict[str, Any]],
    *,
    active_only: bool = False,
) -> tuple[MeasureInterventionComparison, ...]:
    """Contrasta las intervenciones por compás reportadas frente al log de `edit_events`.

    Permite auditar si el cliente reportó fielmente las intervenciones
    observadas en el log append-only de la sesión.
    """
    logged = compute_interventions_from_edits(edits, active_only=active_only)
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
