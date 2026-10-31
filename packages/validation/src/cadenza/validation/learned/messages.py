"""Mensajes de la capa de sugerencias en lenguaje musical (ADR-0036 §3, #245).

Los nombres de las notas y de las figuras son los del validador (`cadenza.validation.language`,
ADR-0040 §1), para que la capa y las reglas hablen igual.

Nunca una cifra sin contexto: la confianza se explica con la evidencia que la respalda
(«en 312 de 1 040 notas parecidas, la corrección fue esa»).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from cadenza.domain import EditOp, EventKind

from ..language import accidental_word, figure_name, note_name
from .features import EventView, split_pitch

if TYPE_CHECKING:
    from .model import Score

__all__ = ["describe_edit", "figure_name", "learned_message", "note_name", "ranking_note"]


def _event_name(view: EventView | None) -> str:
    if view is None:
        return "este evento"
    if view.event.kind is EventKind.REST:
        return f"este silencio de {figure_name(view.event.duration_beats)}"
    return f"este {note_name(view.event.pitch)}"


def describe_edit(op: EditOp, after: Mapping[str, Any] | None, view: EventView | None) -> str:
    """La edición propuesta, dicha como la diría un músico."""
    data = after or {}
    if op is EditOp.SET_ACCIDENTAL and view is not None:
        letter, _, octave = split_pitch(view.event.pitch)
        raw = data.get("accidental")
        accidental = split_pitch(f"C{'' if raw in (None, 'natural') else raw}4")[1]
        target = f"{letter}{accidental}{octave}"
        return f"Cambiar {note_name(view.event.pitch)} por {note_name(target)}."
    if op is EditOp.SET_PITCH:
        before = "la nota" if view is None else note_name(view.event.pitch)
        return f"Cambiar {before} por {note_name(data.get('pitch'))}."
    if op is EditOp.SET_DURATION:
        before = "la figura" if view is None else figure_name(view.event.duration_beats)
        return f"Cambiar la {before} por {figure_name(data.get('duration_beats'))}."
    if op is EditOp.DELETE_EVENT:
        return f"Borrar {_event_name(view)}."
    if op is EditOp.INSERT_EVENT:
        kind = "un silencio" if data.get("kind") == EventKind.REST.value else "una nota"
        return f"Añadir {kind} de {figure_name(data.get('duration_beats'))}."
    if op is EditOp.SET_CLEF:
        return "Cambiar la clave del compás."
    if op is EditOp.SET_KEY:
        return "Cambiar la armadura del compás."
    return "Corregir este evento."


def ranking_note(score: Score) -> str:
    """La evidencia de una confianza: cuántas veces fue esa la corrección en casos parecidos."""
    if score.support == 1:
        return f"En el único caso parecido, la corrección {'fue' if score.count else 'no fue'} esa."
    return f"En {score.count} de {score.support} casos parecidos, la corrección fue esa."


def learned_message(family: str, view: EventView, suggestion: Any) -> str:
    """Mensaje de un posible error propio de la capa (`learned.*`)."""
    after: Mapping[str, Any] = suggestion.after or {}
    if family == "accidental":
        letter, _, octave = split_pitch(view.event.pitch)
        accidental = str(after.get("accidental") or "")
        target = f"{letter}{accidental}{octave}"
        reason = ""
        if accidental == view.context.get("key_accidental"):
            reason = (
                ": la armadura lo pide"
                if accidental
                else ": la armadura no lleva alteración para esta nota"
            )
        elif accidental == view.context.get("previous_accidental_same_step"):
            reason = f": antes en el compás lleva {accidental_word(accidental)}"
        return f"Puede que este {note_name(view.event.pitch)} sea {note_name(target)}{reason}."
    if family == "duration":
        return (
            f"Puede que esta {figure_name(view.event.duration_beats)} sea "
            f"{figure_name(after.get('duration_beats'))}."
        )
    if family == "pitch":
        return f"Puede que este {note_name(view.event.pitch)} sea {note_name(after.get('pitch'))}."
    if family == "delete":
        return f"Puede que {_event_name(view)} sobre: HOMR suele leer de más en casos así."
    return "Puede que este evento esté mal leído."
