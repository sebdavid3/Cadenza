"""Casos límite del catálogo encontrados en la revisión de #246 (ADR-0040)."""

from __future__ import annotations

from fractions import Fraction

from cadenza.domain import Event, EventKind, Finding, ScoreDocument, Tie, TimeSignature
from cadenza.validation import (
    KeyConsistencyRule,
    TieResolutionRule,
    TupletIncompleteRule,
    ValidationEngine,
    VoiceCollisionRule,
)
from cadenza.validation.language import position_phrase

from packages.validation.tests.rule_builders import (
    CORCHEA_TRESILLO,
    NEGRA,
    REDONDA,
    document,
    full,
    m,
    n,
    r,
    surrounded,
)


def _rules(doc: ScoreDocument) -> list[tuple[str, int, int]]:
    return [(f.rule_id, f.anchor.staff, f.anchor.measure) for f in ValidationEngine().validate(doc)]


def test_whole_rest_measures_are_not_a_time_signature_finding() -> None:
    """Un silencio de redonda es un silencio de compás en cualquier métrica (§4.3): no suma
    cuatro negras para `time.signature`."""
    three = [n(p, NEGRA) for p in ("C5", "D5", "E5")]
    doc = document(
        [
            m(1, *three, time=(3, 4)),
            *(m(k, r(REDONDA), time=(3, 4)) for k in (2, 3, 4)),
            m(5, *three, time=(3, 4)),
            m(6, *three, time=(3, 4)),
        ]
    )
    assert _rules(doc) == []


def test_a_resting_right_hand_does_not_change_the_capacity_of_the_left_hand() -> None:
    three = [n(p, NEGRA) for p in ("C3", "D3", "E3")]
    upper = [m(k, r(REDONDA), time=(3, 4)) for k in range(1, 6)]
    lower = [m(k, *three, time=(3, 4)) for k in range(1, 6)]
    assert _rules(document(upper, lower)) == []


def test_a_tie_into_a_rest_with_its_end_mark_is_flagged_once() -> None:
    doc = document(
        [
            full(1),
            m(2, n("C4", Fraction(2), tie=Tie.START), r(Fraction(2), tie=Tie.STOP)),
            full(3),
        ]
    )
    findings = ValidationEngine([TieResolutionRule()]).validate(doc)
    assert [f.message for f in findings] == [
        "La ligadura del Do del tiempo 1 no llega a otro Do: lo siguiente es un silencio."
    ]


def test_an_incomplete_tuplet_is_anchored_to_what_is_seen() -> None:
    events = (
        r(CORCHEA_TRESILLO, hidden=True),
        n("C5", CORCHEA_TRESILLO),
        n("E5", NEGRA),
    )
    doc = surrounded(m(2, *events, time=(2, 4)), time=(2, 4))
    (finding,) = ValidationEngine([TupletIncompleteRule()]).validate(doc)
    assert finding.anchor.event_index == 1


def test_positions_in_compound_meters_use_thirds_and_sixths_of_the_beat() -> None:
    six_eight = TimeSignature(6, 8)
    assert str(position_phrase(Fraction(3, 4), six_eight)) == "la cuarta semicorchea del tiempo 1"
    assert str(position_phrase(Fraction(1, 4), six_eight)) == "la segunda semicorchea del tiempo 1"
    assert str(position_phrase(Fraction(1), six_eight)) == "la tercera corchea del tiempo 1"


def test_the_natural_sign_is_named_against_the_key_in_every_rule() -> None:
    """En Re mayor, un Fa natural es «Fa♮» en todos los mensajes (§1)."""
    chord = (
        n("D4", NEGRA),
        Event(kind=EventKind.NOTE, pitch="F4", duration_beats=Fraction(1, 2), is_chord=True),
        n("A4", Fraction(3)),
    )
    collision = surrounded(m(2, *chord, fifths=2))
    (finding,) = ValidationEngine([VoiceCollisionRule()]).validate(collision)
    assert (
        finding.message == "En el acorde del tiempo 1, el Fa♮ es una corchea y el Re es una negra."
    )
    tie = document(
        [
            m(1, n("D4", REDONDA), fifths=2),
            m(2, n("F4", Fraction(2), tie=Tie.START), n("G4", Fraction(2))),
            full(3),
        ]
    )
    (finding,) = ValidationEngine([TieResolutionRule()]).validate(tie)
    assert finding.message.startswith("La ligadura del Fa♮ del tiempo 1 no llega a otro Fa♮")


def test_a_chord_on_a_grace_note_is_not_a_figure_mismatch() -> None:
    chord = (
        n("D4", Fraction(0)),
        Event(kind=EventKind.NOTE, pitch="F4", duration_beats=Fraction(0), is_chord=True),
        n("A4", REDONDA),
    )
    findings: list[Finding] = VoiceCollisionRule().evaluate(surrounded(m(2, *chord)))
    assert findings == []


def test_a_discrepancy_that_changes_value_is_still_one_stretch() -> None:
    upper = [m(1, n("D5", REDONDA), fifths=2), m(2, n("D5", REDONDA), fifths=3)]
    lower = [m(1, n("D3", REDONDA), fifths=1), m(2, n("D3", REDONDA))]
    findings = ValidationEngine([KeyConsistencyRule()]).validate(document(upper, lower))
    assert [f.anchor.measure for f in findings] == [1]


def test_time_signature_is_anchored_to_the_first_measure_with_something_seen() -> None:
    four = [n(p, NEGRA) for p in ("C5", "D5", "E5", "F5")]
    doc = document(
        [
            m(1, r(NEGRA, hidden=True), time=(3, 4)),
            m(2, *four, time=(3, 4)),
            m(3, *four, time=(3, 4)),
            m(4, n("C5", Fraction(3)), time=(3, 4)),
        ]
    )
    findings = [f for f in ValidationEngine().validate(doc) if f.rule_id == "time.signature"]
    assert [f.anchor.measure for f in findings] == [2]
    assert findings[0].suggested_fix is not None
    assert findings[0].suggested_fix.startswith("Revisa la indicación de compás del compás 2")
