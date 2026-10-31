"""Cómo habla el validador: notas, figuras, cantidades, sitios y compases (ADR-0040 §1).

Todo lo que dicen las reglas y la capa de sugerencias sale de aquí, para que digan lo mismo
de la misma manera. Solo usa la biblioteca estándar y `cadenza.domain`.

- Las notas se nombran en solfeo con su alteración y sin octava («Fa♯»); el becuadro solo
  cuando contradice la armadura, y la octava (Do4 es el Do central) solo donde importa.
- Las figuras, por su nombre («corchea con puntillo», «corchea de tresillo»).
- Una cantidad nunca se dice con una fracción ni contando negras: «una corchea», «una negra
  y una semicorchea».
- Los sitios son sintagmas con artículo («el tiempo 3», «la segunda corchea del tiempo 3»),
  que las plantillas combinan con su preposición y su contracción (`de`, `a`).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

from cadenza.domain import Clef, Event, EventKind, TimeSignature

NOTE_NAMES: Final[dict[str, str]] = {
    "C": "Do",
    "D": "Re",
    "E": "Mi",
    "F": "Fa",
    "G": "Sol",
    "A": "La",
    "B": "Si",
}
ACCIDENTAL_SIGNS: Final[dict[str, str]] = {"": "", "#": "♯", "##": "𝄪", "b": "♭", "bb": "𝄫"}
NATURAL_SIGN: Final[str] = "♮"
ACCIDENTAL_WORDS: Final[dict[str, str]] = {
    "": "becuadro",
    "#": "sostenido",
    "##": "doble sostenido",
    "b": "bemol",
    "bb": "doble bemol",
}

_PITCH_RE: Final[re.Pattern[str]] = re.compile(r"^([A-Ga-g])(#{1,2}|b{1,2}|-{1,2}|x)?(-?\d+)$")
_SHARPS_ORDER: Final[str] = "FCGDAEB"
_FLATS_ORDER: Final[str] = "BEADGCF"
_PITCH_CLASS: Final[dict[str, int]] = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_ACCIDENTAL_STEPS: Final[dict[str, int]] = {"": 0, "#": 1, "##": 2, "b": -1, "bb": -2}

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
_DOTS: Final[tuple[tuple[int, Fraction], ...]] = (
    (0, Fraction(1)),
    (1, Fraction(3, 2)),
    (2, Fraction(7, 4)),
)
_TUPLET_FACTOR: Final[Fraction] = Fraction(3, 2)

_NUMBERS_FEMININE: Final[tuple[str, ...]] = (
    "cero",
    "una",
    "dos",
    "tres",
    "cuatro",
    "cinco",
    "seis",
    "siete",
    "ocho",
    "nueve",
    "diez",
    "once",
    "doce",
)
_ORDINALS_FEMININE: Final[tuple[str, ...]] = (
    "",
    "primera",
    "segunda",
    "tercera",
    "cuarta",
    "quinta",
    "sexta",
    "séptima",
    "octava",
)


# --- Notas --------------------------------------------------------------------------------


def split_pitch(pitch: str | None) -> tuple[str, str, int | None]:
    """(letra, alteración normalizada, octava) de una altura científica, o ``("", "", None)``.

    ``-``/``b`` es bemol y ``x``/``##`` doble sostenido, como en el resto del sistema.
    """
    if not pitch:
        return ("", "", None)
    match = _PITCH_RE.match(pitch.strip())
    if not match:
        return ("", "", None)
    accidental = match.group(2) or ""
    if accidental in ("-", "b"):
        accidental = "b"
    elif accidental in ("--", "bb"):
        accidental = "bb"
    elif accidental in ("x", "##"):
        accidental = "##"
    return (match.group(1).upper(), accidental, int(match.group(3)))


def key_accidental(letter: str, fifths: int) -> str:
    """Alteración que la armadura pone a una letra: ``#``, ``b`` o ninguna."""
    if fifths > 0 and letter in _SHARPS_ORDER[:fifths]:
        return "#"
    if fifths < 0 and letter in _FLATS_ORDER[: abs(fifths)]:
        return "b"
    return ""


def midi_of(pitch: str | None) -> int | None:
    """Número MIDI de una altura (Do4 = 60), o None."""
    letter, accidental, octave = split_pitch(pitch)
    if not letter or octave is None:
        return None
    return (octave + 1) * 12 + _PITCH_CLASS[letter] + _ACCIDENTAL_STEPS[accidental]


def note_name(
    pitch: str | None,
    *,
    fifths: int | None = None,
    octave: bool = False,
    fallback: str = "esta nota",
) -> str:
    """Nombre de una altura en solfeo: «Fa♯», «Si♭», «Mi»; con `octave`, «Do8».

    Con la armadura (`fifths`), una nota sin alteración que la armadura alteraría lleva
    becuadro: «Fa♮» en Re mayor. Sin ella, nunca.
    """
    letter, accidental, number = split_pitch(pitch)
    if not letter:
        return fallback
    sign = ACCIDENTAL_SIGNS[accidental]
    if not accidental and fifths is not None and key_accidental(letter, fifths):
        sign = NATURAL_SIGN
    suffix = str(number) if octave and number is not None else ""
    return f"{NOTE_NAMES[letter]}{sign}{suffix}"


def letter_name(pitch: str | None, fallback: str = "esta nota") -> str:
    """El nombre de la letra de una altura, sin alteración ni octava: «Fa»."""
    letter, _, _ = split_pitch(pitch)
    return NOTE_NAMES[letter] if letter else fallback


def accidental_word(accidental: str) -> str:
    """«sostenido», «bemol», «becuadro», «doble sostenido» o «doble bemol»."""
    return ACCIDENTAL_WORDS.get(accidental, accidental)


# --- Números -------------------------------------------------------------------------------


def number_word(value: int, *, feminine: bool = True) -> str:
    """El número en letra hasta doce («una», «seis»; «un» en masculino) y en cifras después."""
    if 0 <= value < len(_NUMBERS_FEMININE):
        word = _NUMBERS_FEMININE[value]
        return "un" if value == 1 and not feminine else word
    return str(value)


def ordinal_word(value: int) -> str | None:
    """«primera» a «octava», o None más allá."""
    if 1 <= value < len(_ORDINALS_FEMININE):
        return _ORDINALS_FEMININE[value]
    return None


# --- Figuras -------------------------------------------------------------------------------


def _as_fraction(duration: object) -> Fraction | None:
    if duration is None:
        return None
    try:
        return Fraction(str(duration))
    except (ValueError, ZeroDivisionError):
        return None


@dataclass(frozen=True, slots=True)
class Figure:
    """Una figura escrita: su base (en negras), sus puntillos y si es de tresillo."""

    base: Fraction
    dots: int = 0
    tuplet: bool = False

    def name(self, *, plural: bool = False) -> str:
        noun = _FIGURES[self.base] + ("s" if plural else "")
        if self.dots == 1:
            noun += " con puntillo"
        elif self.dots == 2:
            noun += " con doble puntillo"
        if self.tuplet:
            noun += " de tresillo"
        return noun

    @property
    def written(self) -> Figure:
        """La figura tal como se escribe, sin el tresillo: la corchea de una corchea de tresillo."""
        return Figure(self.base, self.dots)


def _plain_figure(duration: Fraction) -> Figure | None:
    for dots, factor in _DOTS:
        base = duration / factor
        if base in _FIGURES:
            return Figure(base, dots)
    return None


def figure_of(duration: object) -> Figure | None:
    """La figura de una duración en negras, o None si no es ninguna.

    Una figura de tresillo es la que resulta de multiplicar su duración por 3/2.
    """
    value = _as_fraction(duration)
    if value is None or value <= 0:
        return None
    plain = _plain_figure(value)
    if plain is not None:
        return plain
    written = _plain_figure(value * _TUPLET_FACTOR)
    if written is not None:
        return Figure(written.base, written.dots, tuplet=True)
    return None


def figure_name(duration: object, *, plural: bool = False) -> str:
    """Nombre de la figura de una duración: «negra», «corchea con puntillo», «corchea de
    tresillo»; «figura» si no es ninguna."""
    figure = figure_of(duration)
    if figure is None:
        return "figuras" if plural else "figura"
    return figure.name(plural=plural)


def count_figures(count: int, duration: object) -> str:
    """«una corchea», «seis corcheas», «cuatro negras»."""
    return f"{number_word(count)} {figure_name(duration, plural=count != 1)}"


def _two_figures(duration: Fraction) -> tuple[Fraction, Fraction] | None:
    """Dos figuras sin puntillo distintas que suman la duración, la mayor primero."""
    smallest = min(_FIGURES)
    units = duration / smallest
    if units.denominator != 1:
        return None
    bits = [1 << i for i in range(int(units).bit_length()) if int(units) >> i & 1]
    if len(bits) != 2:
        return None
    large, small = bits[1] * smallest, bits[0] * smallest
    if large not in _FIGURES or small not in _FIGURES:
        return None
    return large, small


def amount(duration: object) -> str | None:
    """Cuánto falta o sobra, con la primera forma que sirva (ADR-0040 §1):

    1. una figura: «una corchea», «una negra con puntillo»;
    2. una figura de tresillo: «una corchea de tresillo»;
    3. dos figuras sin puntillo: «una negra y una semicorchea»;
    4. ninguna: None, y la plantilla no dice cuánto.
    """
    value = _as_fraction(duration)
    if value is None or value <= 0:
        return None
    figure = figure_of(value)
    if figure is not None:
        return f"una {figure.name()}"
    pair = _two_figures(value)
    if pair is None:
        return None
    return f"una {_FIGURES[pair[0]]} y una {_FIGURES[pair[1]]}"


def single_figure(duration: object) -> str | None:
    """La figura sola de una cantidad, sin artículo («corchea»), si es una sola figura."""
    figure = figure_of(duration)
    return None if figure is None else figure.name()


# --- Métrica, armadura y clave -------------------------------------------------------------


def is_compound(signature: TimeSignature | None) -> bool:
    """6/8, 9/8, 12/8 o 6/4: numerador múltiplo de 3 mayor que 3."""
    return signature is not None and signature.beats > 3 and signature.beats % 3 == 0


def meter_name(signature: TimeSignature) -> str:
    """La métrica como se escribe: «3/4»."""
    return str(signature)


def meter_symbol(signature: TimeSignature) -> str | None:
    """El símbolo con que puede escribirse una métrica: C para 4/4 y ¢ para 2/2."""
    if (signature.beats, signature.beat_type) == (4, 4):
        return "C"
    if (signature.beats, signature.beat_type) == (2, 2):
        return "¢"
    return None


def meter_of(quarters: Fraction, beat_type: int) -> TimeSignature | None:
    """La métrica que suma `quarters` negras, con el denominador leído o, si no sale entera,
    con el doble; None si tampoco. Una métrica de 4/8 se dice 2/4."""
    for denominator in (beat_type, beat_type * 2):
        beats = quarters * denominator / 4
        if beats.denominator == 1 and beats > 0:
            if (int(beats), denominator) == (4, 8):
                return TimeSignature(2, 4)
            return TimeSignature(int(beats), denominator)
    return None


def in_beat_figures(quarters: Fraction, beat_type: int) -> str:
    """Lo que suma un compás entero, contado en figuras del denominador: «cuatro negras»,
    «seis corcheas»; con el doble del denominador si no sale entero."""
    for denominator in (beat_type, beat_type * 2):
        unit = Fraction(4, denominator)
        count = quarters / unit
        if count.denominator == 1 and unit in _FIGURES:
            return count_figures(int(count), unit)
    found = amount(quarters)
    return found if found is not None else "otra duración"


def key_name(fifths: int) -> str:
    """«dos sostenidos», «un bemol», «sin alteraciones»."""
    if fifths == 0:
        return "sin alteraciones"
    count = abs(fifths)
    word = "sostenido" if fifths > 0 else "bemol"
    plural = ("s" if fifths > 0 else "es") if count != 1 else ""
    return f"{number_word(count, feminine=False)} {word}{plural}"


_USUAL_LINE: Final[dict[str, int]] = {"G": 2, "F": 4}
_CLEF_WORDS: Final[dict[str, str]] = {"G": "sol", "F": "fa", "C": "do"}


def clef_name(clef: Clef) -> str:
    """«clave de sol», «clave de fa», «clave de do en tercera», «clave de sol en primera» y
    «… octavada alta» u «… octavada baja»."""
    sign = clef.sign.upper()
    word = _CLEF_WORDS.get(sign)
    if word is None:
        name = "clave de percusión" if sign == "PERCUSSION" else f"clave {clef.sign}"
    else:
        name = f"clave de {word}"
        if sign == "C" or clef.line != _USUAL_LINE[sign]:
            line = ordinal_word(clef.line)
            name += f" en {line}" if line else f" en la línea {clef.line}"
    if clef.octave_change > 0:
        name += " octavada alta"
    elif clef.octave_change < 0:
        name += " octavada baja"
    return name


# --- Sintagmas: dónde -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Phrase:
    """Un sintagma nominal con su artículo, para combinarlo con su preposición."""

    article: str
    text: str

    def __str__(self) -> str:
        return f"{self.article} {self.text}"


def de(phrase: Phrase) -> str:
    """«del tiempo 3», «de la segunda corchea del tiempo 3»."""
    return f"del {phrase.text}" if phrase.article == "el" else f"de {phrase}"


def a(phrase: Phrase) -> str:
    """«al compás 3», «a la voz de arriba»."""
    return f"al {phrase.text}" if phrase.article == "el" else f"a {phrase}"


def capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


def measure_phrase(number: int) -> Phrase:
    """«el compás 3»; el compás 0 de MusicXML es «la anacrusa»."""
    if number == 0:
        return Phrase("la", "anacrusa")
    return Phrase("el", f"compás {number}")


def measures_phrase(selected: Sequence[int], measured: Sequence[int]) -> str:
    """Los compases que comparten algo, entre los `measured` (en orden):

    «los compases 2 y 3», «los compases 2 a 7» o, si no son seguidos, «cinco de los seis
    compases del 2 al 7».
    """
    chosen = list(selected)
    if len(chosen) == 1:
        return str(measure_phrase(chosen[0]))
    start = list(measured).index(chosen[0]) if chosen[0] in measured else -1
    contiguous = start >= 0 and list(measured)[start : start + len(chosen)] == chosen
    if contiguous:
        joiner = " y " if len(chosen) == 2 else " a "
        return f"los compases {chosen[0]}{joiner}{chosen[-1]}"
    return (
        f"{number_word(len(chosen), feminine=False)} de los "
        f"{number_word(len(measured), feminine=False)} compases del {measured[0]} al "
        f"{measured[-1]}"
    )


def beat_length(signature: TimeSignature | None) -> Fraction:
    """El tiempo, en negras: la figura del denominador, tres en un compás compuesto y la negra
    en un compás sin métrica."""
    if signature is None:
        return Fraction(1)
    unit = Fraction(4, signature.beat_type)
    return unit * 3 if is_compound(signature) else unit


def position_phrase(onset: Fraction, signature: TimeSignature | None) -> Phrase:
    """Dónde empieza algo, contado desde el principio del compás (ADR-0040 §1):

    «el tiempo 3» en un tiempo justo y, dentro de él, la subdivisión más gruesa que cae justo
    con su ordinal: «la segunda corchea del tiempo 3». Valen las mitades, cuartos y octavos
    del tiempo; en un compás compuesto, los tercios y sextos, y en uno simple, los tercios y
    sextos de tresillo. Si no cabe ninguna, solo el tiempo.
    """
    beat = beat_length(signature)
    number = int(onset // beat) + 1
    offset = onset - (number - 1) * beat
    whole = Phrase("el", f"tiempo {number}")
    if offset == 0:
        return whole
    for parts in (2, 3, 4, 6, 8):
        sub = beat / parts
        steps = offset / sub
        if steps.denominator != 1:
            continue
        figure = figure_of(sub)
        ordinal = ordinal_word(int(steps) + 1)
        if figure is None or ordinal is None:
            break
        if figure.tuplet and is_compound(signature):
            break
        return Phrase("la", f"{ordinal} {figure.name()} del tiempo {number}")
    return whole


# --- Voces ---------------------------------------------------------------------------------


def _mean_height(events: Sequence[Event]) -> float | None:
    heights = [
        midi
        for event in events
        if event.kind is EventKind.NOTE
        and not event.hidden
        and (midi := midi_of(event.pitch)) is not None
    ]
    return sum(heights) / len(heights) if heights else None


def voice_phrases(voices: Mapping[int, Sequence[Event]]) -> dict[int, Phrase]:
    """El nombre de cada voz que se ve de un compás de un pentagrama, o {} si solo hay una.

    Con dos, «la voz de arriba» y «la voz de abajo», por altura media, como las plicas
    (ADR-0032 §2); con más, «la voz 1», «la voz 2»…, de arriba abajo. Una voz que solo tiene
    silencios va al final, y una hecha solo de silencios invisibles no se nombra.
    """
    visible = [
        voice for voice, events in voices.items() if any(not event.hidden for event in events)
    ]
    if len(visible) < 2:
        return {}

    def order(voice: int) -> tuple[int, float, int]:
        height = _mean_height(voices[voice])
        return (1, 0.0, voice) if height is None else (0, -height, voice)

    ranked = sorted(visible, key=order)
    if len(ranked) == 2:
        return {
            ranked[0]: Phrase("la", "voz de arriba"),
            ranked[1]: Phrase("la", "voz de abajo"),
        }
    return {voice: Phrase("la", f"voz {index}") for index, voice in enumerate(ranked, start=1)}
