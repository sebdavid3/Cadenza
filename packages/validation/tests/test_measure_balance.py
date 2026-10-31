"""Pruebas de la regla de balance de compás, con documentos sintéticos."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from pathlib import Path

from cadenza.domain import Measure, ScoreDocument, Severity, build_anchor_index
from cadenza.omr.testing import FakeOMREngine
from cadenza.validation import MeasureBalanceRule, ValidationEngine

from packages.validation.tests.rule_builders import document, full, m, n, r, surrounded


def _balanced(tmp_path: Path) -> ScoreDocument:
    return FakeOMREngine().transcribe(tmp_path / "score.png")


def _rebuild(document: ScoreDocument, measures: tuple[Measure, ...]) -> ScoreDocument:
    part = document.score.parts[0]
    staff = replace(part.staves[0], measures=measures)
    new_part = replace(part, staves=(staff,))
    score = replace(document.score, parts=(new_part,))
    return replace(document, score=score, anchors=build_anchor_index(score))


def _lengthen_last_event(document: ScoreDocument) -> ScoreDocument:
    """El silencio de blanca del primer compás, leído como redonda: el compás se pasa.

    Un primer compás corto no sirve: es la anacrusa, que no se señala (ADR-0040 §4).
    """
    measures = document.score.parts[0].staves[0].measures
    events = measures[0].events
    longer = replace(events[-1], duration_beats=Fraction(4))
    broken_first = replace(measures[0], events=(*events[:-1], longer))
    return _rebuild(document, (broken_first, *measures[1:]))


def test_rule_id() -> None:
    assert MeasureBalanceRule().rule_id == "measure.balance"


def test_balanced_document_has_no_findings(tmp_path: Path) -> None:
    engine = ValidationEngine([MeasureBalanceRule()])
    assert engine.validate(_balanced(tmp_path)) == []


def test_unbalanced_measure_reports_one_anchored_finding(tmp_path: Path) -> None:
    document = _lengthen_last_event(_balanced(tmp_path))
    findings = ValidationEngine([MeasureBalanceRule()]).validate(document)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == "measure.balance"
    assert finding.severity is Severity.ERROR
    assert finding.anchor == document.anchors.anchors()[0]
    assert finding.anchor.measure == 1
    assert finding.anchor.bbox is not None
    assert finding.suggested_fix is not None


def test_measure_without_meter_is_skipped(tmp_path: Path) -> None:
    document = _balanced(tmp_path)
    measures = document.score.parts[0].staves[0].measures
    without_meter = replace(measures[0], time_signature=None, events=measures[0].events[:-1])
    document = _rebuild(document, (without_meter, *measures[1:]))
    assert ValidationEngine([MeasureBalanceRule()]).validate(document) == []


def test_rule_does_not_mutate_document(tmp_path: Path) -> None:
    document = _lengthen_last_event(_balanced(tmp_path))
    snapshot = document
    ValidationEngine([MeasureBalanceRule()]).validate(document)
    assert document == snapshot


PIANO_FIXTURE = Path(__file__).parent / "fixtures" / "piano.musicxml"


def _piano_document() -> ScoreDocument:
    from cadenza.domain import Provenance
    from cadenza.interchange import read_score

    score = read_score(PIANO_FIXTURE)
    return ScoreDocument(
        id="piano-doc-1",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="fake", model_version="1.0"),
    )


def test_piano_balanced_document_has_no_findings() -> None:
    engine = ValidationEngine([MeasureBalanceRule()])
    doc = _piano_document()
    assert engine.validate(doc) == []


def test_piano_unbalanced_bass_staff_reports_finding_on_staff_1() -> None:
    doc = _piano_document()
    part = doc.score.parts[0]
    staff_0 = part.staves[0]
    staff_1 = part.staves[1]
    broken_m1 = replace(
        staff_1.measures[0],
        events=(replace(staff_1.measures[0].events[0], duration_beats=Fraction(6)),),
    )
    new_staff_1 = replace(staff_1, measures=(broken_m1, staff_1.measures[1]))
    new_part = replace(part, staves=(staff_0, new_staff_1))
    new_score = replace(doc.score, parts=(new_part,))
    broken_doc = replace(doc, score=new_score, anchors=build_anchor_index(new_score))

    engine = ValidationEngine([MeasureBalanceRule()])
    findings = engine.validate(broken_doc)
    assert len(findings) == 1
    assert findings[0].anchor.staff == 1
    assert findings[0].anchor.measure == 1
    assert findings[0].message.startswith("En el compás 1 sobra una blanca para el 4/4: ")


def _with_second_voice_lasting(beats: int, first_voice_beats: int = 2) -> ScoreDocument:
    """El piano con la segunda voz del compás 2 (una redonda) cambiada a ``beats`` negras y las
    dos blancas de la primera voz, a ``first_voice_beats`` negras cada una."""

    doc = _piano_document()
    part = doc.score.parts[0]
    staff_0 = part.staves[0]
    m2_events = [
        replace(
            event,
            duration_beats=Fraction(beats if event.voice == 1 else first_voice_beats),
        )
        for event in staff_0.measures[1].events
    ]
    broken_m2 = replace(staff_0.measures[1], events=tuple(m2_events))
    new_staff_0 = replace(staff_0, measures=(staff_0.measures[0], broken_m2))
    new_part = replace(part, staves=(new_staff_0, part.staves[1]))
    new_score = replace(doc.score, parts=(new_part,))
    return replace(doc, score=new_score, anchors=build_anchor_index(new_score))


def test_piano_voice_that_overflows_a_polyphonic_measure() -> None:
    findings = ValidationEngine([MeasureBalanceRule()]).validate(_with_second_voice_lasting(6))
    assert len(findings) == 1
    assert findings[0].anchor.staff == 0
    assert findings[0].anchor.measure == 2
    assert findings[0].anchor.voice == 1
    # La voz se nombra por su altura, no por su índice interno (ADR-0040 §1).
    assert findings[0].message.startswith(
        "En el compás 2, a la voz de abajo le sobra una blanca para el 4/4: "
    )


def test_a_voice_may_end_before_the_measure_if_another_completes_it() -> None:
    """Una voz que sale a mitad del compás no es un error si otra lo completa (ADR-0032, #218):
    MusicXML no obliga a rellenarla, y las transcripciones hechas a mano no lo hacen."""

    engine = ValidationEngine([MeasureBalanceRule()])
    assert engine.validate(_with_second_voice_lasting(2)) == []


def test_a_voice_of_hidden_rests_does_not_complete_the_measure() -> None:
    """Un silencio de redonda invisible (Finale, OpenScore) no completa el compás: la voz que se
    ve y se queda corta sigue siendo un error."""

    from cadenza.domain import Event, EventKind

    doc = _piano_document()
    part = doc.score.parts[0]
    staff_0 = part.staves[0]
    events = (
        *(
            Event(kind=EventKind.NOTE, voice=0, pitch=p, duration_beats=Fraction(1))
            for p in ("C4", "D4", "E4")
        ),
        Event(kind=EventKind.REST, voice=1, duration_beats=Fraction(4), hidden=True),
    )
    broken_m2 = replace(staff_0.measures[1], events=events)
    new_staff_0 = replace(staff_0, measures=(staff_0.measures[0], broken_m2))
    new_score = replace(doc.score, parts=(replace(part, staves=(new_staff_0, part.staves[1])),))
    broken_doc = replace(doc, score=new_score, anchors=build_anchor_index(new_score))

    findings = ValidationEngine([MeasureBalanceRule()]).validate(broken_doc)
    assert [(f.anchor.measure, f.anchor.voice) for f in findings] == [(2, 0)]


def test_short_voices_are_errors_if_no_voice_completes_the_measure() -> None:
    findings = ValidationEngine([MeasureBalanceRule()]).validate(
        _with_second_voice_lasting(2, first_voice_beats=1)
    )
    assert [(f.anchor.measure, f.anchor.voice) for f in findings] == [(2, 0), (2, 1)]
    assert [f.message for f in findings] == [
        "En el compás 2, a la voz de arriba le falta una blanca para completar el 4/4: sus "
        "figuras se acaban antes del tiempo 3.",
        "En el compás 2, a la voz de abajo le falta una blanca para completar el 4/4: sus "
        "figuras se acaban antes del tiempo 3.",
    ]


# --- ADR-0040 §4 ----------------------------------------------------------------------------


def test_a_voice_of_only_hidden_rests_is_never_flagged() -> None:
    """No se ve: antes se señalaba si ninguna voz completaba el compás."""
    doc = surrounded(m(2, n("C4", Fraction(4)), r(Fraction(2), voice=1, hidden=True)))
    assert ValidationEngine([MeasureBalanceRule()]).validate(doc) == []


def test_a_short_last_measure_without_an_upbeat_is_flagged() -> None:
    """En una página del estudio el último compás suele estar completo (ADR-0040 §4.2)."""
    doc = document([full(1), full(2), m(3, n("C4", Fraction(2)))])
    findings = ValidationEngine([MeasureBalanceRule()]).validate(doc)
    assert [(f.anchor.measure, f.message) for f in findings] == [
        (
            3,
            "Al compás 3 le falta una blanca para completar el 4/4: las figuras se acaban "
            "antes del tiempo 3.",
        )
    ]


def test_an_overflowing_upbeat_is_flagged() -> None:
    doc = document([m(1, n("C4", Fraction(4)), n("D4", Fraction(1))), full(2), full(3)])
    (finding,) = ValidationEngine([MeasureBalanceRule()]).validate(doc)
    assert finding.message == (
        "En el compás 1 sobra una negra para el 4/4: el compás ya está lleno cuando llega el Re."
    )


def test_a_grace_rest_counts_as_a_quarter_and_grace_notes_count_nothing() -> None:
    """ADR-0028 §2: un silencio sin duración se exporta como negra; la nota es de adorno."""
    balanced = surrounded(m(2, n("G#4", Fraction(0)), n("A4", Fraction(3)), r(None)))
    assert ValidationEngine([MeasureBalanceRule()]).validate(balanced) == []


def test_an_amount_that_is_no_figure_is_not_said() -> None:
    doc = surrounded(m(2, n("C4", Fraction(2)), n("D4", Fraction(5, 8))))
    (finding,) = ValidationEngine([MeasureBalanceRule()]).validate(doc)
    assert finding.message.startswith("Al compás 2 le falta duración para completar el 4/4: ")
    assert finding.suggested_fix == (
        "Revisa las figuras del compás: puede que alguna sea más larga de lo que se leyó."
    )


def test_a_measure_in_a_time_signature_span_is_checked_against_its_sum() -> None:
    """En los compases de un hallazgo de `time.signature`, la capacidad es la suma que da
    (ADR-0040 §4 y §5), y la métrica se nombra como lo que suman."""
    four = [n(p, Fraction(1)) for p in ("C5", "D5", "E5", "F5")]
    doc = document(
        [
            m(1, n("D4", Fraction(1)), time=(3, 4)),
            m(2, *four, time=(3, 4)),
            m(3, *four, time=(3, 4)),
            m(4, n("C5", Fraction(1)), n("D5", Fraction(2)), time=(3, 4)),
            m(5, *four, time=(3, 4)),
            m(6, n("C5", Fraction(3)), time=(3, 4)),
        ]
    )
    (finding,) = ValidationEngine([MeasureBalanceRule()]).validate(doc)
    assert finding.anchor.measure == 4
    assert finding.message == (
        "Al compás 4 le falta una negra para completar las cuatro negras que suman los demás "
        "compases: las figuras se acaban antes del tiempo 4."
    )


def test_a_short_voice_explained_by_an_incomplete_tuplet_is_left_to_the_tuplet() -> None:
    third = Fraction(1, 3)
    doc = surrounded(m(2, n("C5", third), n("D5", third), n("E5", Fraction(3))))
    assert ValidationEngine([MeasureBalanceRule()]).validate(doc) == []
