"""Pruebas de la regla de balance de compás, con documentos sintéticos."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from cadenza.domain import Measure, ScoreDocument, Severity, build_anchor_index
from cadenza.omr.testing import FakeOMREngine
from cadenza.validation import MeasureBalanceRule, ValidationEngine


def _balanced(tmp_path: Path) -> ScoreDocument:
    return FakeOMREngine().transcribe(tmp_path / "score.png")


def _rebuild(document: ScoreDocument, measures: tuple[Measure, ...]) -> ScoreDocument:
    part = document.score.parts[0]
    staff = replace(part.staves[0], measures=measures)
    new_part = replace(part, staves=(staff,))
    score = replace(document.score, parts=(new_part,))
    return replace(document, score=score, anchors=build_anchor_index(score))


def _drop_last_event(document: ScoreDocument) -> ScoreDocument:
    measures = document.score.parts[0].staves[0].measures
    broken_first = replace(measures[0], events=measures[0].events[:-1])
    return _rebuild(document, (broken_first, *measures[1:]))


def test_rule_id() -> None:
    assert MeasureBalanceRule().rule_id == "measure.balance"


def test_balanced_document_has_no_findings(tmp_path: Path) -> None:
    engine = ValidationEngine([MeasureBalanceRule()])
    assert engine.validate(_balanced(tmp_path)) == []


def test_unbalanced_measure_reports_one_anchored_finding(tmp_path: Path) -> None:
    document = _drop_last_event(_balanced(tmp_path))
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
    document = _drop_last_event(_balanced(tmp_path))
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
    from fractions import Fraction

    doc = _piano_document()
    part = doc.score.parts[0]
    staff_0 = part.staves[0]
    staff_1 = part.staves[1]
    broken_m1 = replace(
        staff_1.measures[0],
        events=(replace(staff_1.measures[0].events[0], duration_beats=Fraction(2)),),
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
    assert "suma 2 negras y su métrica 4/4 exige 4" in findings[0].message


def _with_second_voice_lasting(beats: int, first_voice_beats: int = 2) -> ScoreDocument:
    """El piano con la segunda voz del compás 2 (una redonda) cambiada a ``beats`` negras y las
    dos blancas de la primera voz, a ``first_voice_beats`` negras cada una."""

    from fractions import Fraction

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
    assert "voz 1" in findings[0].message
    assert "suma 6 negras" in findings[0].message


def test_a_voice_may_end_before_the_measure_if_another_completes_it() -> None:
    """Una voz que sale a mitad del compás no es un error si otra lo completa (ADR-0032, #218):
    MusicXML no obliga a rellenarla, y las transcripciones hechas a mano no lo hacen."""

    engine = ValidationEngine([MeasureBalanceRule()])
    assert engine.validate(_with_second_voice_lasting(2)) == []


def test_short_voices_are_errors_if_no_voice_completes_the_measure() -> None:
    findings = ValidationEngine([MeasureBalanceRule()]).validate(
        _with_second_voice_lasting(2, first_voice_beats=1)
    )
    assert [(f.anchor.measure, f.anchor.voice) for f in findings] == [(2, 0), (2, 1)]
    assert all("suma 2 negras y su métrica 4/4 exige 4" in f.message for f in findings)
