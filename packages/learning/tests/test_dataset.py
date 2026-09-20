"""Pruebas del `DatasetBuilder` (alineación por ancla y features)."""

from __future__ import annotations

from cadenza.domain import EditOp
from cadenza.learning import DatasetBuilder

from .support import make_anchor, make_document, make_edit, make_finding


def test_builds_samples_with_magnitude_and_error_density() -> None:
    document = make_document()
    edits = [
        make_edit(1, make_anchor(0), "C4", "D4"),
        make_edit(2, make_anchor(1), "D4", "F4"),
    ]
    findings = [make_finding(make_anchor(0))]

    samples = DatasetBuilder().build(document, edits, findings)

    assert len(samples) == 2
    first, second = samples
    assert first.before_pitch == "C4"
    assert first.after_pitch == "D4"
    assert first.correction_magnitude == 2.0
    assert first.error_density == 0.5  # 1 finding / 2 eventos del compás
    assert second.correction_magnitude == 3.0
    assert second.error_density == 0.5


def test_ignores_non_pitch_edits_and_other_documents() -> None:
    document = make_document()
    edits = [
        make_edit(1, make_anchor(0), "C4", "D4", op=EditOp.SET_DURATION),
        make_edit(2, make_anchor(0), "C4", "D4", document_id="other"),
        make_edit(3, make_anchor(0), "C4", "D4"),
    ]

    samples = DatasetBuilder().build(document, edits)

    assert [sample.document_id for sample in samples] == ["doc-1"]


def test_build_is_deterministic() -> None:
    document = make_document()
    edits = [make_edit(1, make_anchor(0), "C4", "D4")]
    builder = DatasetBuilder()
    assert builder.build(document, edits) == builder.build(document, edits)
