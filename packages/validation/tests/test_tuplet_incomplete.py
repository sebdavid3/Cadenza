"""Pruebas de `tuplet.incomplete`: tresillo incompleto (ADR-0040 §6)."""

from __future__ import annotations

from fractions import Fraction

from cadenza.domain import Event, EventKind
from cadenza.validation import TupletIncompleteRule, ValidationEngine

from packages.validation.tests.rule_builders import CORCHEA_TRESILLO, NEGRA, m, n, r, surrounded

NEGRA_TRESILLO = Fraction(2, 3)
SEMICORCHEA_TRESILLO = Fraction(1, 6)


def _rule(*events: Event, time: tuple[int, int] = (2, 4)) -> list[tuple[int, str, str | None]]:
    doc = surrounded(m(2, *events, time=time), time=time)
    findings = ValidationEngine([TupletIncompleteRule()]).validate(doc)
    return [(f.anchor.event_index, f.message, f.suggested_fix) for f in findings]


def test_rule_id() -> None:
    assert TupletIncompleteRule().rule_id == "tuplet.incomplete"


def test_complete_groups_do_not_fire_even_mixing_figures() -> None:
    assert _rule(n("C5", NEGRA_TRESILLO), n("D5", CORCHEA_TRESILLO), n("E5", NEGRA)) == []


def test_two_complete_triplets_in_a_row_do_not_fire() -> None:
    six = [n("C5", CORCHEA_TRESILLO) for _ in range(6)]
    assert _rule(*six) == []


def test_two_missing_units() -> None:
    assert _rule(n("C5", CORCHEA_TRESILLO), r(Fraction(1, 2)), n("D5", NEGRA)) == [
        (
            0,
            "En el compás 2, al tresillo de corcheas del tiempo 1 le faltan dos corcheas.",
            "Revisa el tresillo: puede que falten dos notas o que sobre una.",
        )
    ]


def test_the_place_is_where_the_group_starts() -> None:
    found = _rule(
        n("C5", Fraction(1, 2)),
        n("D5", SEMICORCHEA_TRESILLO),
        n("E5", SEMICORCHEA_TRESILLO),
        n("F5", NEGRA),
        n("G5", Fraction(1, 6)),
    )
    assert found[0][1] == (
        "En el compás 2, al tresillo de semicorcheas de la segunda corchea del tiempo 1 le "
        "falta una semicorchea."
    )


def test_quintuplets_are_not_triplets() -> None:
    five = [n("C5", Fraction(1, 5)) for _ in range(4)]
    assert _rule(*five, n("D5", Fraction(6, 5))) == []


def test_chord_notes_and_grace_notes_do_not_count() -> None:
    chord_note = Event(
        kind=EventKind.NOTE, pitch="E5", duration_beats=CORCHEA_TRESILLO, is_chord=True
    )
    grace = n("B4", Fraction(0))
    assert (
        _rule(
            n("C5", CORCHEA_TRESILLO),
            chord_note,
            grace,
            n("D5", CORCHEA_TRESILLO),
            n("E5", CORCHEA_TRESILLO),
            n("F5", NEGRA),
        )
        == []
    )
