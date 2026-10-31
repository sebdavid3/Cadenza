"""Título, compositor e instrumento de cada parte de una sesión (#235, ADR-0041)."""

from __future__ import annotations

import pytest
from cadenza.domain import (
    COMPOSER_MAX_LENGTH,
    MAX_PARTS,
    PART_NAME_MAX_LENGTH,
    SOURCE_FILENAME_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    Instrument,
    PartMetadata,
    ScoreMetadata,
    normalize_source_filename,
)


def test_closed_list_has_piano_voice_and_other() -> None:
    values = {instrument.value for instrument in Instrument}
    assert {"piano", "voice", "other"} <= values
    # Identificadores estables en minúsculas, sin espacios: viajan en la API y en la base.
    assert all(value.isascii() and value.islower() and " " not in value for value in values)


def test_empty_metadata_is_empty() -> None:
    assert ScoreMetadata().is_empty
    assert ScoreMetadata(title="  ", composer="", parts=(PartMetadata(),)).is_empty
    assert not ScoreMetadata(title="Mondnacht").is_empty
    assert not ScoreMetadata(parts=(PartMetadata(instrument=Instrument.VOICE),)).is_empty


def test_text_is_trimmed_and_whitespace_collapsed() -> None:
    metadata = ScoreMetadata(title="  Mond\tnacht \n", composer=" Robert   Schumann ")
    assert metadata.title == "Mond nacht"
    assert metadata.composer == "Robert Schumann"


def test_control_characters_become_spaces() -> None:
    assert ScoreMetadata(title="Lied\x00Nr.\x1f2").title == "Lied Nr. 2"


@pytest.mark.parametrize("bad", ["\ud800", "\udfff", "￾", "￿", "\x7f"])
def test_characters_xml_and_utf8_cannot_carry_become_spaces(bad: str) -> None:
    # Un título así rompía el MusicXML exportado o la escritura en la base (revisión de #235).
    metadata = ScoreMetadata(title=f"Lied{bad}2", composer=bad, parts=(PartMetadata(name=bad),))
    assert metadata.title == "Lied 2"
    assert metadata.composer is None
    assert metadata.parts == ()
    assert normalize_source_filename(f"pagina{bad}.png") == "pagina .png"


def test_blank_text_is_none() -> None:
    metadata = ScoreMetadata(title=" \t ", composer="")
    assert metadata.title is None
    assert metadata.composer is None
    assert PartMetadata(name="   ").name is None


def test_too_long_title_is_rejected() -> None:
    assert ScoreMetadata(title="x" * TITLE_MAX_LENGTH).title == "x" * TITLE_MAX_LENGTH
    with pytest.raises(ValueError):
        ScoreMetadata(title="x" * (TITLE_MAX_LENGTH + 1))


def test_too_long_composer_is_rejected() -> None:
    assert ScoreMetadata(composer="x" * COMPOSER_MAX_LENGTH).composer is not None
    with pytest.raises(ValueError):
        ScoreMetadata(composer="x" * (COMPOSER_MAX_LENGTH + 1))


def test_too_long_part_name_is_rejected() -> None:
    PartMetadata(name="x" * PART_NAME_MAX_LENGTH)
    with pytest.raises(ValueError):
        PartMetadata(name="x" * (PART_NAME_MAX_LENGTH + 1))


def test_too_many_parts_are_rejected() -> None:
    ScoreMetadata(parts=tuple(PartMetadata(instrument=Instrument.PIANO) for _ in range(MAX_PARTS)))
    with pytest.raises(ValueError):
        ScoreMetadata(
            parts=tuple(PartMetadata(instrument=Instrument.PIANO) for _ in range(MAX_PARTS + 1))
        )


def test_trailing_empty_parts_are_dropped() -> None:
    metadata = ScoreMetadata(
        parts=(PartMetadata(), PartMetadata(instrument=Instrument.PIANO), PartMetadata(name=" "))
    )
    assert metadata.parts == (PartMetadata(), PartMetadata(instrument=Instrument.PIANO))
    # Dos formas de decir lo mismo son iguales: la caché compara los metadatos (ADR-0041 §5).
    assert metadata == ScoreMetadata(parts=(PartMetadata(), PartMetadata(Instrument.PIANO)))


def test_part_beyond_the_given_ones_has_no_instrument() -> None:
    metadata = ScoreMetadata(parts=(PartMetadata(instrument=Instrument.VOICE),))
    assert metadata.part(0) == PartMetadata(instrument=Instrument.VOICE)
    assert metadata.part(1) == PartMetadata()


def test_fitted_drops_parts_the_score_does_not_have() -> None:
    metadata = ScoreMetadata(
        title="Mondnacht",
        parts=(PartMetadata(Instrument.VOICE), PartMetadata(Instrument.PIANO)),
    )
    fitted = metadata.fitted(1)
    assert fitted.title == "Mondnacht"
    assert fitted.parts == (PartMetadata(Instrument.VOICE),)
    assert metadata.fitted(3) == metadata


def test_parts_primitive_round_trip() -> None:
    metadata = ScoreMetadata(
        title="Mondnacht",
        composer="Robert Schumann",
        parts=(
            PartMetadata(instrument=Instrument.VOICE, name="Soprano"),
            PartMetadata(),
            PartMetadata(instrument=Instrument.OTHER, name="Theremin"),
        ),
    )
    primitive = metadata.parts_to_primitive()
    assert primitive == [
        {"instrument": "voice", "name": "Soprano"},
        {"instrument": None, "name": None},
        {"instrument": "other", "name": "Theremin"},
    ]
    assert ScoreMetadata.parts_from_primitive(primitive) == metadata.parts
    assert ScoreMetadata.parts_from_primitive(None) == ()


def test_unknown_instrument_is_rejected() -> None:
    with pytest.raises(ValueError):
        ScoreMetadata.parts_from_primitive([{"instrument": "kazoo", "name": None}])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("mondnacht.png", "mondnacht.png"),
        ("C:\\fakepath\\Lied Nr. 2.jpg", "Lied Nr. 2.jpg"),
        ("/tmp/subida/pagina\x00uno.png", "pagina uno.png"),
        ("carpeta/", None),
    ],
)
def test_source_filename_keeps_only_the_name(raw: str | None, expected: str | None) -> None:
    assert normalize_source_filename(raw) == expected


def test_long_source_filename_is_shortened() -> None:
    name = "a" * (SOURCE_FILENAME_MAX_LENGTH + 50) + ".png"
    shortened = normalize_source_filename(name)
    assert shortened is not None
    assert len(shortened) == SOURCE_FILENAME_MAX_LENGTH
