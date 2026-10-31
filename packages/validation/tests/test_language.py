"""El vocabulario del validador (ADR-0040 §1)."""

from __future__ import annotations

from fractions import Fraction

import pytest
from cadenza.domain import Clef, TimeSignature
from cadenza.validation import language
from cadenza.validation.language import (
    Phrase,
    a,
    amount,
    clef_name,
    count_figures,
    de,
    figure_name,
    in_beat_figures,
    key_name,
    measure_phrase,
    measures_phrase,
    meter_of,
    note_name,
    position_phrase,
    voice_phrases,
)

from packages.validation.tests.rule_builders import n, r


@pytest.mark.parametrize(
    ("pitch", "fifths", "octave", "expected"),
    [
        ("F#4", None, False, "Fa♯"),
        ("Bb3", None, False, "Si♭"),
        ("B-3", None, False, "Si♭"),
        ("E4", None, False, "Mi"),
        ("Cx5", None, False, "Do𝄪"),
        ("Dbb2", None, False, "Re𝄫"),
        ("F4", 2, False, "Fa♮"),
        ("G4", 2, False, "Sol"),
        ("F4", 0, False, "Fa"),
        ("C8", None, True, "Do8"),
        (None, None, False, "esta nota"),
    ],
)
def test_note_names(pitch: str | None, fifths: int | None, octave: bool, expected: str) -> None:
    """Sin octava salvo donde importa, y el becuadro solo cuando contradice la armadura."""
    assert note_name(pitch, fifths=fifths, octave=octave) == expected


@pytest.mark.parametrize(
    ("duration", "plural", "expected"),
    [
        (Fraction(8), False, "cuadrada"),
        (Fraction(4), False, "redonda"),
        (Fraction(2), False, "blanca"),
        (Fraction(1), False, "negra"),
        (Fraction(1, 2), False, "corchea"),
        (Fraction(1, 4), False, "semicorchea"),
        (Fraction(1, 8), False, "fusa"),
        (Fraction(1, 16), False, "semifusa"),
        (Fraction(1, 32), False, "garrapatea"),
        (Fraction(3, 2), False, "negra con puntillo"),
        (Fraction(7, 4), False, "negra con doble puntillo"),
        (Fraction(1, 3), False, "corchea de tresillo"),
        (Fraction(2, 3), False, "negra de tresillo"),
        (Fraction(1, 2), True, "corcheas"),
        (Fraction(3, 2), True, "negras con puntillo"),
        (Fraction(5, 7), False, "figura"),
    ],
)
def test_figure_names(duration: Fraction, plural: bool, expected: str) -> None:
    assert figure_name(duration, plural=plural) == expected


def test_counts_in_words_up_to_twelve() -> None:
    assert count_figures(1, Fraction(1)) == "una negra"
    assert count_figures(6, Fraction(1, 2)) == "seis corcheas"
    assert count_figures(12, Fraction(1, 2)) == "doce corcheas"
    assert count_figures(13, Fraction(1, 2)) == "13 corcheas"


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        (Fraction(1, 2), "una corchea"),
        (Fraction(3, 2), "una negra con puntillo"),
        (Fraction(1, 3), "una corchea de tresillo"),
        (Fraction(5, 4), "una negra y una semicorchea"),
        (Fraction(5, 2), "una blanca y una corchea"),
        (Fraction(7, 8), "una corchea con doble puntillo"),
        (Fraction(11, 8), None),
        (Fraction(1, 5), None),
    ],
)
def test_amounts_never_use_fractions(duration: Fraction, expected: str | None) -> None:
    assert amount(duration) == expected


@pytest.mark.parametrize(
    ("onset", "time", "expected"),
    [
        (Fraction(0), (4, 4), "el tiempo 1"),
        (Fraction(2), (4, 4), "el tiempo 3"),
        (Fraction(7, 2), (4, 4), "la segunda corchea del tiempo 4"),
        (Fraction(1, 4), (4, 4), "la segunda semicorchea del tiempo 1"),
        (Fraction(3, 4), (4, 4), "la cuarta semicorchea del tiempo 1"),
        (Fraction(1, 3), (4, 4), "la segunda corchea de tresillo del tiempo 1"),
        (Fraction(1, 2), (6, 8), "la segunda corchea del tiempo 1"),
        (Fraction(3, 2), (6, 8), "el tiempo 2"),
        (Fraction(1, 2), (3, 8), "el tiempo 2"),
        (Fraction(1, 2), None, "la segunda corchea del tiempo 1"),
        (Fraction(1, 5), (4, 4), "el tiempo 1"),
    ],
)
def test_positions(onset: Fraction, time: tuple[int, int] | None, expected: str) -> None:
    signature = None if time is None else TimeSignature(*time)
    assert str(position_phrase(onset, signature)) == expected


def test_prepositions_contract_with_the_masculine_article() -> None:
    assert de(Phrase("el", "tiempo 3")) == "del tiempo 3"
    assert de(Phrase("la", "segunda corchea del tiempo 3")) == "de la segunda corchea del tiempo 3"
    assert a(Phrase("el", "compás 3")) == "al compás 3"
    assert a(Phrase("la", "voz de arriba")) == "a la voz de arriba"


def test_measures() -> None:
    assert str(measure_phrase(3)) == "el compás 3"
    assert str(measure_phrase(0)) == "la anacrusa"
    assert measures_phrase([2, 3], [2, 3]) == "los compases 2 y 3"
    assert measures_phrase([2, 3, 4, 5, 6, 7], [2, 3, 4, 5, 6, 7]) == "los compases 2 a 7"
    assert (
        measures_phrase([2, 3, 4, 6, 7], [2, 3, 4, 5, 6, 7])
        == "cinco de los seis compases del 2 al 7"
    )


def test_meter_key_and_clef() -> None:
    assert in_beat_figures(Fraction(4), 4) == "cuatro negras"
    assert in_beat_figures(Fraction(3), 8) == "seis corcheas"
    assert meter_of(Fraction(4), 4) == TimeSignature(4, 4)
    assert meter_of(Fraction(2), 8) == TimeSignature(2, 4)
    assert meter_of(Fraction(7, 2), 4) == TimeSignature(7, 8)
    assert meter_of(Fraction(7, 4), 4) is None
    assert key_name(2) == "dos sostenidos"
    assert key_name(-1) == "un bemol"
    assert key_name(-3) == "tres bemoles"
    assert key_name(0) == "sin alteraciones"
    assert clef_name(Clef.treble()) == "clave de sol"
    assert clef_name(Clef.bass()) == "clave de fa"
    assert clef_name(Clef.alto()) == "clave de do en tercera"
    assert clef_name(Clef(sign="G", line=1)) == "clave de sol en primera"
    assert clef_name(Clef(sign="G", line=2, octave_change=-1)) == "clave de sol octavada baja"
    assert clef_name(Clef(sign="F", line=4, octave_change=1)) == "clave de fa octavada alta"


def test_voices_are_named_by_height_only_when_more_than_one_is_seen() -> None:
    single = {0: (n("C4", Fraction(4)),), 1: (r(Fraction(4), voice=1, hidden=True),)}
    assert voice_phrases(single) == {}
    two = {
        0: (n("C4", Fraction(4)),),
        1: (n("E5", Fraction(4), voice=1),),
    }
    assert {voice: str(p) for voice, p in voice_phrases(two).items()} == {
        1: "la voz de arriba",
        0: "la voz de abajo",
    }
    three = {
        0: (r(Fraction(4)),),
        1: (n("C4", Fraction(4), voice=1),),
        2: (n("C5", Fraction(4), voice=2),),
    }
    assert {voice: str(p) for voice, p in voice_phrases(three).items()} == {
        2: "la voz 1",
        1: "la voz 2",
        0: "la voz 3",
    }


def test_the_vocabulary_only_uses_the_standard_library_and_the_domain() -> None:
    source = language.__file__
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        imports = [
            line
            for line in handle
            if line.startswith(("import ", "from ")) and "__future__" not in line
        ]
    allowed = ("re", "collections.abc", "dataclasses", "fractions", "typing", "cadenza.domain")
    assert all(line.split()[1] in allowed for line in imports), imports
