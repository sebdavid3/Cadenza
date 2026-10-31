"""Pruebas de `accidental.repeated`: alteración repetida (ADR-0040 §7)."""

from __future__ import annotations

from fractions import Fraction

from cadenza.domain import EditOp, Event, EventKind, ScoreDocument, validate_after
from cadenza.validation import AccidentalRepeatedRule, ValidationEngine

from packages.validation.tests.rule_builders import BLANCA, NEGRA, document, full, m, n, surrounded


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
