"""Pruebas de la regla de balance de compás, con documentos sintéticos."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from cadenza.domain import Anchor, Measure, ScoreDocument, Severity, build_anchor_index
from cadenza.omr import FakeOMREngine
from cadenza.validation import MeasureBalanceRule, ValidationEngine

PART_STAFF_ID = "part-0-staff-0"
FIRST_EVENT_ANCHOR = Anchor(
    part=0,
    staff=0,
    measure=1,
    voice=0,
    event_index=0,
    staff_id=PART_STAFF_ID,
)


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
    assert finding.anchor == FIRST_EVENT_ANCHOR
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
