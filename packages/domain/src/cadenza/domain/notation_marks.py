"""Marcas de notación del `ScoreIR` como tipos de valor de dominio neutrales (ADR-0031).

Tres clases de marca, según a qué se pegan:

- **De una nota:** las articulaciones (`Articulation`) y el calderón son atributos del `Event`.
- **De una posición del compás:** una dinámica (`Dynamic`) es un atributo del `Measure`, con su
  ataque en negras desde el inicio del compás; rige su pentagrama.
- **De varias notas:** una ligadura de expresión (`Slur`) se guarda como dos extremos, inicio y
  fin, en los eventos que une; un regulador (`Wedge`), como dos extremos en las posiciones de
  los compases donde empieza y acaba. Los extremos de una misma marca comparten `number`, que la
  identifica dentro de su parte y no se reutiliza (en MusicXML, `number` va de 1 a 16 y se
  reutiliza; aquí no, para que el emparejamiento no dependa del orden ni de las ediciones).

Ninguna es un evento: no cambian el `event_index` de las anclas (ADR-0002, ADR-0011).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Any


class Articulation(StrEnum):
    """Articulación de una nota; el orden de definición es el canónico."""

    STACCATO = "staccato"
    STACCATISSIMO = "staccatissimo"
    ACCENT = "accent"
    MARCATO = "marcato"
    TENUTO = "tenuto"


class SlurType(StrEnum):
    """Extremo de una ligadura de expresión."""

    START = "start"
    STOP = "stop"


class DynamicMark(StrEnum):
    """Indicación dinámica de una posición del compás."""

    PPP = "ppp"
    PP = "pp"
    P = "p"
    MP = "mp"
    MF = "mf"
    F = "f"
    FF = "ff"
    FFF = "fff"
    SF = "sf"
    SFZ = "sfz"
    FP = "fp"
    FZ = "fz"


class WedgeType(StrEnum):
    """Extremo de un regulador: su inicio dice si es de crescendo o de diminuendo."""

    CRESCENDO = "crescendo"
    DIMINUENDO = "diminuendo"
    STOP = "stop"


_ARTICULATION_ORDER: dict[Articulation, int] = {a: i for i, a in enumerate(Articulation)}
_SLUR_TYPE_ORDER: dict[SlurType, int] = {t: i for i, t in enumerate(SlurType)}
_WEDGE_TYPE_ORDER: dict[WedgeType, int] = {t: i for i, t in enumerate(WedgeType)}


def _check_number(number: int) -> None:
    if isinstance(number, bool) or number < 1:
        raise ValueError(f"number must be >= 1, got {number!r}")


def _check_offset(offset_beats: Fraction) -> None:
    if offset_beats < 0:
        raise ValueError(f"offset_beats must be >= 0, got {offset_beats}")


@dataclass(frozen=True, slots=True)
class Slur:
    """Extremo (inicio o fin) de una ligadura de expresión en un evento."""

    type: SlurType
    number: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", SlurType(self.type))
        _check_number(self.number)

    def to_primitive(self) -> dict[str, Any]:
        return {"type": self.type.value, "number": self.number}

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> Slur:
        return cls(type=SlurType(str(data["type"])), number=int(data["number"]))


@dataclass(frozen=True, slots=True)
class Dynamic:
    """Dinámica en una posición del compás, en negras desde su inicio."""

    mark: DynamicMark
    offset_beats: Fraction

    def __post_init__(self) -> None:
        object.__setattr__(self, "mark", DynamicMark(self.mark))
        _check_offset(self.offset_beats)

    def to_primitive(self) -> dict[str, Any]:
        return {"mark": self.mark.value, "offset_beats": str(self.offset_beats)}

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> Dynamic:
        return cls(
            mark=DynamicMark(str(data["mark"])),
            offset_beats=Fraction(str(data["offset_beats"])),
        )


@dataclass(frozen=True, slots=True)
class Wedge:
    """Extremo de un regulador en una posición del compás, en negras desde su inicio."""

    type: WedgeType
    number: int
    offset_beats: Fraction

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", WedgeType(self.type))
        _check_number(self.number)
        _check_offset(self.offset_beats)

    def to_primitive(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "number": self.number,
            "offset_beats": str(self.offset_beats),
        }

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> Wedge:
        return cls(
            type=WedgeType(str(data["type"])),
            number=int(data["number"]),
            offset_beats=Fraction(str(data["offset_beats"])),
        )


def normalize_articulations(values: Iterable[Articulation | str]) -> tuple[Articulation, ...]:
    """Conjunto de articulaciones en orden canónico, sin repetir."""

    return tuple(sorted({Articulation(v) for v in values}, key=_ARTICULATION_ORDER.__getitem__))


def normalize_slurs(values: Iterable[Slur]) -> tuple[Slur, ...]:
    """Extremos de ligadura sin repetir, ordenados por número y tipo."""

    return tuple(sorted(set(values), key=lambda slur: (slur.number, _SLUR_TYPE_ORDER[slur.type])))


def sort_dynamics(values: Iterable[Dynamic]) -> tuple[Dynamic, ...]:
    """Dinámicas por su posición; las de la misma posición, en el orden dado."""

    return tuple(sorted(values, key=lambda dynamic: dynamic.offset_beats))


def sort_wedges(values: Iterable[Wedge]) -> tuple[Wedge, ...]:
    """Extremos de regulador por su posición, número y tipo."""

    return tuple(
        sorted(
            values,
            key=lambda wedge: (wedge.offset_beats, wedge.number, _WEDGE_TYPE_ORDER[wedge.type]),
        )
    )
