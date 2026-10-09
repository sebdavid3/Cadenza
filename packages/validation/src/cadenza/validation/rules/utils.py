"""Utilidades compartidas para las reglas de validación (M2)."""

from __future__ import annotations

from cadenza.domain import Anchor, AnchorIndex, Clef


def build_event_anchor_map(
    anchors: AnchorIndex,
) -> dict[tuple[int, int, int, int, int], Anchor]:
    """Mapea ``(part, staff, measure, voice, event_index) -> Anchor`` canónica."""
    result: dict[tuple[int, int, int, int, int], Anchor] = {}
    for anchor in anchors.anchors():
        result[(anchor.part, anchor.staff, anchor.measure, anchor.voice, anchor.event_index)] = (
            anchor
        )
    return result


def find_measure_first_anchor(
    anchors: AnchorIndex,
    part: int,
    staff: int,
    measure: int,
) -> Anchor | None:
    """Devuelve la primera ancla del compás en el pentagrama especificado."""
    for anchor in anchors.anchors():
        if anchor.part == part and anchor.staff == staff and anchor.measure == measure:
            return anchor
    return None


def clef_display_name(clef: Clef) -> str:
    """Descripción legible de una clave musical."""
    sign = clef.sign.upper()
    line = clef.line
    octave = clef.octave_change
    suffix = ""
    if octave == 1:
        suffix = " (8ª alta)"
    elif octave == -1:
        suffix = " (8ª baja)"

    if sign == "G" and line == 2:
        return f"Sol en 2ª línea{suffix}"
    if sign == "F" and line == 4:
        return f"Fa en 4ª línea{suffix}"
    if sign == "C" and line == 3:
        return f"Do en 3ª línea (alto){suffix}"
    if sign == "C" and line == 4:
        return f"Do en 4ª línea (tenor){suffix}"
    return f"clave {sign} en línea {line}{suffix}"
