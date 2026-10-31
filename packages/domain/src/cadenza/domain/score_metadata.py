"""Título, compositor e instrumento de cada parte de una sesión (#235, ADR-0041).

Son datos de la sesión, no del `ScoreIR`: los indica la persona, no los lee el OMR, y
cambiarlos no es una edición del log (ADR-0007). La exportación los recibe aparte para
escribirlos en el MusicXML y en el MIDI.

La parte `i` de `ScoreMetadata.parts` es la parte `i` del `ScoreIR`, en el orden en que HOMR
las detecta; una parte sin entrada no tiene instrumento ni nombre.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

TITLE_MAX_LENGTH: Final[int] = 200
COMPOSER_MAX_LENGTH: Final[int] = 200
PART_NAME_MAX_LENGTH: Final[int] = 100
SOURCE_FILENAME_MAX_LENGTH: Final[int] = 255
MAX_PARTS: Final[int] = 32


class Instrument(StrEnum):
    """Lista cerrada de instrumentos de una parte (ADR-0041 §2).

    El valor es un identificador estable que viaja en la API y se guarda en la base: la lista
    solo crece. `other` admite un nombre libre (el de la parte) y suena como el piano.
    """

    PIANO = "piano"
    VOICE = "voice"
    VIOLIN = "violin"
    CELLO = "cello"
    FLUTE = "flute"
    CLARINET = "clarinet"
    GUITAR = "guitar"
    OTHER = "other"


def _clean_text(value: str | None) -> str | None:
    """Sin caracteres de control ni espacios repetidos o en los extremos; vacío es None."""
    if value is None:
        return None
    replaced = "".join(" " if unicodedata.category(ch) == "Cc" else ch for ch in value)
    cleaned = " ".join(replaced.split())
    return cleaned or None


def _bounded_text(value: str | None, *, field: str, max_length: int) -> str | None:
    cleaned = _clean_text(value)
    if cleaned is not None and len(cleaned) > max_length:
        raise ValueError(f"{field} admite como mucho {max_length} caracteres")
    return cleaned


def normalize_source_filename(raw: str | None) -> str | None:
    """El nombre del archivo subido, sin la ruta (con `/` o `\\`) y acortado si es muy largo.

    Solo sirve para nombrar la sesión cuando no tiene título (#240): se acorta, no se rechaza.
    """
    if raw is None:
        return None
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _clean_text(name)
    if cleaned is None:
        return None
    return cleaned[:SOURCE_FILENAME_MAX_LENGTH]


@dataclass(frozen=True, slots=True)
class PartMetadata:
    """El instrumento de una parte y, si se da, su nombre (el que se lee en la partitura)."""

    instrument: Instrument | None = None
    name: str | None = None

    def __post_init__(self) -> None:
        if self.instrument is not None and not isinstance(self.instrument, Instrument):
            object.__setattr__(self, "instrument", Instrument(self.instrument))
        object.__setattr__(
            self,
            "name",
            _bounded_text(
                self.name, field="El nombre de la parte", max_length=PART_NAME_MAX_LENGTH
            ),
        )

    @property
    def is_empty(self) -> bool:
        return self.instrument is None and self.name is None

    def to_primitive(self) -> dict[str, Any]:
        return {
            "instrument": None if self.instrument is None else self.instrument.value,
            "name": self.name,
        }

    @classmethod
    def from_primitive(cls, data: Mapping[str, Any]) -> PartMetadata:
        instrument = data.get("instrument")
        name = data.get("name")
        return cls(
            instrument=None if instrument is None else Instrument(str(instrument)),
            name=None if name is None else str(name),
        )


@dataclass(frozen=True, slots=True)
class ScoreMetadata:
    """Título, compositor e instrumento de cada parte, normalizados (ADR-0041 §1).

    Dos formas de decir lo mismo son iguales: el texto se limpia y las partes vacías del final
    se quitan. La caché del estado compara los metadatos con los del MusicXML guardado.
    """

    title: str | None = None
    composer: str | None = None
    parts: tuple[PartMetadata, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "title", _bounded_text(self.title, field="El título", max_length=TITLE_MAX_LENGTH)
        )
        object.__setattr__(
            self,
            "composer",
            _bounded_text(self.composer, field="El compositor", max_length=COMPOSER_MAX_LENGTH),
        )
        parts = list(self.parts)
        while parts and parts[-1].is_empty:
            parts.pop()
        if len(parts) > MAX_PARTS:
            raise ValueError(f"Se admiten como mucho {MAX_PARTS} partes")
        object.__setattr__(self, "parts", tuple(parts))

    @property
    def is_empty(self) -> bool:
        return self.title is None and self.composer is None and not self.parts

    def part(self, index: int) -> PartMetadata:
        """Los datos de la parte `index` (vacíos si no se dieron)."""
        return self.parts[index] if 0 <= index < len(self.parts) else PartMetadata()

    def fitted(self, part_count: int) -> ScoreMetadata:
        """Sin las partes que la partitura no tiene."""
        if len(self.parts) <= part_count:
            return self
        return ScoreMetadata(
            title=self.title, composer=self.composer, parts=self.parts[:part_count]
        )

    def parts_to_primitive(self) -> list[dict[str, Any]]:
        return [part.to_primitive() for part in self.parts]

    @staticmethod
    def parts_from_primitive(
        data: Sequence[Mapping[str, Any]] | None,
    ) -> tuple[PartMetadata, ...]:
        return tuple(PartMetadata.from_primitive(item) for item in data or ())
