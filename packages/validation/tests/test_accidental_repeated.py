"""Pruebas de `accidental.repeated`: alteración repetida (ADR-0040 §7)."""

from __future__ import annotations

from collections.abc import Callable
from fractions import Fraction
from functools import partial

from cadenza.domain import (
    EditOp,
    Event,
    EventKind,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Staff,
    build_anchor_index,
    validate_after,
)
from cadenza.validation import AccidentalRepeatedRule, ValidationEngine

from packages.validation.tests.rule_builders import (
    BLANCA,
    BLANCA_PUNTILLO,
    CORCHEA,
    NEGRA,
    REDONDA,
    document,
    full,
    m,
    n,
    r,
    surrounded,
)


def _flagged(doc: ScoreDocument) -> list[tuple[int, int, int]]:
    findings = ValidationEngine([AccidentalRepeatedRule()]).validate(doc)
    return [(f.anchor.measure, f.anchor.voice, f.anchor.event_index) for f in findings]


def test_rule_id() -> None:
    assert AccidentalRepeatedRule().rule_id == "accidental.repeated"


def test_the_same_letter_in_another_octave_does_not_fire() -> None:
    doc = surrounded(m(2, n("F#4", NEGRA), n("F#5", NEGRA), n("G4", BLANCA)))
    assert _flagged(doc) == []


def test_a_note_of_another_voice_does_not_fire() -> None:
    doc = surrounded(
        m(
            2,
            n("F#4", BLANCA, voice=0),
            n("G4", BLANCA, voice=0),
            n("C4", NEGRA, voice=1),
            n("F#4", NEGRA, voice=1),
            n("C4", BLANCA, voice=1),
        )
    )
    assert _flagged(doc) == []


def test_the_barline_cancels_the_accidental() -> None:
    doc = document([m(1, n("F#4", Fraction(4))), m(2, n("F#4", Fraction(4))), full(3)])
    assert _flagged(doc) == []


def test_an_accidental_of_the_key_does_not_fire() -> None:
    doc = surrounded(m(2, n("F#4", BLANCA), n("F#4", BLANCA), fifths=2))
    assert _flagged(doc) == []


def test_a_natural_against_the_key_does_not_fire() -> None:
    """En el recuento, ninguno de los 4 becuadros repetidos contra la armadura era un error."""
    doc = surrounded(m(2, n("F4", BLANCA), n("F4", BLANCA), fifths=2))
    assert _flagged(doc) == []


def test_every_repetition_is_flagged_but_not_the_first_note() -> None:
    doc = surrounded(m(2, n("C#4", NEGRA), n("C#4", NEGRA), n("D4", NEGRA), n("C#4", NEGRA)))
    assert _flagged(doc) == [(2, 0, 1), (2, 0, 3)]


def test_grace_and_chord_notes_count_as_previous() -> None:
    grace = n("B-4", Fraction(0))
    chord = Event(kind=EventKind.NOTE, pitch="Eb4", duration_beats=BLANCA, is_chord=True)
    doc = surrounded(m(2, grace, n("Bb4", BLANCA), chord, n("Eb4", BLANCA)))
    assert _flagged(doc) == [(2, 0, 1), (2, 0, 3)]


def test_the_key_in_force_is_the_one_of_the_measure() -> None:
    doc = document(
        [
            m(1, n("C5", Fraction(4)), fifths=0),
            m(2, n("F#4", BLANCA), n("F#4", BLANCA), fifths=1),
            m(3, n("F#4", BLANCA), n("F#4", BLANCA), fifths=0),
            full(4),
        ]
    )
    assert _flagged(doc) == [(3, 0, 1)]


def test_double_sharps_and_their_message() -> None:
    doc = surrounded(m(2, n("F##4", BLANCA), n("F##4", BLANCA), fifths=2))
    (finding,) = ValidationEngine([AccidentalRepeatedRule()]).validate(doc)
    assert finding.message == (
        "El Fa𝄪 del tiempo 3 repite el doble sostenido del Fa del tiempo 1, y la armadura no lo "
        "lleva."
    )
    assert finding.suggested_fix == (
        "Mira si en la partitura este Fa lleva sostenido: entonces es Fa♯, no Fa𝄪."
    )


def test_the_candidate_is_a_valid_edit_to_the_key_accidental() -> None:
    doc = surrounded(m(2, n("B4", NEGRA), n("Bb4", NEGRA), n("Bb4", BLANCA), fifths=0))
    (finding,) = AccidentalRepeatedRule().evaluate(doc)
    (candidate,) = finding.candidates
    assert candidate.op is EditOp.SET_ACCIDENTAL
    assert dict(candidate.after or {}) == {"accidental": ""}
    validate_after(doc.score, candidate.anchor, candidate.op, candidate.after)


# --- #318: TS-02, *Letzte Hoffnung* (cc. 6-13 del lied, compases 1 a 8 del banco) ----------
#
# Los compases de la verdad del banco del estudio (#247), en 3 bemoles y 3/4. La voz repite en
# el compás una alteración que la armadura no lleva, escrita una sola vez, como se escribe en
# la práctica común: vale hasta la barra. Antes de #318 daba tres avisos falsos: el segundo
# Do♭ de los compases 1 y 5 y el segundo Fa♯ del compás 8. El piano lleva en el mismo compás
# la misma alteración: el Do♭5 del acorde de la mano derecha y el Fa♯ de las dos manos.

_TS02 = (3, 4)
_FIFTHS = {1: -3}


def _ts02_voice(number: int) -> Measure:
    if number in (1, 5):
        return m(
            number,
            n("Cb5", CORCHEA),
            n("Ab4", CORCHEA),
            n("Cb5", Fraction(3, 2)),
            n("Ab4", CORCHEA),
            time=_TS02,
            fifths=_FIFTHS.get(number),
        )
    if number == 8:
        return m(8, n("F#4", BLANCA), n("F#4", NEGRA), time=_TS02)
    return full(number, _TS02)


def _ts02_right_hand(number: int) -> Measure:
    if number in (1, 5):
        return m(
            number,
            r(CORCHEA),
            n("F5", CORCHEA),
            n("D5", CORCHEA),
            r(CORCHEA),
            r(CORCHEA),
            n("F4", CORCHEA),
            n("Ab4", CORCHEA, chord=True),
            n("Cb5", CORCHEA, chord=True),
            time=_TS02,
            fifths=_FIFTHS.get(number),
        )
    if number == 8:
        return m(8, n("F#4", BLANCA_PUNTILLO), time=_TS02)
    return full(number, _TS02)


def _ts02_left_hand(number: int, *, f_sharp: str = "F#3") -> Measure:
    if number in (1, 5):
        return m(
            number,
            n("Ab3", CORCHEA),
            r(CORCHEA),
            r(CORCHEA),
            n("Ab4", CORCHEA),
            n("F4", CORCHEA),
            n("D4", CORCHEA),
            time=_TS02,
            fifths=_FIFTHS.get(number),
        )
    if number == 8:
        return m(8, n(f_sharp, BLANCA_PUNTILLO), time=_TS02)
    return full(number, _TS02)


def _staff(staff_id: str, build: Callable[[int], Measure], numbers: range = range(1, 10)) -> Staff:
    return Staff(id=staff_id, measures=tuple(build(number) for number in numbers))


def _doc(*parts: Part) -> ScoreDocument:
    score = ScoreIR(parts=parts)
    return ScoreDocument(
        id="ts02", score=score, anchors=build_anchor_index(score), provenance=Provenance("fake")
    )


def _ts02_flagged(doc: ScoreDocument) -> list[tuple[int, int, int, int, int]]:
    findings = ValidationEngine([AccidentalRepeatedRule()]).validate(doc)
    return [
        (f.anchor.part, f.anchor.staff, f.anchor.measure, f.anchor.voice, f.anchor.event_index)
        for f in findings
    ]


def test_ts02_truth_has_no_repeated_accidental_warning() -> None:
    """Como el MusicXML de la verdad: el piano (dos pentagramas) y la voz, en dos partes."""
    piano = Part(
        id="P1",
        staves=(_staff("P1-S1", _ts02_right_hand), _staff("P1-S2", _ts02_left_hand)),
    )
    voice = Part(id="P2", staves=(_staff("P2-S1", _ts02_voice),))
    assert _ts02_flagged(_doc(piano, voice)) == []


def test_ts02_as_homr_reads_it_has_no_repeated_accidental_warning() -> None:
    """Como lo lee HOMR: una parte con los tres pentagramas, la voz arriba."""
    staves = (
        _staff("P1-S1", _ts02_voice),
        _staff("P1-S2", _ts02_right_hand),
        _staff("P1-S3", _ts02_left_hand),
    )
    assert _ts02_flagged(_doc(Part(id="P1", staves=staves))) == []


def test_the_voice_alone_is_still_flagged() -> None:
    """Sin otro pentagrama que la confirme, la alteración repetida de una sola línea se sigue
    señalando: no se distingue de un becuadro que HOMR no vio (falso positivo conocido)."""
    voice = _doc(Part(id="P1", staves=(_staff("P1-S1", _ts02_voice),)))
    assert _ts02_flagged(voice) == [(0, 0, 1, 0, 2), (0, 0, 5, 0, 2), (0, 0, 8, 0, 1)]


def test_another_alteration_of_the_letter_does_not_confirm() -> None:
    """Un Fa sin alteración, o con otra, en el otro pentagrama no confirma el Fa♯ repetido."""
    numbers = range(7, 10)
    for other in ("F3", "Fb3", "F##3"):
        piano = Part(
            id="P1",
            staves=(
                _staff("P1-S1", partial(full, time=_TS02), numbers),
                _staff("P1-S2", partial(_ts02_left_hand, f_sharp=other), numbers),
            ),
        )
        voice = Part(id="P2", staves=(_staff("P2-S1", _ts02_voice, numbers),))
        assert _ts02_flagged(_doc(piano, voice)) == [(1, 0, 8, 0, 1)], other


def test_another_voice_of_the_same_staff_confirms() -> None:
    """El Fa♯3 de la voz de abajo sigue sonando cuando empieza el segundo Fa♯4."""
    doc = surrounded(
        m(
            2,
            n("F#4", BLANCA, voice=0),
            n("F#4", BLANCA, voice=0),
            n("D4", NEGRA, voice=1),
            n("F#3", BLANCA, voice=1),
            n("D4", NEGRA, voice=1),
        )
    )
    assert _flagged(doc) == []


def test_the_confirmation_is_in_the_same_measure() -> None:
    """La alteración de otro pentagrama en el compás anterior no confirma: la barra la anula."""
    upper = [full(1), m(2, n("F#4", BLANCA), n("F#4", BLANCA)), full(3)]
    lower = [m(1, n("F#3", Fraction(4))), full(2), full(3)]
    assert _flagged(document(upper, lower)) == [(2, 0, 1)]


def test_a_note_of_a_chord_does_not_fire() -> None:
    """TS-04, compás 1 de la mano derecha, en Fa mayor: el Re♭ pasa de un acorde al siguiente."""
    doc = surrounded(
        m(
            2,
            n("D4", NEGRA),
            n("F4", NEGRA, chord=True),
            n("Bb3", CORCHEA),
            n("Db4", CORCHEA, chord=True),
            n("F4", CORCHEA, chord=True),
            n("Bb3", CORCHEA),
            n("Db4", CORCHEA, chord=True),
            n("G4", CORCHEA, chord=True),
            n("A3", NEGRA),
            n("C4", NEGRA, chord=True),
            n("F4", NEGRA, chord=True),
            n("G3", CORCHEA),
            n("C4", CORCHEA, chord=True),
            n("E4", CORCHEA, chord=True),
            n("E4", CORCHEA),
            n("G4", CORCHEA, chord=True),
            fifths=-1,
        )
    )
    assert _flagged(doc) == []


def test_a_chord_after_a_single_note_is_still_flagged() -> None:
    """Solo se deja el acorde que repite la nota de otro acorde: tras una nota suelta, el Fa♯
    que empieza el acorde se sigue señalando."""
    doc = surrounded(
        m(2, n("F#4", NEGRA), n("F#4", NEGRA), n("A4", NEGRA, chord=True), n("G4", BLANCA))
    )
    assert _flagged(doc) == [(2, 0, 1)]


def test_the_same_voice_in_another_octave_does_not_confirm() -> None:
    doc = surrounded(m(2, n("F#3", NEGRA), n("F#4", NEGRA), n("F#4", NEGRA), n("G4", NEGRA)))
    assert _flagged(doc) == [(2, 0, 2)]


def test_a_note_that_has_stopped_sounding_does_not_confirm() -> None:
    """Un Fa♯ de otro pentagrama que dejó de sonar antes del repetido no lo confirma. Es la
    duplicación a la octava de Fa♯ · Fa♮ en la que HOMR no ve el becuadro de arriba."""
    upper = [full(1), m(2, n("F#4", NEGRA), n("F#4", NEGRA), n("E4", BLANCA)), full(3)]
    lower = [full(1), m(2, n("F#3", NEGRA), n("F3", NEGRA), n("E3", BLANCA)), full(3)]
    assert _flagged(document(upper, lower)) == [(2, 0, 1)]


def test_two_staves_that_repeat_together_confirm_each_other() -> None:
    """Si dos pentagramas repiten la alteración a la vez, se confirman entre sí. Así se escribe
    la alteración que vale hasta la barra en las dos manos (TS-04), y así quedaría también una
    duplicación en la que HOMR no viera ninguno de los dos becuadros: falso negativo conocido."""
    upper = [full(1), m(2, n("F#4", NEGRA), n("F#4", NEGRA), n("E4", BLANCA)), full(3)]
    lower = [full(1), m(2, n("F#3", NEGRA), n("F#3", NEGRA), n("E3", BLANCA)), full(3)]
    assert _flagged(document(upper, lower)) == []


def _ts04_right_hand(number: int) -> Measure:
    if number == 3:
        return m(
            3,
            n("A3", NEGRA),
            n("C4", NEGRA, chord=True),
            n("A4", NEGRA, chord=True),
            n("G3", CORCHEA),
            n("C4", CORCHEA, chord=True),
            n("G4", CORCHEA, chord=True),
            n("F3", CORCHEA),
            n("C4", CORCHEA, chord=True),
            n("F4", CORCHEA, chord=True),
            n("C4", NEGRA),
            n("Eb4", NEGRA, chord=True),
            n("A4", NEGRA, chord=True),
            n("Bb3", CORCHEA),
            n("Eb4", CORCHEA, chord=True),
            n("G4", CORCHEA, chord=True),
            n("A3", CORCHEA),
            n("Eb4", CORCHEA, chord=True),
            n("F4", CORCHEA, chord=True),
        )
    if number == 4:
        return m(
            4,
            n("Bb3", CORCHEA),
            n("Eb4", CORCHEA, chord=True),
            n("F4", CORCHEA, chord=True),
            n("D4", CORCHEA),
            n("F4", CORCHEA, chord=True),
            n("Bb4", CORCHEA, chord=True),
            n("C4", CORCHEA),
            n("Eb4", CORCHEA, chord=True),
            n("F#4", CORCHEA, chord=True),
            n("A4", CORCHEA, chord=True),
            n("Bb3", CORCHEA),
            n("D4", CORCHEA, chord=True),
            n("G4", CORCHEA, chord=True),
            n("C4", NEGRA),
            n("F4", NEGRA, chord=True),
            n("C4", CORCHEA),
            n("E4", CORCHEA, chord=True),
            r(CORCHEA),
        )
    return m(number, n("F4", REDONDA), fifths=-1 if number == 1 else None)


def _ts04_left_hand(number: int) -> Measure:
    if number == 3:
        return m(
            3,
            n("F2", NEGRA),
            n("C3", NEGRA, chord=True),
            n("F2", CORCHEA),
            n("Bb2", CORCHEA, chord=True),
            n("C3", CORCHEA, chord=True),
            n("F2", CORCHEA),
            n("A2", CORCHEA, chord=True),
            n("C3", CORCHEA, chord=True),
            n("F2", NEGRA),
            n("C3", NEGRA, chord=True),
            n("Eb3", NEGRA, chord=True),
            n("F3", NEGRA, chord=True),
            n("F2", CORCHEA),
            n("C3", CORCHEA, chord=True),
            n("Eb3", CORCHEA, chord=True),
            n("F3", CORCHEA, chord=True),
            n("F2", CORCHEA),
            n("C3", CORCHEA, chord=True),
            n("Eb3", CORCHEA, chord=True),
            n("F3", CORCHEA, chord=True),
        )
    if number == 4:
        return m(
            4,
            n("Eb3", CORCHEA),
            n("D3", CORCHEA),
            n("Eb3", CORCHEA),
            n("F#3", CORCHEA, chord=True),
            n("D3", CORCHEA),
            n("G3", CORCHEA, chord=True),
            n("C3", NEGRA),
            n("A3", NEGRA, chord=True),
            n("C3", CORCHEA),
            n("G3", CORCHEA, chord=True),
            r(CORCHEA),
            n("Bb2", BLANCA, voice=1),
            r(BLANCA, voice=1, hidden=True),
            n("F3", NEGRA, voice=2),
            r(BLANCA_PUNTILLO, voice=2, hidden=True),
        )
    return m(number, n("F3", REDONDA), fifths=-1 if number == 1 else None)


def test_ts04_measures_3_and_4_have_no_repeated_accidental_warning() -> None:
    """TS-04 (cc. 10-11 de la obra; compases 3 y 4 del banco), en Fa mayor: los Mi♭ pasan de un
    acorde a otro en las dos manos (seis avisos antes de #318), y el Mi♭ · Re · Mi♭ de la mano
    izquierda en el compás 4 suena a la vez que el Mi♭4 de un acorde de la derecha (uno más)."""
    numbers = range(1, 6)
    staves = (
        _staff("P1-S1", _ts04_right_hand, numbers),
        _staff("P1-S2", _ts04_left_hand, numbers),
    )
    assert _ts02_flagged(_doc(Part(id="P1", staves=staves))) == []
