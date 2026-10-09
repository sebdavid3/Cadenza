"""Pruebas unitarias de las métricas de evaluación del validador (ADR-0008, Issue #18, D8)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest
from cadenza.domain import (
    Anchor,
    Clef,
    EditEvent,
    EditOp,
    Event,
    EventKind,
    Finding,
    KeySignature,
    Measure,
    Part,
    ScoreIR,
    Severity,
    Staff,
    TimeSignature,
)
from cadenza.learning import (
    MeasureEvaluationRecord,
    aggregate_validation_metrics,
    categorize_edit_op,
    compute_binary_metrics,
    evaluate_score_measures,
)


def _make_score(measures: list[Measure]) -> ScoreIR:
    staff = Staff(id="part-0-staff-0", measures=tuple(measures))
    return ScoreIR(parts=(Part(id="part-0", staves=(staff,)),))


def _make_measure(number: int, events: list[Event], duration_beats: int = 4) -> Measure:
    return Measure(
        number=number,
        events=tuple(events),
        clef=Clef.treble(),
        key_signature=KeySignature(fifths=0),
        time_signature=TimeSignature(duration_beats, 4),
    )


def _note(pitch: str, duration: int = 1) -> Event:
    return Event(
        kind=EventKind.NOTE,
        voice=0,
        pitch=pitch,
        duration_beats=Fraction(duration),
    )


# ============================================================================
# 1. Pruebas de métricas binarias
# ============================================================================


def test_binary_metrics_calculations() -> None:
    # TP=8, FP=2, FN=2, TN=8 -> Precision=8/10=0.8, Recall=8/10=0.8, F1=0.8
    m = compute_binary_metrics(tp=8, fp=2, fn=2, tn=8)
    assert m.total == 20
    assert m.precision == 0.8
    assert m.recall == 0.8
    assert m.f1 == 0.8
    assert m.accuracy == 0.8
    assert m.specificity == 0.8

    d = m.to_dict()
    assert d["tp"] == 8
    assert d["precision"] == 0.8


def test_binary_metrics_zero_denominators() -> None:
    m = compute_binary_metrics(tp=0, fp=0, fn=0, tn=0)
    assert m.precision == 0.0
    assert m.recall == 0.0
    assert m.f1 == 0.0
    assert m.accuracy == 0.0
    assert m.specificity == 0.0


# ============================================================================
# 2. Pruebas de categorización de operaciones
# ============================================================================


def test_categorize_edit_op() -> None:
    assert categorize_edit_op(EditOp.SET_DURATION) == "duration"
    assert categorize_edit_op(EditOp.SET_ACCIDENTAL) == "accidental"
    assert categorize_edit_op(EditOp.SET_PITCH) == "pitch"
    assert categorize_edit_op(EditOp.INSERT_EVENT) == "structure"
    assert categorize_edit_op(EditOp.DELETE_EVENT) == "structure"
    assert categorize_edit_op(EditOp.SET_KEY) == "key_clef"
    assert categorize_edit_op(EditOp.SET_CLEF) == "key_clef"
    assert categorize_edit_op("custom") == "other"


# ============================================================================
# 3. Pruebas de evaluación compás a compás
# ============================================================================


def test_evaluate_score_measures() -> None:
    m1 = _make_measure(1, [_note("C4", 1), _note("D4", 1)])
    m2 = _make_measure(2, [_note("E4", 2)])
    score = _make_score([m1, m2])

    anchor_m1 = Anchor(
        part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="part-0-staff-0"
    )

    # M1 tiene un error real de duración y un hallazgo de balance (TP)
    edits = [
        EditEvent(
            id="e1",
            document_id="doc-1",
            seq=1,
            anchor=anchor_m1,
            op=EditOp.SET_DURATION,
            author="tester",
            created_at=pytest.importorskip("datetime").datetime.now(
                pytest.importorskip("datetime").UTC
            ),
        )
    ]
    findings = [
        Finding(
            anchor=anchor_m1,
            rule_id="measure.balance",
            severity=Severity.ERROR,
            message="desbalance",
        )
    ]

    records = evaluate_score_measures("doc-1", score, findings, edits)
    assert len(records) == 2

    r1 = records[0]
    assert r1.measure_number == 1
    assert r1.has_real_error is True
    assert "duration" in r1.error_categories
    assert r1.flagged_global is True
    assert "measure.balance" in r1.flagged_rules

    r2 = records[1]
    assert r2.measure_number == 2
    assert r2.has_real_error is False
    assert r2.flagged_global is False


# ============================================================================
# 4. Pruebas de agregación de métricas y cobertura
# ============================================================================


def test_aggregate_validation_metrics() -> None:
    records = [
        # TP
        MeasureEvaluationRecord(
            score_id="s1",
            part_index=0,
            staff_index=0,
            measure_number=1,
            has_real_error=True,
            error_operations=("SetDuration",),
            error_categories=("duration",),
            flagged_global=True,
            flagged_rules=("measure.balance",),
        ),
        # FP
        MeasureEvaluationRecord(
            score_id="s1",
            part_index=0,
            staff_index=0,
            measure_number=2,
            has_real_error=False,
            error_operations=(),
            error_categories=(),
            flagged_global=True,
            flagged_rules=("measure.balance",),
        ),
        # FN
        MeasureEvaluationRecord(
            score_id="s1",
            part_index=0,
            staff_index=0,
            measure_number=3,
            has_real_error=True,
            error_operations=("SetPitch",),
            error_categories=("pitch",),
            flagged_global=False,
            flagged_rules=(),
        ),
        # TN
        MeasureEvaluationRecord(
            score_id="s1",
            part_index=0,
            staff_index=0,
            measure_number=4,
            has_real_error=False,
            error_operations=(),
            error_categories=(),
            flagged_global=False,
            flagged_rules=(),
        ),
    ]

    report = aggregate_validation_metrics(records, known_rules=["measure.balance", "pitch.range"])
    assert report.total_scores == 1
    assert report.total_measures == 4
    assert report.measures_with_real_errors == 2
    assert report.measures_flagged == 2

    # Global: TP=1, FP=1, FN=1, TN=1 -> P=0.5, R=0.5, F1=0.5
    assert report.global_metrics.tp == 1
    assert report.global_metrics.fp == 1
    assert report.global_metrics.fn == 1
    assert report.global_metrics.tn == 1
    assert report.global_metrics.precision == 0.5
    assert report.global_metrics.recall == 0.5
    assert report.global_metrics.f1 == 0.5

    # Regla measure.balance
    assert "measure.balance" in report.metrics_by_rule
    mb = report.metrics_by_rule["measure.balance"]
    assert mb.tp == 1
    assert mb.fp == 1

    # Regla pitch.range (sin flags)
    assert "pitch.range" in report.metrics_by_rule
    pr = report.metrics_by_rule["pitch.range"]
    assert pr.tp == 0
    assert pr.fp == 0

    # Cobertura por categoría
    assert "duration" in report.coverage_by_category
    assert report.coverage_by_category["duration"].coverage_rate == 1.0
    assert report.coverage_by_category["pitch"].coverage_rate == 0.0

    d = report.to_dict()
    assert d["total_measures"] == 4
    assert "what_catalog_covers" in d["coverage_analysis"]


# ============================================================================
# 5. Smoke test sobre par real de PrIMuS si está disponible
# ============================================================================


def test_evaluate_pair_primus_smoke() -> None:
    pred_path = Path("data/primus/predictions/000051650-1_1_1.musicxml")
    gt_path = Path("data/primus/package_aa/000051650-1_1_1/000051650-1_1_1.mei")

    if not pred_path.is_file() or not gt_path.is_file():
        pytest.skip("Corpus PrIMuS no disponible localmente")

    from cadenza.interchange import read_score
    from cadenza.learning import evaluate_pair
    from cadenza.validation import ValidationEngine

    score_pred = read_score(pred_path)
    score_gt = read_score(gt_path)
    validator = ValidationEngine()

    records = evaluate_pair("000051650-1_1_1", score_pred, score_gt, validator)
    assert len(records) > 0
    report = aggregate_validation_metrics(records)
    assert report.total_measures == len(records)
