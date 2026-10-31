"""Mensajes de la capa de sugerencias en lenguaje musical (ADR-0036 §3, #245).

Nunca una cifra sin contexto: la confianza se explica con la evidencia que la respalda
(«en 312 de 1 040 notas parecidas, la corrección fue esa»).
"""

from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Final

from cadenza.domain import EditOp, EventKind

from .features import EventView, figure_of, split_pitch

if TYPE_CHECKING:
    from .model import Score

_NOTE_NAMES: Final[dict[str, str]] = {
    "C": "Do",
    "D": "Re",
    "E": "Mi",
    "F": "Fa",
    "G": "Sol",
    "A": "La",
    "B": "Si",
}
_ACCIDENTAL_SIGNS: Final[dict[str, str]] = {"": "", "#": "♯", "##": "𝄪", "b": "♭", "bb": "𝄫"}
_ACCIDENTAL_WORDS: Final[dict[str, str]] = {
    "": "becuadro",
    "#": "sostenido",
    "##": "doble sostenido",
    "b": "bemol",
    "bb": "doble bemol",
}
_FIGURES: Final[dict[Fraction, str]] = {
    Fraction(8): "cuadrada",
    Fraction(4): "redonda",
    Fraction(2): "blanca",
    Fraction(1): "negra",
    Fraction(1, 2): "corchea",
    Fraction(1, 4): "semicorchea",
    Fraction(1, 8): "fusa",
    Fraction(1, 16): "semifusa",
    Fraction(1, 32): "garrapatea",
    Fraction(1, 64): "semigarrapatea",
}


def note_name(pitch: str | None) -> str:
    """Nombre de una altura en solfeo, con su alteración: «Si♭», «Fa♯»."""
    letter, accidental, _ = split_pitch(pitch)
    if not letter:
        return "esta nota"
    return f"{_NOTE_NAMES[letter]}{_ACCIDENTAL_SIGNS.get(accidental, accidental)}"


def figure_name(duration: object) -> str:
    """Nombre de la figura de una duración en negras: «negra», «corchea con puntillo»."""
    try:
        value = Fraction(str(duration))
    except (ValueError, ZeroDivisionError):
        return "figura"
    parsed = figure_of(value)
    if parsed is None:
        return f"figura de {value} negras"
    base, dots = parsed
    name = _FIGURES.get(base, "figura")
    if dots == 1:
        return f"{name} con puntillo"
    if dots == 2:
        return f"{name} con doble puntillo"
    return name


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
            reason = f": antes en el compás lleva {_ACCIDENTAL_WORDS.get(accidental, accidental)}"
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
