"""Funciones de apoyo y análisis de esfuerzo de corrección (#13, ADR-0050)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Final

from cadenza.domain import (
    CONTENT_EDIT_OPS,
    GAP_EDIT_OPS,
    MARK_EDIT_OPS,
    METER_EDIT_OPS,
    EditEvent,
    EditOp,
)

from .ports.effort_repository import EffortMetricsData, EffortSegment
from .ports.session_repository import PersistedSuggestion
from .suggestions import ACCEPTED, REJECTED

EFFORT_CLASSES: Final[tuple[str, ...]] = ("content", "mark", "meter")
"""Las clases de las intervenciones (ADR-0039, ADR-0044): el contenido, las marcas de notación y
el compás con los tresillos, la figura de un acorde y la ligadura de prolongación (ADR-0055)."""


def effort_class(op: EditOp) -> str:
    """La clase de una operación para las métricas de esfuerzo (protocolo §3.4, ADR-0050 §3)."""
    if op in MARK_EDIT_OPS:
        return "mark"
    if op in METER_EDIT_OPS:
        return "meter"
    # Escribir en un hueco o hacerlo visible es contenido, como insertar o borrar (ADR-0058):
    # las clases siguen siendo tres.
    if op in CONTENT_EDIT_OPS or op in GAP_EDIT_OPS:
        return "content"
    raise ValueError(f"Operación sin clase de esfuerzo: {op}")


def interventions_by_class(edits: Iterable[EditEvent]) -> dict[str, dict[str, int]]:
    """Las ediciones del log por clase y por compás de su ancla, con las tres clases siempre.

    Cuenta todas: las compensatorias de deshacer son de la misma operación que deshacen, y
    rehacer es una edición más (ADR-0034).
    """
    counts: dict[str, dict[str, int]] = {name: {} for name in EFFORT_CLASSES}
    for edit in edits:
        by_measure = counts[effort_class(edit.op)]
        key = str(edit.anchor.measure)
        by_measure[key] = by_measure.get(key, 0) + 1
    return counts


def merge_segment(
    segments: Sequence[EffortSegment], segment: EffortSegment
) -> tuple[EffortSegment, ...]:
    """Los tramos con `segment` sumado: uno nuevo va al final; uno conocido solo crece.

    Idempotente y conmutativo para el mismo tramo: una petición repetida o que llega tarde con
    un valor menor no cambia nada (ADR-0050 §2). La primera edición, una vez conocida, se queda;
    del umbral vale el último que se dijo.
    """
    merged: list[EffortSegment] = []
    found = False
    for stored in segments:
        if stored.id != segment.id:
            merged.append(stored)
            continue
        found = True
        merged.append(
            EffortSegment(
                id=stored.id,
                active_ms=max(stored.active_ms, segment.active_ms),
                first_edit_ms=(
                    stored.first_edit_ms
                    if stored.first_edit_ms is not None
                    else segment.first_edit_ms
                ),
                idle_threshold_ms=(
                    segment.idle_threshold_ms
                    if segment.idle_threshold_ms is not None
                    else stored.idle_threshold_ms
                ),
            )
        )
    if not found:
        merged.append(segment)
    return tuple(merged)


def total_active_ms(segments: Iterable[EffortSegment]) -> int:
    """La duración: la suma del tiempo de todos los tramos."""
    return sum(segment.active_ms for segment in segments)


def time_to_first_edit_ms(segments: Sequence[EffortSegment]) -> int | None:
    """El tiempo hasta la primera edición con la misma regla que la duración: el de los tramos
    anteriores al que la guardó más el de ese tramo hasta guardarla. None si ningún tramo la
    dice (no hubo ediciones, o no llegó a saberse cuándo)."""
    before = 0
    for segment in segments:
        if segment.first_edit_ms is not None:
            return before + segment.first_edit_ms
        before += segment.active_ms
    return None


def _own_responses(suggestions: Iterable[PersistedSuggestion], response: str) -> int:
    # Un rechazo heredado repite la respuesta de otra fila: no es otra acción (ADR-0036 §4).
    return sum(1 for s in suggestions if s.response == response and s.inherited_from is None)


def refreshed_effort(
    record: EffortMetricsData,
    *,
    segments: Sequence[EffortSegment],
    edits: Sequence[EditEvent],
    suggestions: Sequence[PersistedSuggestion],
    now: datetime,
) -> EffortMetricsData:
    """El registro acumulado con todo lo que se deriva vuelto a calcular (ADR-0050 §3)."""
    return replace(
        record,
        segments=tuple(segments),
        duration_ms=total_active_ms(segments),
        time_to_first_edit_ms=time_to_first_edit_ms(segments),
        interventions=compute_interventions_from_edits(edits),
        interventions_by_class=interventions_by_class(edits),
        suggestions_applied=_own_responses(suggestions, ACCEPTED),
        suggestions_rejected=_own_responses(suggestions, REJECTED),
        updated_at=now,
    )


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
