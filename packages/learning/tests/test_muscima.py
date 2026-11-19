"""Pruebas de la lectura de MuNG (MUSCIMA++ v2.0) y su conversión a `ScoreIR` (#102)."""

from __future__ import annotations

from fractions import Fraction

import pytest
from cadenza.domain import Clef, KeySignature, ScoreIR, Tie, TimeSignature
from cadenza.learning import (
    MungConversionError,
    mung_counts,
    mung_texture,
    mung_to_score,
    parse_mung,
)

from .muscima_support import GAP
from .muscima_support import Page as _Page
from .muscima_support import Staff as _Staff


def _events(score: ScoreIR, measure: int) -> list[tuple[str, str | None, Fraction | None]]:
    events = score.parts[0].staves[0].measures[measure].events
    return [(e.kind.value, e.pitch, e.duration_beats) for e in events]


def _measures(score: ScoreIR) -> int:
    return len(score.parts[0].staves[0].measures)


# --- Lectura ---------------------------------------------------------------------------


def test_parse_mung_reads_boxes_classes_and_links() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<Nodes dataset="MUSCIMA-pp_2.0" document="CVC-MUSCIMA_W-01_N-10_D-ideal">
  <Node><Id>0</Id><ClassName>noteheadFull</ClassName><Top>372</Top><Left>494</Left>
    <Width>29</Width><Height>20</Height><Mask>0:1 1:2</Mask><Outlinks>7 3</Outlinks></Node>
  <Node><Id>3</Id><ClassName>stem</ClassName><Top>300</Top><Left>520</Left>
    <Width>3</Width><Height>80</Height></Node>
</Nodes>"""
    nodes = parse_mung(xml)
    assert set(nodes) == {0, 3}
    head = nodes[0]
    assert (head.class_name, head.top, head.left, head.width, head.height) == (
        "noteheadFull",
        372,
        494,
        29,
        20,
    )
    assert head.outlinks == (7, 3)
    assert (head.bottom, head.right) == (392, 523)
    assert nodes[3].outlinks == ()


# --- Conversión de una voz --------------------------------------------------------------


def test_single_staff_converts_clef_key_time_pitches_and_durations() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    staff.key(50, sharps=1)
    staff.time(80, 4, 4)
    staff.note(-2, 120)  # G4
    staff.note(-3, 160)  # Fa, con el sostenido de la armadura
    staff.note(6, 200)  # La sobre una línea adicional
    staff.note(-6, 240)  # Do central bajo una línea adicional
    staff.separator(280)
    beam = page.add("beam", staff.y(4), 300, 60, 6)
    staff.note(0, 300, beams=(beam,))  # B4 corchea
    staff.note(1, 340, beams=(beam,))  # C5 corchea
    staff.note(-1, 380, head="noteheadHalf", dots=1)  # A4 blanca con puntillo
    staff.separator(440)
    staff.rest("restQuarter", 460)
    staff.note(3, 500, flag="flag8thUp")  # E5 corchea con corchete
    staff.rest("rest8th", 540)
    staff.note(-4, 580, head="noteheadWhole")  # E4 redonda
    staff.separator(640)

    score = mung_to_score(page.nodes)

    measures = score.parts[0].staves[0].measures
    assert len(measures) == 3
    first = measures[0]
    assert first.clef == Clef.treble()
    assert first.key_signature == KeySignature(fifths=1)
    assert first.time_signature == TimeSignature(4, 4)
    assert _events(score, 0) == [
        ("note", "G4", Fraction(1)),
        ("note", "F#4", Fraction(1)),
        ("note", "A5", Fraction(1)),
        ("note", "C4", Fraction(1)),
    ]
    assert _events(score, 1) == [
        ("note", "B4", Fraction(1, 2)),
        ("note", "C5", Fraction(1, 2)),
        ("note", "A4", Fraction(3)),
    ]
    assert _events(score, 2) == [
        ("rest", None, Fraction(1)),
        ("note", "E5", Fraction(1, 2)),
        ("rest", None, Fraction(1, 2)),
        ("note", "E4", Fraction(4)),
    ]
    # Lo que no cambia no se repite en los compases siguientes.
    assert measures[1].clef is None and measures[1].key_signature is None
    assert {e.voice for m in measures for e in m.events} == {0}


def test_inline_accidentals_last_until_the_barline_and_natural_cancels_the_key() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    staff.key(50, flats=1)
    staff.note(0, 100)  # B, con el bemol de la armadura
    staff.note(0, 140, accidental="accidentalNatural")  # B natural
    staff.note(0, 180)  # sigue natural en el compás
    staff.note(-3, 220, accidental="accidentalSharp")  # F#
    staff.note(4, 260)  # F5: otra octava, sin alteración
    staff.separator(300)
    staff.note(0, 320)  # vuelve la armadura
    staff.note(-3, 360)  # el sostenido no pasa la barra
    staff.separator(400)

    score = mung_to_score(page.nodes)

    assert [p for _, p, _ in _events(score, 0)] == ["Bb4", "B4", "B4", "F#4", "F5"]
    assert [p for _, p, _ in _events(score, 1)] == ["Bb4", "F4"]


def test_tied_notes_share_the_pitch_and_mark_start_and_stop() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    tie = page.add("tie", staff.y(-3) + 8, 120, 70, 8)
    staff.note(-3, 100, accidental="accidentalSharp", ties=(tie,))
    staff.separator(160)
    staff.note(-3, 200, ties=(tie,))  # sin su sostenido: lo hereda por la ligadura
    staff.note(-3, 240)
    staff.separator(300)

    score = mung_to_score(page.nodes)
    first = score.parts[0].staves[0].measures[0].events[0]
    second, third = score.parts[0].staves[0].measures[1].events
    assert (first.pitch, first.tie) == ("F#4", Tie.START)
    assert (second.pitch, second.tie) == ("F#4", Tie.STOP)
    assert (third.pitch, third.tie) == ("F4", None)


def test_noteheads_on_one_stem_are_a_chord_in_ascending_order() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    stem = page.add("stem", staff.y(4), 122, 2, 4 * GAP)
    staff.note(2, 100, stem=stem)  # D5
    staff.note(-2, 100, stem=stem)  # G4
    staff.note(0, 160)
    staff.separator(200)

    score = mung_to_score(page.nodes)
    events = score.parts[0].staves[0].measures[0].events
    assert [(e.pitch, e.is_chord) for e in events] == [("G4", False), ("D5", True), ("B4", False)]


def test_a_measure_runs_across_the_line_break_and_line_start_context_is_not_repeated() -> None:
    page = _Page()
    upper = _Staff(page, top=200)
    lower = _Staff(page, top=500)
    for staff in (upper, lower):
        staff.clef("fClef", 10)
        staff.key(50, flats=2)
    upper.time(80, 3, 4)
    upper.note(-2, 120)  # B2 en clave de fa
    upper.separator(160)
    upper.note(2, 200)  # F3
    lower.note(0, 120)  # D3: termina el compás que empezó arriba
    lower.separator(160)
    lower.note(-4, 200, head="noteheadHalf")
    lower.separator(260)

    score = mung_to_score(page.nodes)

    assert _measures(score) == 3
    measures = score.parts[0].staves[0].measures
    assert measures[0].clef == Clef.bass()
    assert measures[0].key_signature == KeySignature(fifths=-2)
    assert [m.clef for m in measures[1:]] == [None, None]
    assert [m.key_signature for m in measures[1:]] == [None, None]
    assert [p for _, p, _ in _events(score, 0)] == ["Bb2"]
    assert [p for _, p, _ in _events(score, 1)] == ["F3", "D3"]
    assert _events(score, 2) == [("note", "G2", Fraction(2))]


@pytest.mark.parametrize(("line", "expected"), [(3, "C4"), (4, "A3")])
def test_c_clef_line_comes_from_its_position_on_the_staff(line: int, expected: str) -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("cClef", 10, line=line)
    staff.note(0, 100)  # la línea central
    staff.separator(160)

    score = mung_to_score(page.nodes)
    assert score.parts[0].staves[0].measures[0].clef == Clef(sign="C", line=line)
    assert _events(score, 0)[0][1] == expected


def test_clef_change_inside_a_line_applies_from_there_and_to_the_next_measure() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("fClef", 10)
    staff.note(0, 100)  # D3
    staff.clef("gClef", 140)
    staff.note(0, 180)  # B4: la nueva clave rige desde donde está
    staff.separator(220)
    staff.note(0, 260)
    staff.separator(300)

    score = mung_to_score(page.nodes)
    measures = score.parts[0].staves[0].measures
    assert [p for _, p, _ in _events(score, 0)] == ["D3", "B4"]
    assert measures[0].clef == Clef.bass()
    assert measures[1].clef == Clef.treble()


def test_tuplet_and_common_time_and_whole_rest_filling_the_measure() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    staff.time(60, None)  # C
    three = page.add("numeral3", staff.y(8), 140, 10, 16)
    tuplet = page.add("tuple", staff.y(8), 120, 60, 16, (three,))
    beam = page.add("beam", staff.y(4), 100, 90, 6)
    for i, delta in enumerate((-2, -1, 0)):
        staff.note(delta, 100 + 30 * i, beams=(beam,), tuple_node=tuplet)
    staff.note(1, 200, head="noteheadHalf")
    staff.note(2, 240)
    staff.separator(280)
    staff.rest("restWhole", 320)
    staff.separator(400)

    score = mung_to_score(page.nodes)
    measures = score.parts[0].staves[0].measures
    assert measures[0].time_signature == TimeSignature(4, 4, symbol="common")
    assert [d for _, _, d in _events(score, 0)] == [
        Fraction(1, 3),
        Fraction(1, 3),
        Fraction(1, 3),
        Fraction(2),
        Fraction(1),
    ]
    assert _events(score, 1) == [("rest", None, Fraction(4))]


def test_a_page_without_key_signature_starts_in_c() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    staff.note(0, 100)
    staff.separator(160)
    staff.note(1, 200)
    staff.separator(260)

    measures = mung_to_score(page.nodes).parts[0].staves[0].measures
    assert measures[0].key_signature == KeySignature(fifths=0)
    assert measures[1].key_signature is None


def test_grace_notes_are_left_out_and_counted() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    staff.note(2, 90, head="noteheadFullSmall")
    staff.note(0, 120)
    staff.separator(160)

    score = mung_to_score(page.nodes)
    assert _events(score, 0) == [("note", "B4", Fraction(1))]
    counts = mung_counts(page.nodes)
    assert (counts["noteheads"], counts["grace_noteheads"]) == (1, 1)


# --- Lo que no se convierte -------------------------------------------------------------


def test_texture_and_counts() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    staff.note(0, 100)
    staff.rest("restQuarter", 140)
    staff.separator(180)
    assert mung_texture(page.nodes) == "single_staff"
    counts = mung_counts(page.nodes)
    assert counts["noteheads"] == 1
    assert counts["rests"] == 1
    assert counts["staves"] == 1
    assert counts["measure_separators"] == 1

    other = _Staff(page, top=400)
    shared = page.add("measureSeparator", 200, 180, 3, 300, (staff.id, other.id))
    assert shared in page.nodes
    assert mung_texture(page.nodes) == "multi_staff"


def test_systems_of_several_staves_are_not_converted() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    staff.note(0, 100)
    page.add("brace", 200, 0, 10, 400, (staff.id,))
    with pytest.raises(MungConversionError, match="varios pentagramas"):
        mung_to_score(page.nodes)


def test_a_notehead_on_two_stems_is_polyphony() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    head = staff.note(0, 100)
    other_stem = page.add("stem", staff.y(0), 100, 2, 3 * GAP)
    page.link(head, other_stem)
    with pytest.raises(MungConversionError, match="polifonía"):
        mung_to_score(page.nodes)


def test_simultaneous_notes_on_different_stems_are_polyphony() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    staff.note(2, 100)
    staff.note(-2, 102)  # otra plica, a la misma altura horizontal
    staff.separator(160)
    with pytest.raises(MungConversionError, match="polifonía"):
        mung_to_score(page.nodes)


@pytest.mark.parametrize("class_name", ["multiMeasureRest", "repeat1Bar"])
def test_measure_shorthands_are_not_converted(class_name: str) -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    staff.note(0, 100)
    staff.separator(160)
    staff.symbol(class_name, 200)
    with pytest.raises(MungConversionError, match=class_name):
        mung_to_score(page.nodes)


def test_a_notehead_without_staff_position_is_an_error() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    head = page.add("noteheadFull", staff.y(0) - GAP / 2, 100, 24, GAP)
    page.link(head, staff.id)
    with pytest.raises(MungConversionError, match="posición"):
        mung_to_score(page.nodes)


# --- Casos de la revisión ----------------------------------------------------------------


def test_heads_on_different_stems_that_overlap_a_little_are_polyphony() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    staff.note(2, 100)
    staff.note(-2, 120)  # comparte 4 de sus 24 píxeles con la anterior
    staff.separator(200)
    with pytest.raises(MungConversionError, match="polifonía"):
        mung_to_score(page.nodes)


def test_a_c_clef_between_two_lines_takes_the_previous_c_clef_or_fails() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.symbol("cClef", 10, top=staff.y(1) - 1.5 * GAP, height=3 * GAP)  # entre 3.ª y 4.ª
    staff.note(0, 100)
    staff.separator(160)
    with pytest.raises(MungConversionError, match="entre dos líneas"):
        mung_to_score(page.nodes)

    page = _Page()
    upper = _Staff(page, top=200)
    lower = _Staff(page, top=500)
    upper.clef("cClef", 10, line=4)  # tenor, claro
    upper.note(0, 100)
    upper.separator(160)
    lower.symbol("cClef", 10, top=lower.y(1) - 1.5 * GAP, height=3 * GAP)
    lower.note(0, 100)
    lower.separator(160)
    score = mung_to_score(page.nodes)
    assert score.parts[0].staves[0].measures[0].clef == Clef(sign="C", line=4)
    assert [p for _, p, _ in _events(score, 1)] == ["A3"]


def test_a_repeat_barline_ends_the_measure() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    staff.note(0, 100)
    barline = page.add("barline", 200, 150, 3, 4 * GAP)
    dots = page.add("repeatDot", staff.y(1), 140, 4, 4)
    page.add("repeat", 200, 138, 16, 4 * GAP, (barline, dots))  # sin enlace al pentagrama
    staff.note(1, 200)
    staff.separator(260)

    score = mung_to_score(page.nodes)
    assert _measures(score) == 2
    assert [p for _, p, _ in _events(score, 1)] == ["C5"]


def test_a_tie_across_the_line_break_has_one_head_on_each_side() -> None:
    page = _Page()
    upper = _Staff(page, top=200)
    lower = _Staff(page, top=500)
    for staff in (upper, lower):
        staff.clef("gClef", 10)
    upper.note(0, 100)
    out_tie = page.add("tie", upper.y(0) + 8, 130, 60, 8)  # sale hacia la derecha
    upper.note(-1, 140, ties=(out_tie,))
    in_tie = page.add("tie", lower.y(-1) + 8, 50, 60, 8)  # llega desde la izquierda
    lower.note(-1, 120, ties=(in_tie,))
    lower.separator(200)

    events = mung_to_score(page.nodes).parts[0].staves[0].measures[0].events
    assert [e.tie for e in events] == [None, Tie.START, Tie.STOP]


def test_a_key_change_with_naturals_counts_only_the_new_accidentals() -> None:
    page = _Page()
    upper = _Staff(page, top=200)
    lower = _Staff(page, top=500)
    upper.clef("gClef", 10)
    upper.key(50, flats=2)
    upper.note(0, 120)
    upper.separator(160)
    lower.clef("gClef", 10)
    naturals = [page.add("accidentalNatural", 500, 40 + 8 * i, 8, 30) for i in range(2)]
    sharp = page.add("accidentalSharp", 500, 60, 8, 30)
    lower.symbol("keySignature", 40, *naturals, sharp)
    lower.note(-3, 120)  # F#
    lower.note(0, 160)  # B natural
    lower.separator(200)

    score = mung_to_score(page.nodes)
    assert score.parts[0].staves[0].measures[1].key_signature == KeySignature(fifths=1)
    assert [p for _, p, _ in _events(score, 1)] == ["F#4", "B4"]


def test_a_tuplet_numeral_annotated_twice_counts_once_and_odd_numbers_fail() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    first = page.add("numeral3", staff.y(8), 140, 10, 16)
    again = page.add("numeral3", staff.y(8) + 1, 141, 10, 16)
    tuplet = page.add("tuple", staff.y(8), 120, 60, 16, (first, again))
    beam = page.add("beam", staff.y(4), 100, 90, 6)
    for i, delta in enumerate((-2, -1, 0)):
        staff.note(delta, 100 + 30 * i, beams=(beam,), tuple_node=tuplet)
    staff.separator(220)
    assert [d for _, _, d in _events(mung_to_score(page.nodes), 0)] == [Fraction(1, 3)] * 3

    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    four = page.add("numeral4", staff.y(8), 140, 10, 16)
    tuplet = page.add("tuple", staff.y(8), 120, 60, 16, (four,))
    staff.note(0, 100, flag="flag8thUp", tuple_node=tuplet)
    staff.separator(160)
    with pytest.raises(MungConversionError, match="grupo irregular"):
        mung_to_score(page.nodes)


def test_a_head_between_the_staff_and_its_first_ledger_line() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    # G5, en el espacio sobre el pentagrama, enlazada por error a la primera línea adicional.
    ledger = page.add("legerLine", staff.y(6) - 1, 94, 36, 3)
    head = page.add("noteheadFull", staff.y(5) - GAP / 2, 100, 24, GAP)
    stem = page.add("stem", staff.y(5), 122, 2, 3 * GAP)
    page.link(head, ledger, stem, staff.id)
    staff.separator(160)
    assert _events(mung_to_score(page.nodes), 0)[0][1] == "G5"


def test_a_tie_between_different_positions_does_not_carry_the_accidental() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    tie = page.add("tie", staff.y(-3) + 8, 120, 70, 8)
    staff.note(-3, 100, accidental="accidentalSharp", ties=(tie,))  # F#4
    staff.separator(160)
    staff.note(-2, 200, ties=(tie,))  # G4: la ligadura está mal anotada
    staff.separator(260)
    assert _events(mung_to_score(page.nodes), 1)[0][1] == "G4"


def test_a_whole_rest_without_time_signature_lasts_the_usual_measure() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    for m in range(2):
        for i in range(3):
            staff.note(0, 100 + 200 * m + 40 * i)
        staff.separator(220 + 200 * m)
    staff.rest("restWhole", 500)
    staff.separator(560)
    assert _events(mung_to_score(page.nodes), 2) == [("rest", None, Fraction(3))]


def test_a_rest_that_touches_the_next_head_is_not_polyphony() -> None:
    page = _Page()
    staff = _Staff(page, top=200)
    staff.clef("gClef", 10)
    staff.rest("rest16th", 100)  # 14 de ancho: comparte 4 píxeles con la cabeza siguiente
    staff.note(0, 110, flag="flag16thUp")
    staff.separator(200)
    assert _events(mung_to_score(page.nodes), 0) == [
        ("rest", None, Fraction(1, 4)),
        ("note", "B4", Fraction(1, 4)),
    ]
