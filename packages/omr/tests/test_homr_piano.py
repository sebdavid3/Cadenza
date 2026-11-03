"""El piano de una página de voz y piano, combinado de las dos lecturas de HOMR (#325, ADR-0060).

Las lecturas son sintéticas: compases de `ScoreIR` como los que da HOMR y el MusicXML mínimo del
que se cuentan los sistemas. La prueba de punta a punta usa MusicXML como el de HOMR 0.7, sin
imágenes ni HOMR.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from fractions import Fraction

import pytest
from cadenza.domain import (
    Clef,
    Event,
    EventKind,
    KeySignature,
    Measure,
    Part,
    ScoreIR,
    Slur,
    SlurType,
    Staff,
    TimeSignature,
)
from cadenza.interchange import musicxml_to_score_ir
from cadenza.omr.adapters.homr_grand_staff import PianoReading
from cadenza.omr.adapters.homr_piano import (
    StaffReading,
    SystemChoice,
    choose_readings,
    combine_musicxml,
    combine_voice_and_piano,
    system_sizes,
    usual_duration,
)

PAIRED, ALONE = PianoReading.PAIRED, PianoReading.ALONE


def _note(pitch: str, beats: Fraction | int = 1, *slurs: Slur) -> Event:
    return Event(
        kind=EventKind.NOTE, pitch=pitch, duration_beats=Fraction(beats), slurs=tuple(slurs)
    )


def _m(number: int, *events: Event, clef: Clef | None = None) -> Measure:
    return Measure(number=number, events=tuple(events), clef=clef)


def _full(number: int, pitch: str, *, clef: Clef | None = None) -> Measure:
    """Un compás de 4/4 con cuatro negras."""

    return _m(number, *(_note(pitch) for _ in range(4)), clef=clef)


def _short(number: int, pitch: str) -> Measure:
    """Un compás al que le falta una negra."""

    return _m(number, *(_note(pitch) for _ in range(3)))


def _staff(
    reading: PianoReading, measures: Sequence[Measure], systems: Sequence[int]
) -> StaffReading:
    return StaffReading(reading, 1, tuple(measures), tuple(systems))


def _pitches(measures: Sequence[Measure]) -> list[str | None]:
    return [measure.events[0].pitch if measure.events else None for measure in measures]


# ----------------------------------------------------------------------------------- sistemas


def _xml(*parts: Sequence[int]) -> str:
    """Un MusicXML con un compás por número, que empieza sistema donde dice cada parte."""

    body = []
    for index, sizes in enumerate(parts, start=1):
        measures = []
        number = 1
        for system, size in enumerate(sizes):
            for position in range(size):
                printed = '<print new-system="yes" />' if system and position == 0 else ""
                measures.append(f'<measure number="{number}">{printed}</measure>')
                number += 1
        body.append(f'<part id="P{index}">{"".join(measures)}</part>')
    return f"<score-partwise>{''.join(body)}</score-partwise>"


def test_systems_are_counted_where_homr_starts_each_one() -> None:
    assert system_sizes(_xml([2, 3], [1, 1, 1])) == [[2, 3], [1, 1, 1]]
    # El salto de sistema del primer compás no abre un sistema vacío.
    first = '<part id="P1"><measure><print new-system="yes" /></measure><measure /></part>'
    assert system_sizes(f"<score-partwise>{first}</score-partwise>") == [[2]]


def test_the_usual_duration_is_the_most_repeated_and_the_longer_on_a_tie() -> None:
    assert usual_duration([_full(1, "C5"), _short(2, "C5"), _full(3, "C5")]) == 4
    assert usual_duration([_full(1, "C5"), _short(2, "C5")]) == 4
    assert usual_duration([_m(1)]) is None


def test_measures_without_notes_are_irregular() -> None:
    # Un compás que HOMR deja vacío perdió sus notas: cuenta contra la lectura.
    staff = _staff(PAIRED, [_full(1, "C5"), _m(2), _short(3, "C5")], [3])
    assert staff.irregular(0, Fraction(4)) == 2


def test_a_reading_must_cover_its_measures_with_its_systems() -> None:
    with pytest.raises(ValueError, match="sistemas"):
        _staff(PAIRED, [_full(1, "C5")], [2])


# ----------------------------------------------------------------------- la lectura de cada mano


def test_each_hand_takes_the_reading_with_fewer_irregular_measures() -> None:
    paired = [
        _staff(PAIRED, [_full(1, "C5"), _short(2, "C5"), _full(3, "C5")], [1, 2]),
        _staff(PAIRED, [_full(1, "C3"), _full(2, "C3"), _full(3, "C3")], [1, 2]),
    ]
    alone = [
        _staff(ALONE, [_full(1, "E5"), _full(2, "E5"), _full(3, "E5")], [1, 2]),
        _staff(ALONE, [_full(1, "E3"), _short(2, "E3"), _full(3, "E3")], [1, 2]),
    ]

    assert choose_readings(paired, alone) == [
        SystemChoice(PAIRED, PAIRED),  # nada irregular: a igualdad, la emparejada
        SystemChoice(ALONE, PAIRED),
    ]


def test_a_hand_alone_with_other_measures_in_the_system_is_not_taken() -> None:
    # La lectura sola es mejor en las dos manos, pero tiene un compás más que la emparejada: el
    # piano dejaría de tener los compases de la voz desde ese sistema (#239 los alinea).
    paired = [
        _staff(PAIRED, [_short(1, "C5"), _full(2, "C5"), _full(3, "C5")], [2, 1]),
        _staff(PAIRED, [_short(1, "C3"), _full(2, "C3"), _full(3, "C3")], [2, 1]),
    ]
    alone = [
        _staff(ALONE, [_full(1, "E5"), _full(2, "E5"), _full(3, "E5"), _full(4, "E5")], [3, 1]),
        _staff(ALONE, [_full(1, "E3"), _full(2, "E3"), _full(3, "E3")], [2, 1]),
    ]

    assert choose_readings(paired, alone) == [
        SystemChoice(PAIRED, ALONE),
        SystemChoice(PAIRED, PAIRED),
    ]


def test_a_hand_alone_that_lost_its_notes_is_not_taken() -> None:
    # Sola, la mano derecha deja vacíos dos compases del sistema 2; emparejada, uno es corto.
    paired = [
        _staff(PAIRED, [_full(1, "C5"), _full(2, "C5"), _full(3, "C5"), _short(4, "C5")], [1, 3]),
        _staff(PAIRED, [_full(1, "C3"), _full(2, "C3"), _full(3, "C3"), _full(4, "C3")], [1, 3]),
    ]
    alone = [
        _staff(ALONE, [_full(1, "E5"), _m(2), _m(3), _full(4, "E5")], [1, 3]),
        _staff(ALONE, [_full(1, "E3"), _full(2, "E3"), _full(3, "E3"), _full(4, "E3")], [1, 3]),
    ]

    assert choose_readings(paired, alone)[1] == SystemChoice(PAIRED, PAIRED)


def test_a_hand_alone_with_another_usual_duration_is_not_taken() -> None:
    # Sola, la mano derecha lee tres tiempos en todos los compases: con su propia habitual
    # parecería regular, pero dejaría compases de 3 frente a los de 4 de la mano izquierda.
    paired = [
        _staff(PAIRED, [_full(1, "C5"), _full(2, "C5"), _full(3, "C5"), _short(4, "C5")], [2, 2]),
        _staff(PAIRED, [_full(1, "C3"), _full(2, "C3"), _full(3, "C3"), _full(4, "C3")], [2, 2]),
    ]
    alone = [
        _staff(ALONE, [_short(n, "E5") for n in range(1, 5)], [2, 2]),
        _staff(ALONE, [_full(n, "E3") for n in range(1, 5)], [2, 2]),
    ]

    assert choose_readings(paired, alone) == [
        SystemChoice(PAIRED, PAIRED),
        SystemChoice(PAIRED, PAIRED),
    ]


def test_readings_with_different_systems_are_not_combined() -> None:
    paired = [_staff(PAIRED, [_full(1, "C5")], [1]), _staff(PAIRED, [_full(1, "C3")], [1])]
    alone = [
        _staff(ALONE, [_full(1, "E5"), _full(2, "E5")], [1, 1]),
        _staff(ALONE, [_full(1, "E3"), _full(2, "E3")], [1, 1]),
    ]
    with pytest.raises(ValueError, match="sistemas"):
        choose_readings(paired, alone)


# ------------------------------------------------------------------------------- la combinación


def _part(index: int, *staves: Sequence[Measure]) -> Part:
    return Part(
        id=f"part-{index}",
        staves=tuple(
            Staff(id=f"part-{index}-staff-{s}", measures=tuple(m)) for s, m in enumerate(staves)
        ),
    )


VOICE = [_full(1, "A4", clef=Clef.treble()), _full(2, "A4"), _full(3, "A4"), _full(4, "A4")]


def _paired() -> ScoreIR:
    right = [
        _m(1, _note("C5", 1, Slur(SlurType.START, 1)), *(_note("C5") for _ in range(3))),
        _m(2, _note("C5", 1, Slur(SlurType.STOP, 1)), *(_note("C5") for _ in range(3))),
        _short(3, "C5"),
        _full(4, "C5"),
    ]
    right[0] = Measure(number=1, events=right[0].events, clef=Clef.treble())
    left = [_full(1, "C3", clef=Clef.bass()), _full(2, "C3"), _full(3, "C3"), _full(4, "C3")]
    return ScoreIR(parts=(_part(0, VOICE), _part(1, right, left)))


def _alone() -> ScoreIR:
    right = [
        _full(1, "E5", clef=Clef.treble()),
        # La lectura sola cambia a la clave de fa en el sistema 1 y la mantiene en el 2.
        _m(
            2,
            *(_note("E5") for _ in range(3)),
            _note("E5", 1, Slur(SlurType.START, 1)),
            clef=Clef.bass(),
        ),
        _m(
            3,
            _note("E5", 1, Slur(SlurType.STOP, 1)),
            _note("E5", 1, Slur(SlurType.START, 2)),
            _note("E5"),
            _note("E5"),
        ),
        _m(4, _note("E5", 1, Slur(SlurType.STOP, 2)), *(_note("E5") for _ in range(3))),
    ]
    left = [_full(1, "E3", clef=Clef.bass()), _short(2, "E3"), _full(3, "E3"), _full(4, "E3")]
    return ScoreIR(parts=(_part(0, VOICE), _part(1, right), _part(2, left)))


PAIRED_XML = _xml([2, 2], [2, 2])
ALONE_XML = _xml([2, 2], [2, 2], [2, 2])


def test_the_piano_is_spliced_system_by_system_and_hand_by_hand() -> None:
    result = combine_voice_and_piano(_paired(), PAIRED_XML, _alone(), ALONE_XML)
    assert result is not None
    score, choices = result

    # Sistema 1: la izquierda sola tiene un compás corto; sistema 2: la derecha emparejada.
    assert choices == [SystemChoice(PAIRED, PAIRED), SystemChoice(ALONE, PAIRED)]
    assert score.parts[0] == _paired().parts[0]
    right, left = score.parts[1].staves
    assert (right.id, left.id) == ("part-1-staff-0", "part-1-staff-1")
    assert _pitches(right.measures) == ["C5", "C5", "E5", "E5"]
    assert _pitches(left.measures) == ["C3", "C3", "C3", "C3"]
    assert [m.number for m in right.measures] == [1, 2, 3, 4]


def test_a_spliced_system_starts_with_the_clef_in_force_in_its_reading() -> None:
    result = combine_voice_and_piano(_paired(), PAIRED_XML, _alone(), ALONE_XML)
    assert result is not None
    right = result[0].parts[1].staves[0]

    assert [m.clef for m in right.measures] == [Clef.treble(), None, Clef.bass(), None]


def test_slurs_keep_both_ends_and_are_renumbered() -> None:
    result = combine_voice_and_piano(_paired(), PAIRED_XML, _alone(), ALONE_XML)
    assert result is not None
    right = result[0].parts[1].staves[0]
    slurs = [
        [slur for event in measure.events for slur in event.slurs] for measure in right.measures
    ]

    # La de la lectura sola que empieza en el sistema 1 (no elegido) se pierde con su final.
    assert slurs == [
        [Slur(SlurType.START, 1)],
        [Slur(SlurType.STOP, 1)],
        [Slur(SlurType.START, 2)],
        [Slur(SlurType.STOP, 2)],
    ]


def test_the_time_signature_is_carried_only_when_it_changes() -> None:
    four = TimeSignature(4, 4)
    paired = _paired()
    right, left = paired.parts[1].staves
    paired = ScoreIR(
        parts=(
            paired.parts[0],
            Part(
                id="part-1",
                staves=(
                    Staff(
                        id=right.id,
                        measures=(
                            Measure(
                                number=1,
                                events=right.measures[0].events,
                                clef=Clef.treble(),
                                time_signature=four,
                            ),
                            *right.measures[1:],
                        ),
                    ),
                    left,
                ),
            ),
        )
    )
    alone = _alone()
    alone_right = alone.parts[1].staves[0]
    first = Measure(
        number=1, events=alone_right.measures[0].events, clef=Clef.treble(), time_signature=four
    )
    alone = ScoreIR(
        parts=(
            alone.parts[0],
            Part(
                id="part-1",
                staves=(Staff(id=alone_right.id, measures=(first, *alone_right.measures[1:])),),
            ),
            alone.parts[2],
        )
    )

    result = combine_voice_and_piano(paired, PAIRED_XML, alone, ALONE_XML)
    assert result is not None
    assert [m.time_signature for m in result[0].parts[1].staves[0].measures] == [
        four,
        None,
        None,
        None,
    ]


def test_a_spliced_system_starts_with_the_key_in_force_in_its_reading() -> None:
    # La lectura sola lee un bemol en el sistema 1 (no elegido) y lo mantiene en el 2, que sí se
    # elige para la mano derecha: el sistema empalmado empieza con esa armadura.
    alone = _alone()
    alone_right = alone.parts[1].staves[0]
    second = replace(alone_right.measures[1], key_signature=KeySignature(-1))
    alone = ScoreIR(
        parts=(
            alone.parts[0],
            Part(
                id="part-1",
                staves=(
                    Staff(
                        id=alone_right.id,
                        measures=(alone_right.measures[0], second, *alone_right.measures[2:]),
                    ),
                ),
            ),
            alone.parts[2],
        )
    )

    result = combine_voice_and_piano(_paired(), PAIRED_XML, alone, ALONE_XML)
    assert result is not None
    right, left = result[0].parts[1].staves
    assert [m.key_signature for m in right.measures] == [None, None, KeySignature(-1), None]
    assert [m.key_signature for m in left.measures] == [None, None, None, None]


def test_pages_that_are_not_voice_and_piano_are_not_combined() -> None:
    paired, alone = _paired(), _alone()
    piano_alone = ScoreIR(parts=(paired.parts[1],))

    assert combine_voice_and_piano(piano_alone, _xml([2, 2]), alone, ALONE_XML) is None
    assert combine_voice_and_piano(paired, PAIRED_XML, paired, PAIRED_XML) is None
    # Otros sistemas en la lectura sola: no se sabe qué compases emparejar.
    assert combine_voice_and_piano(paired, PAIRED_XML, alone, _xml([4], [4], [4])) is None
    # Tampoco si solo cambian los de la voz: HOMR se saltó sistemas distintos en cada lectura.
    assert combine_voice_and_piano(paired, PAIRED_XML, alone, _xml([4], [2, 2], [2, 2])) is None


# ------------------------------------------------------------------------- de punta a punta

_HEADER = (
    '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n<score-partwise version="4.0">'
    "<part-list>{parts}</part-list>"
)


def _score_part(index: int) -> str:
    return f'<score-part id="P{index}"><part-name>Voice</part-name></score-part>'


def _notes(pitch: str, beats: Sequence[int], staff: int = 1) -> str:
    step, octave = pitch[0], pitch[1]
    names = {1: "quarter", 2: "half", 4: "whole"}
    return "".join(
        f"<note><pitch><step>{step}</step><octave>{octave}</octave></pitch>"
        f"<duration>{d}</duration><voice>{1 if staff == 1 else 5}</voice>"
        f"<type>{names[d]}</type><staff>{staff}</staff></note>"
        for d in beats
    )


def _attributes(clefs: Sequence[tuple[str, int]], staves: int = 1) -> str:
    staves_xml = f"<staves>{staves}</staves>" if staves > 1 else ""
    clef_xml = "".join(
        f'<clef number="{n}"><sign>{sign}</sign><line>{line}</line></clef>'
        for n, (sign, line) in enumerate(clefs, start=1)
    )
    return (
        "<attributes><divisions>1</divisions><key><fifths>0</fifths></key>"
        f"<time><beats>4</beats><beat-type>4</beat-type></time>{staves_xml}{clef_xml}</attributes>"
    )


def _measure(number: int, body: str, *, new_system: bool = False, attributes: str = "") -> str:
    printed = '<print new-system="yes" />' if new_system else ""
    return f'<measure number="{number}">{printed}{attributes}{body}</measure>'


def _part_xml(index: int, measures: Sequence[str]) -> str:
    return f'<part id="P{index}">{"".join(measures)}</part>'


def _voice_part() -> str:
    return _part_xml(
        1,
        [
            _measure(1, _notes("A4", [4]), attributes=_attributes([("G", 2)])),
            _measure(2, _notes("A4", [4]), new_system=True),
        ],
    )


def _homr_readings(paired_right: Sequence[int]) -> tuple[str, str]:
    """El MusicXML de las dos lecturas de HOMR de una página de dos sistemas: en el segundo, la
    mano derecha emparejada lee `paired_right` y la sola, dos blancas."""

    piano = _part_xml(
        2,
        [
            _measure(
                1,
                _notes("C5", [1, 1, 1, 1])
                + "<backup><duration>4</duration></backup>"
                + _notes("C3", [4], staff=2),
                attributes=_attributes([("G", 2), ("F", 4)], staves=2),
            ),
            _measure(
                2,
                _notes("C5", paired_right)
                + f"<backup><duration>{sum(paired_right)}</duration></backup>"
                + _notes("C3", [4], staff=2),
                new_system=True,
            ),
        ],
    )
    paired_xml = (
        _HEADER.format(parts=_score_part(1) + _score_part(2))
        + _voice_part()
        + piano
        + "</score-partwise>"
    )
    right = _part_xml(
        2,
        [
            _measure(1, _notes("E5", [1, 1, 1, 1]), attributes=_attributes([("G", 2)])),
            _measure(2, _notes("E5", [2, 2]), new_system=True),
        ],
    )
    left = _part_xml(
        3,
        [
            _measure(1, _notes("E3", [4]), attributes=_attributes([("F", 4)])),
            _measure(2, _notes("E3", [4]), new_system=True),
        ],
    )
    alone_xml = (
        _HEADER.format(parts=_score_part(1) + _score_part(2) + _score_part(3))
        + _voice_part()
        + right
        + left
        + "</score-partwise>"
    )
    return paired_xml, alone_xml


def test_homr_readings_combine_into_the_voice_above_the_piano() -> None:
    # Emparejada: en el sistema 2 la mano derecha suma tres negras (HOMR se equivocó).
    paired_xml, alone_xml = _homr_readings([1, 1, 1])

    score = musicxml_to_score_ir(combine_musicxml(paired_xml, alone_xml))

    assert [len(part.staves) for part in score.parts] == [1, 2]
    voice, (rh, lh) = score.parts[0].staves[0], score.parts[1].staves
    assert _pitches(voice.measures) == ["A4", "A4"]
    assert _pitches(rh.measures) == ["C5", "E5"]
    assert [e.duration_beats for e in rh.measures[1].events] == [2, 2]
    assert _pitches(lh.measures) == ["C3", "C3"]
    assert lh.measures[0].clef == Clef.bass()


def test_if_no_hand_is_taken_alone_the_paired_reading_is_returned_as_is() -> None:
    # Las dos lecturas valen igual: sin pasar por el exportador, la de HOMR con sus saltos de
    # sistema y sus ligaduras (#239).
    paired_xml, alone_xml = _homr_readings([1, 1, 1, 1])

    assert combine_musicxml(paired_xml, alone_xml) == paired_xml


def test_a_combination_that_does_not_import_again_leaves_the_paired_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cadenza.interchange

    monkeypatch.setattr(cadenza.interchange, "score_ir_to_musicxml", lambda score: "<roto")
    paired_xml, alone_xml = _homr_readings([1, 1, 1])

    assert combine_musicxml(paired_xml, alone_xml) == paired_xml


def test_readings_that_cannot_be_combined_leave_the_paired_one() -> None:
    paired_xml = _HEADER.format(parts=_score_part(1)) + _voice_part() + "</score-partwise>"
    assert combine_musicxml(paired_xml, paired_xml) == paired_xml


def test_a_combination_that_fails_leaves_the_paired_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cadenza.omr.adapters import homr_piano

    def broken(*args: object) -> None:
        raise RuntimeError("roto")

    monkeypatch.setattr(homr_piano, "combine_voice_and_piano", broken)
    paired_xml = _HEADER.format(parts=_score_part(1)) + _voice_part() + "</score-partwise>"

    assert combine_musicxml(paired_xml, "<no es MusicXML") == paired_xml
