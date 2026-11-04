"""Pruebas de `time.signature`: indicación de compás (ADR-0040 §5)."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

from cadenza.domain import (
    EditOp,
    Measure,
    TimeSignature,
    snapshot_before,
    validate_after,
)
from cadenza.validation import MeasureBalanceRule, TimeSignatureRule, ValidationEngine

from packages.validation.tests.rule_builders import NEGRA, document, m, n


def _quarters(number: int, count: int, time: tuple[int, int] = (3, 4)) -> Measure:
    return m(number, *(n("C5", NEGRA) for _ in range(count)), time=time)


def _rule(*staves: list[Measure]) -> list[tuple[int, str, str | None]]:
    findings = ValidationEngine([TimeSignatureRule()]).validate(document(*staves))
    return [(f.anchor.measure, f.message, f.suggested_fix) for f in findings]


def test_rule_id() -> None:
    assert TimeSignatureRule().rule_id == "time.signature"


def test_a_tramo_with_fewer_than_two_measured_measures_never_fires() -> None:
    """Un incipit de tres compases: solo el de en medio se mide."""
    assert _rule([_quarters(1, 4), _quarters(2, 4), _quarters(3, 4)]) == []


def test_scattered_sums_are_figure_errors_left_to_measure_balance() -> None:
    measures = [_quarters(1, 3), _quarters(2, 4), _quarters(3, 2), _quarters(4, 5), _quarters(5, 3)]
    assert _rule(measures) == []


def test_measures_without_a_meter_never_fire() -> None:
    measures = [_quarters(number, 4, time=(3, 4)) for number in range(1, 6)]
    measures = [m(meas.number, *meas.events, time=None) for meas in measures]
    assert _rule(measures) == []


def test_a_sum_that_is_no_meter_never_fires() -> None:
    odd = [n("C5", Fraction(17, 8))]
    measures = [_quarters(1, 3), *(m(k, *odd, time=(3, 4)) for k in range(2, 6)), _quarters(6, 3)]
    assert _rule(measures) == []


def test_matching_measures_that_are_not_consecutive() -> None:
    measures = [
        _quarters(1, 1),
        _quarters(2, 4),
        _quarters(3, 4),
        _quarters(4, 4),
        _quarters(5, 3),
        _quarters(6, 4),
        _quarters(7, 4),
        _quarters(8, 3),
    ]
    assert _rule(measures) == [
        (
            1,
            "Cinco de los seis compases del 2 al 7 suman cuatro negras y la indicación de compás "
            "es 3/4.",
            "Revisa la indicación de compás del compás 1: puede que sea 4/4 (C). Mientras no "
            "cambie, la duración de cada compás se comprueba con cuatro negras.",
        )
    ]


def test_cut_time_is_proposed_with_its_symbol() -> None:
    half = Fraction(2)
    measures = [
        m(1, n("C5", half), time=(3, 2)),
        *(m(k, n("C5", half), n("D5", half), time=(3, 2)) for k in (2, 3, 4)),
        m(5, n("C5", half), time=(3, 2)),
    ]
    ((_, message, fix),) = _rule(measures)
    assert message == "Los compases 2 a 4 suman dos blancas y la indicación de compás es 3/2."
    assert fix is not None and fix.startswith(
        "Revisa la indicación de compás del compás 1: puede que sea 2/2 (¢)."
    )


def test_unmarked_triplets_are_not_a_time_signature_finding() -> None:
    """En un compás simple, compases que suman la métrica más su mitad en grupos de tres
    figuras iguales son tresillos sin marcar: los señala `measure.balance` (§4)."""
    eighths = [n(pitch, Fraction(1, 2)) for pitch in ("C5", "D5", "E5", "F5", "G5", "A5")]
    measures = [
        _quarters(1, 2, time=(2, 4)),
        *(m(k, *eighths, time=(2, 4)) for k in (2, 3, 4)),
        _quarters(5, 2, time=(2, 4)),
    ]
    assert _rule(measures) == []
    balance = ValidationEngine([MeasureBalanceRule()]).validate(document(measures))
    assert [f.anchor.measure for f in balance] == [2, 3, 4]
    assert all("van en grupos de tres, como los tresillos" in f.message for f in balance)


def test_several_runs_in_a_tramo_give_one_finding_each() -> None:
    measures = [
        _quarters(1, 1),
        *(_quarters(k, 3) for k in range(2, 5)),
        *(_quarters(k, 2) for k in range(5, 8)),
        *(_quarters(k, 3) for k in range(8, 10)),
        *(_quarters(k, 4) for k in range(10, 13)),
        _quarters(13, 3),
    ]
    assert [(measure, message) for measure, message, _ in _rule(measures)] == [
        (5, "Desde el compás 5, los compases suman dos negras y la indicación sigue siendo 3/4."),
        (
            10,
            "Desde el compás 10, los compases suman cuatro negras y la indicación sigue siendo "
            "3/4.",
        ),
    ]
    # Fuera de las rachas, la capacidad vuelve a ser la métrica leída.
    assert ValidationEngine([MeasureBalanceRule()]).validate(document(measures)) == []


def test_a_change_of_meter_starts_a_new_tramo() -> None:
    measures = [
        _quarters(1, 3),
        _quarters(2, 3),
        _quarters(3, 3),
        _quarters(4, 2, time=(2, 4)),
        _quarters(5, 2, time=(2, 4)),
        _quarters(6, 2, time=(2, 4)),
    ]
    assert _rule(measures) == []


def test_the_capacity_applies_to_every_staff_of_the_part_and_fires_once() -> None:
    upper = [
        _quarters(1, 1),
        _quarters(2, 4),
        _quarters(3, 4),
        m(4, n("C5", Fraction(3)), time=(3, 4)),
    ]
    lower = [
        m(1, n("C3", NEGRA), time=(3, 4)),
        m(2, n("C3", Fraction(4)), time=(3, 4)),
        m(3, n("C3", Fraction(4)), time=(3, 4)),
        m(4, n("C3", Fraction(3)), time=(3, 4)),
    ]
    findings = ValidationEngine().validate(document(upper, lower))
    assert [(f.rule_id, f.anchor.staff, f.anchor.measure) for f in findings] == [
        ("time.signature", 0, 1)
    ]


# --- Con #236: el símbolo leído y el candidato de cambiar el compás (ADR-0040, enmienda 10) ---


def _four_in_three() -> list[Measure]:
    return [_quarters(1, 1), *(_quarters(k, 4) for k in range(2, 6)), _quarters(6, 3)]


def test_the_finding_proposes_changing_the_meter_from_its_measure() -> None:
    doc = document(_four_in_three())
    (finding,) = ValidationEngine([TimeSignatureRule()]).validate(doc)
    (candidate,) = finding.candidates
    assert candidate.op is EditOp.SET_TIME
    assert candidate.anchor == finding.anchor
    assert candidate.after == {"time_signature": {"beats": 4, "beat_type": 4}}
    # Es una edición que el servidor admite: cambia el compás de todo el tramo.
    validate_after(doc.score, candidate.anchor, candidate.op, candidate.after)
    assert snapshot_before(doc.score, candidate.anchor, candidate.op, candidate.after) == {
        "time_signature": {"beats": 3, "beat_type": 4},
        "measures": 6,
    }


def test_a_read_symbol_is_named_as_it_is_written() -> None:
    measures = [
        _quarters(1, 1, time=(4, 4)),
        *(_quarters(k, 3, time=(4, 4)) for k in range(2, 6)),
        _quarters(6, 4, time=(4, 4)),
    ]
    common = TimeSignature(4, 4, "common")
    measures = [replace(meas, time_signature=common) for meas in measures]
    ((_, message, fix),) = _rule(measures)
    assert message == "Los compases 2 a 5 suman tres negras y la indicación de compás es C."
    assert fix is not None and fix.startswith(
        "Revisa la indicación de compás del compás 1: puede que sea 3/4."
    )


def test_the_candidate_is_described_in_musical_language() -> None:
    from cadenza.validation.learned import describe_edit

    after = {"time_signature": {"beats": 4, "beat_type": 4, "symbol": "common"}}
    assert describe_edit(EditOp.SET_TIME, after, None) == (
        "Cambiar la indicación de compás a C desde este compás."
    )
    assert describe_edit(EditOp.SET_TIME, {"time_signature": None}, None) == (
        "Quitar el cambio de compás de este compás."
    )


def test_a_run_proposes_the_meter_only_for_its_measures() -> None:
    measures = [
        _quarters(1, 1),
        *(_quarters(k, 3) for k in range(2, 5)),
        *(_quarters(k, 2) for k in range(5, 8)),
        *(_quarters(k, 3) for k in range(8, 10)),
    ]
    doc = document(measures)
    (finding,) = ValidationEngine([TimeSignatureRule()]).validate(doc)
    (candidate,) = finding.candidates
    assert candidate.after == {"time_signature": {"beats": 2, "beat_type": 4}, "measures": 3}
    validate_after(doc.score, candidate.anchor, candidate.op, candidate.after)
