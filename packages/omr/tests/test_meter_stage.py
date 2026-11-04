"""Etapa del compás tras HOMR (#237, ADR-0059), con lecturas sintéticas de HOMR.

Cada lectura imita lo que da HOMR 0.7.0: el mismo numerador en todos los compases (la mediana),
la indicación solo donde cambia el denominador y, sin ella, ningún compás (el tramo empezó en
otra página). No hay imágenes ni HOMR: la CI no los tiene.
"""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction

import pytest
from cadenza.domain import (
    Event,
    EventKind,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Staff,
    TimeSignature,
    build_anchor_index,
)
from cadenza.omr.meter_stage import (
    ALL_METER_FEATURES,
    METER_STAGE_VERSION,
    MeterFeature,
    MeterStage,
    marked_figures,
    measure_sum,
    parse_meter_features,
    recognize_meter,
)

NUMERATOR = frozenset({MeterFeature.NUMERATOR})
SYMBOL = frozenset({MeterFeature.SYMBOL})
TUPLETS = frozenset({MeterFeature.IMPLICIT_TUPLETS})
EIGHTH = Fraction(1, 2)
TRIPLET_EIGHTH = Fraction(1, 3)


def _notes(*durations: Fraction | int, voice: int = 0) -> tuple[Event, ...]:
    return tuple(
        Event(kind=EventKind.NOTE, voice=voice, pitch="C5", duration_beats=Fraction(d))
        for d in durations
    )


def _m(number: int, time: TimeSignature | None, *events: Event) -> Measure:
    return Measure(number=number, events=tuple(events), time_signature=time)


def _staff(measures: Sequence[Measure], name: str = "s") -> Staff:
    return Staff(id=name, measures=tuple(measures))


def _score(*staves: Sequence[Measure]) -> ScoreIR:
    """Una parte con un pentagrama por lista de compases (un piano si son dos)."""

    return ScoreIR(
        parts=(Part(id="p", staves=tuple(_staff(m, f"s{i}") for i, m in enumerate(staves))),)
    )


def _times(score: ScoreIR, part: int = 0, staff: int = 0) -> list[str | None]:
    labels: list[str | None] = []
    for measure in score.parts[part].staves[staff].measures:
        ts = measure.time_signature
        labels.append(
            None if ts is None else {"common": "C", "cut": "¢"}.get(ts.symbol or "", str(ts))
        )
    return labels


def _durations(measure: Measure) -> list[Fraction]:
    return [e.duration_beats for e in measure.events if e.duration_beats is not None]


# ------------------------------------------------------------------------------- los rasgos


def test_features_are_parsed_by_name_and_unknown_names_fail() -> None:
    assert parse_meter_features(None) == frozenset()
    assert parse_meter_features("") == frozenset()
    assert parse_meter_features(" none ") == frozenset()
    assert parse_meter_features("all") == ALL_METER_FEATURES
    assert parse_meter_features("numerator, symbol") == NUMERATOR | SYMBOL
    with pytest.raises(ValueError, match="desconocidos: numerador"):
        parse_meter_features("numerador,symbol")


def test_without_features_the_reading_is_left_as_is() -> None:
    score = _score([_m(1, TimeSignature(4, 4), *_notes(1, 1, 1))])

    result, report = recognize_meter(score, ())

    assert result is score
    assert report.to_primitive()["features"] == []
    assert not report.changed


# ------------------------------------------------------------------------------- numerador


def test_the_numerator_of_a_segment_comes_from_its_measures() -> None:
    """Ellens Gesang p. 7: el tramo empezó antes (sin indicación) y HOMR lee el cambio a 3/4 a
    mitad de página con el numerador de la mediana de la página (4/4)."""

    four = TimeSignature(4, 4)
    score = _score(
        [_m(1, None, *_notes(1, 1, 1, 1)), _m(2, None, *_notes(2, 2))]
        + [_m(n, four, *_notes(1, 1, 1)) for n in range(3, 7)]
    )

    result, report = recognize_meter(score, NUMERATOR)

    assert _times(result) == [None, None, "3/4", "3/4", "3/4", "3/4"]
    assert report.segments == (
        {"part": 0, "measures": [3, 6], "read": "4/4", "recognized": "3/4", "changed": True},
    )


def test_each_segment_between_changes_gets_its_own_numerator() -> None:
    # HOMR lee 2/4 y 3/8 (otro denominador, otro tramo) con el numerador de la mediana.
    two, three_eighths = TimeSignature(2, 4), TimeSignature(2, 8)
    score = _score(
        [_m(n, two, *_notes(1, 1, 1)) for n in (1, 2, 3)]
        + [_m(n, three_eighths, *_notes(EIGHTH, EIGHTH, EIGHTH)) for n in (4, 5)]
    )

    result, _ = recognize_meter(score, NUMERATOR)

    assert _times(result) == ["3/4", "3/4", "3/4", "3/8", "3/8"]


def test_the_pickup_and_the_closing_measure_do_not_vote() -> None:
    # Un incipit de PrIMuS: anacrusa de una negra, dos compases de 3/4 y uno cortado.
    read = TimeSignature(2, 4)
    score = _score(
        [
            _m(1, read, *_notes(1)),
            _m(2, read, *_notes(1, 1, 1)),
            _m(3, read, *_notes(2, 1)),
            _m(4, read, *_notes(1, 1)),
        ]
    )

    result, _ = recognize_meter(score, NUMERATOR)

    assert _times(result) == ["3/4"] * 4


def test_the_most_frequent_sum_wins_and_a_tie_goes_to_the_longest() -> None:
    read = TimeSignature(3, 4)
    misread = _score(
        [
            _m(n, read, *_notes(*d))
            for n, d in enumerate([(1, 1, 1, 1)] * 3 + [(1, 1, 1)] + [(2, 2, 1)], 1)
        ]
    )
    tie = _score([_m(1, read, *_notes(1, 1, 1)), _m(2, read, *_notes(2, 2))])

    assert _times(recognize_meter(misread, NUMERATOR)[0]) == ["4/4"] * 5
    assert _times(recognize_meter(tie, NUMERATOR)[0]) == ["4/4"] * 2


@pytest.mark.parametrize(
    "sums",
    [(4, 5, 4), (4, 5, 4, 4), (4, 4, 5, 4)],
    ids=["en-medio", "con-ultimo", "con-primero"],
)
def test_a_measure_read_too_long_does_not_drop_the_full_first_and_last(
    sums: tuple[int, ...],
) -> None:
    read = TimeSignature(4, 4)
    score = _score([_m(n, read, *_notes(*(1,) * total)) for n, total in enumerate(sums, 1)])

    assert recognize_meter(score, NUMERATOR)[0] is score


def test_sums_that_give_no_numerator_do_not_vote() -> None:
    # Con denominador 4, nueve corcheas no son ningún compás: votan los de tres negras.
    read = TimeSignature(4, 4)
    long = _notes(2, 2, EIGHTH)
    score = _score(
        [_m(1, read, *_notes(1, 1, 1))]
        + [_m(n, read, *long) for n in (2, 3, 4)]
        + [_m(n, read, *_notes(1, 1, 1)) for n in (5, 6)]
    )
    # Con el último compás más corto que los demás, no vota: solo quedan los de nueve corcheas.
    cut = _score([_m(n, read, *long) for n in (1, 2, 3)] + [_m(4, read, *_notes(1, 1, 1))])

    assert _times(recognize_meter(score, NUMERATOR)[0]) == ["3/4"] * 6
    assert recognize_meter(cut, NUMERATOR)[0] is cut


def test_a_two_staff_segment_with_a_pickup_takes_the_full_measures() -> None:
    read = TimeSignature(2, 4)
    right = [_m(1, read, *_notes(1))] + [_m(n, read, *_notes(1, 1, 1)) for n in (2, 3, 4)]
    left = [_m(1, read, *_notes(1))] + [_m(n, read, *_notes(3)) for n in (2, 3, 4)]

    result, _ = recognize_meter(_score(right, left), NUMERATOR)

    assert _times(result) == ["3/4"] * 4 and _times(result, staff=1) == ["3/4"] * 4


def test_a_sum_that_is_no_numerator_of_the_read_denominator_keeps_homr() -> None:
    read = TimeSignature(4, 4)
    score = _score([_m(n, read, *_notes(2, 2, EIGHTH)) for n in (1, 2, 3)])

    result, report = recognize_meter(score, NUMERATOR)

    assert result is score
    assert report.segments[0]["changed"] is False


def test_an_empty_segment_keeps_what_homr_read() -> None:
    # La cortesía de final de página, leída como un compás vacío con su indicación.
    score = _score([_m(1, TimeSignature(3, 4), *_notes(1, 1, 1)), _m(2, TimeSignature(3, 2))])

    result, _ = recognize_meter(score, NUMERATOR)

    assert _times(result) == ["3/4", "3/2"]


def test_measure_sum_is_the_longest_voice_without_chord_notes() -> None:
    chord = Event(kind=EventKind.NOTE, pitch="E5", duration_beats=Fraction(1), is_chord=True)
    measure = _m(1, None, *_notes(1, 1), chord, *_notes(1, voice=1))

    assert measure_sum(measure) == 2


# ------------------------------------------------------------------------------- símbolo


def test_four_four_is_written_common_and_two_two_cut() -> None:
    score = ScoreIR(
        parts=(
            Part(id="a", staves=(_staff([_m(1, TimeSignature(4, 4), *_notes(1, 1, 1, 1))]),)),
            Part(id="b", staves=(_staff([_m(1, TimeSignature(2, 2), *_notes(2, 2))]),)),
            Part(id="c", staves=(_staff([_m(1, TimeSignature(3, 4), *_notes(1, 1, 1))]),)),
            Part(id="d", staves=(_staff([_m(1, None, *_notes(1, 1, 1, 1))]),)),
        )
    )

    result, report = recognize_meter(score, SYMBOL)

    assert [_times(result, part)[0] for part in range(4)] == ["C", "¢", "3/4", None]
    assert [item["recognized"] for item in report.segments] == ["C", "¢", "3/4"]


def test_the_symbol_goes_on_the_recognized_numerator() -> None:
    read = TimeSignature(3, 4)
    score = _score([_m(n, read, *_notes(1, 1, 1, 1)) for n in (1, 2)])

    assert _times(recognize_meter(score, NUMERATOR | SYMBOL)[0]) == ["C", "C"]
    assert _times(recognize_meter(score, NUMERATOR)[0]) == ["4/4", "4/4"]


def test_a_symbol_the_engine_gave_is_kept_unless_the_meter_changes() -> None:
    common = TimeSignature(4, 4, "common")
    kept = _score([_m(n, common, *_notes(1, 1, 1, 1)) for n in (1, 2)])
    changed = _score([_m(n, common, *_notes(1, 1, 1)) for n in (1, 2)])

    assert recognize_meter(kept, NUMERATOR)[0] is kept
    assert _times(recognize_meter(changed, NUMERATOR)[0]) == ["3/4", "3/4"]


# ------------------------------------------------------------------------------- tresillos


def test_marked_figures_count_the_measure_and_the_ones_before() -> None:
    measures = [
        _m(1, None, *_notes(EIGHTH, EIGHTH)),
        _m(2, None, *_notes(TRIPLET_EIGHTH, TRIPLET_EIGHTH, TRIPLET_EIGHTH, 1)),
        _m(3, None, *_notes(1, 1)),
    ]

    assert marked_figures(measures) == [frozenset(), {EIGHTH}, {EIGHTH}]


def test_after_a_marked_triplet_the_same_figure_that_does_not_fit_is_a_triplet() -> None:
    """Der stürmische Morgen: el compás 2 tiene tresillos marcados; en el 3, HOMR lee las mismas
    corcheas sin número y el compás no cuadra. El 1, anterior a los marcados, no se toca."""

    read = TimeSignature(2, 4)
    triplet = (TRIPLET_EIGHTH,) * 3
    score = _score(
        [
            _m(1, read, *_notes(EIGHTH, EIGHTH, EIGHTH, 1)),
            _m(2, read, *_notes(*triplet, 1)),
            _m(3, read, *_notes(EIGHTH, EIGHTH, EIGHTH, 1)),
            _m(4, read, *_notes(EIGHTH, EIGHTH, 1)),
        ]
    )

    result, report = recognize_meter(score, TUPLETS)

    measures = result.parts[0].staves[0].measures
    assert _durations(measures[0]) == [EIGHTH] * 3 + [1]
    assert _durations(measures[1]) == [TRIPLET_EIGHTH] * 3 + [1]
    assert _durations(measures[2]) == [TRIPLET_EIGHTH] * 3 + [1]
    assert _durations(measures[3]) == [EIGHTH, EIGHTH, 1]
    assert report.tuplets == ({"part": 0, "staff": 0, "measure": 3, "voices": {"0": "1/2"}},)


def test_without_a_signal_an_overfull_measure_is_not_turned_into_triplets() -> None:
    read = TimeSignature(2, 4)
    score = _score([_m(n, read, *_notes(EIGHTH, EIGHTH, EIGHTH, 1)) for n in (1, 2)])

    result, report = recognize_meter(score, TUPLETS)

    assert result is score
    assert report.tuplets == ()


def test_a_fit_with_two_figures_is_ambiguous_and_left_alone() -> None:
    # En 5/4, tres negras y seis corcheas (6 negras) cuadran pasando a tresillo cualquiera de
    # las dos figuras: no se sabe cuál, así que no se toca. El otro pentagrama dura 5, y con una
    # sola figura los dos compases sí pasarían a tresillos (los de abajo, con seis corcheas).
    read = TimeSignature(5, 4)
    ambiguous = _notes(1, 1, 1, *(EIGHTH,) * 6)
    score = _score(
        [_m(n, read, *ambiguous) for n in (1, 2)], [_m(n, read, *_notes(4, 1)) for n in (1, 2)]
    )
    clear = _score(
        [_m(n, read, *_notes(2, 1, *(EIGHTH,) * 6)) for n in (1, 2)],
        [_m(n, read, *_notes(4, 1)) for n in (1, 2)],
    )
    assert len(recognize_meter(clear, TUPLETS)[1].tuplets) == 2

    result, report = recognize_meter(score, TUPLETS)

    assert result is score
    assert report.tuplets == ()


def test_one_overfull_measure_confirmed_only_by_the_other_staff_is_not_enough() -> None:
    """Una sola negra-negra-negra-tres corcheas en 4/4 (4,5) que cuadra con tresillos, con la
    mano izquierda llena: puede ser un compás leído de más, así que no se toca."""

    read = TimeSignature(4, 4)
    right = [_m(1, read, *_notes(1, 1, 1, EIGHTH, EIGHTH, EIGHTH))] + [
        _m(n, read, *_notes(1, 1, 1, 1)) for n in (2, 3)
    ]
    left = [_m(n, read, *_notes(4)) for n in (1, 2, 3)]

    result, report = recognize_meter(_score(right, left), TUPLETS)

    assert report.tuplets == ()
    assert _durations(result.parts[0].staves[0].measures[0])[-1] == EIGHTH


def test_hidden_rests_are_neither_converted_nor_marked() -> None:
    read = TimeSignature(2, 4)
    gap = Event(kind=EventKind.REST, duration_beats=Fraction(1, 3), hidden=True, voice=1)
    eighths = _notes(EIGHTH, EIGHTH, EIGHTH, 1)
    score = _score([_m(1, read, gap, *_notes(Fraction(5, 3), voice=1)), _m(2, read, *eighths)])

    assert marked_figures(score.parts[0].staves[0].measures) == [frozenset(), frozenset()]
    assert recognize_meter(score, TUPLETS)[1].tuplets == ()


def test_a_measure_converts_only_if_every_overfull_voice_fits() -> None:
    read = TimeSignature(2, 4)
    marked = _m(1, read, *_notes(TRIPLET_EIGHTH, TRIPLET_EIGHTH, TRIPLET_EIGHTH, 1))
    fits = _notes(EIGHTH, EIGHTH, EIGHTH, 1)
    both = _m(2, read, *fits, *_notes(1, 1, 1, voice=1))
    one = _m(2, read, *fits, *_notes(1, 1, voice=1))

    assert recognize_meter(_score([marked, both]), TUPLETS)[1].tuplets == ()
    assert [t["measure"] for t in recognize_meter(_score([marked, one]), TUPLETS)[1].tuplets] == [2]


def test_chord_notes_follow_their_first_note() -> None:
    read = TimeSignature(2, 4)
    chord_note = Event(kind=EventKind.NOTE, pitch="E5", duration_beats=EIGHTH, is_chord=True)
    first, *rest = _notes(EIGHTH, EIGHTH, EIGHTH, 1)
    score = _score(
        [
            _m(1, read, *_notes(TRIPLET_EIGHTH, TRIPLET_EIGHTH, TRIPLET_EIGHTH, 1)),
            _m(2, read, first, chord_note, *rest),
        ]
    )

    result, _ = recognize_meter(score, TUPLETS)

    assert _durations(result.parts[0].staves[0].measures[1]) == [TRIPLET_EIGHTH] * 4 + [1]


def test_the_cut_time_sonata_gets_cut_time_and_triplets_from_the_left_hand() -> None:
    """Claro de luna: HOMR quita los tresillos marcados del compás 1 y lee 3/2 con doce corcheas
    en la mano derecha; la izquierda dura una redonda. Las dos cosas cuadran juntas en ¢."""

    read = TimeSignature(3, 2)
    right = [_m(n, read, *_notes(*(EIGHTH,) * 12)) for n in (1, 2, 3, 4)]
    left = [_m(n, read, *_notes(4)) for n in (1, 2)] + [_m(n, read, *_notes(2, 2)) for n in (3, 4)]
    score = _score(right, left)

    result, report = recognize_meter(score, ALL_METER_FEATURES)

    assert _times(result) == ["¢"] * 4 and _times(result, staff=1) == ["¢"] * 4
    for measure in result.parts[0].staves[0].measures:
        assert _durations(measure) == [TRIPLET_EIGHTH] * 12
    assert [item["measure"] for item in report.tuplets] == [1, 2, 3, 4]
    assert report.segments[0]["read"] == "3/2" and report.segments[0]["recognized"] == "¢"

    # Sin los tresillos, la mano derecha y la izquierda empatan y gana la medida mayor (3/2).
    assert _times(recognize_meter(score, NUMERATOR | SYMBOL)[0]) == ["3/2"] * 4


def test_twelve_eighths_alone_stay_in_three_two() -> None:
    read = TimeSignature(3, 2)
    score = _score([_m(n, read, *_notes(*(EIGHTH,) * 12)) for n in (1, 2, 3)])

    result, report = recognize_meter(score, ALL_METER_FEATURES)

    assert result is score
    assert report.tuplets == ()


def test_a_part_whose_staves_do_not_line_up_is_skipped() -> None:
    read = TimeSignature(4, 4)
    score = _score([_m(1, read, *_notes(1, 1, 1))], [])

    result, report = recognize_meter(score, ALL_METER_FEATURES)

    assert result is score
    assert report.skipped_parts == (0,)


# ------------------------------------------------------------------------------- la etapa


def _document(score: ScoreIR) -> ScoreDocument:
    return ScoreDocument(
        id="doc",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="homr", model_version="0.7.0"),
    )


def test_the_stage_records_itself_in_the_provenance_and_keeps_the_anchors() -> None:
    read = TimeSignature(3, 4)
    document = _document(_score([_m(n, read, *_notes(1, 1, 1, 1)) for n in (1, 2)]))

    staged = MeterStage(NUMERATOR | SYMBOL).apply(document)

    assert _times(staged.score) == ["C", "C"]
    assert staged.provenance.omr_engine == "homr"
    stage = (staged.provenance.omr_stages or {})["meter"]
    assert stage["version"] == METER_STAGE_VERSION
    assert stage["features"] == ["numerator", "symbol"]
    assert stage["segments"][0]["recognized"] == "C"
    assert set(staged.anchors.anchors()) == set(document.anchors.anchors())
    restored = Provenance.from_primitive(staged.provenance.to_primitive())
    assert restored == staged.provenance


def test_a_stage_that_changes_nothing_keeps_the_document_and_says_it_ran() -> None:
    document = _document(_score([_m(1, TimeSignature(3, 4), *_notes(1, 1, 1))]))

    staged = MeterStage(ALL_METER_FEATURES).apply(document)

    assert staged.score is document.score
    assert staged.anchors is document.anchors
    assert (staged.provenance.omr_stages or {})["meter"]["features"] == [
        "numerator",
        "symbol",
        "implicit_tuplets",
    ]
