"""La sugerencia estructurada (`SuggestedEdit`) y los candidatos de un hallazgo (ADR-0036 §4)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from cadenza.domain import (
    Anchor,
    EditEvent,
    EditOp,
    Finding,
    Provenance,
    Severity,
    SuggestedEdit,
    SuggestedFinding,
    SuggestionResult,
    translate_finding,
)


def _anchor(index: int = 0) -> Anchor:
    return Anchor(part=0, staff=0, measure=1, voice=0, event_index=index, staff_id="P1-S1")


def _suggestion(**overrides: object) -> SuggestedEdit:
    values: dict[str, object] = {
        "op": EditOp.SET_ACCIDENTAL,
        "anchor": _anchor(1),
        "after": {"accidental": "b"},
        "confidence": 0.82,
        "confidence_level": "high",
        "explanation": "Puede que este Si sea Si♭: la armadura lo pide.",
        "source": "learned",
        "model_version": "sug-1",
    }
    values.update(overrides)
    return SuggestedEdit(**values)  # type: ignore[arg-type]


def test_suggested_edit_is_frozen_and_hashable() -> None:
    suggestion = _suggestion()
    with pytest.raises(FrozenInstanceError):
        suggestion.confidence = 0.1  # type: ignore[misc]
    with pytest.raises(TypeError):
        suggestion.after["accidental"] = "#"  # type: ignore[index]
    assert hash(suggestion) == hash(_suggestion())
    assert suggestion == _suggestion()


def test_suggested_edit_roundtrip() -> None:
    suggestion = _suggestion(before={"accidental": ""})
    assert SuggestedEdit.from_primitive(suggestion.to_primitive()) == suggestion


@pytest.mark.parametrize(
    ("field", "value"),
    [("confidence", 1.5), ("confidence_level", "low"), ("source", "oracle")],
)
def test_suggested_edit_rejects_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        _suggestion(**{field: value})


def test_finding_candidates_default_to_empty_and_are_not_serialized() -> None:
    finding = Finding(
        anchor=_anchor(), rule_id="measure.balance", severity=Severity.ERROR, message="m"
    )
    assert finding.candidates == ()
    assert "candidates" not in finding.to_primitive()
    assert Finding.from_primitive(finding.to_primitive()) == finding


def test_finding_with_candidates_roundtrips_and_hashes() -> None:
    finding = Finding(
        anchor=_anchor(),
        rule_id="measure.balance",
        severity=Severity.ERROR,
        message="m",
        candidates=(_suggestion(source="rule", confidence=None, confidence_level=None),),
    )
    assert Finding.from_primitive(finding.to_primitive()) == finding
    assert hash(finding) == hash(Finding.from_primitive(finding.to_primitive()))


def test_translate_finding_translates_its_candidates() -> None:
    finding = Finding(
        anchor=_anchor(2),
        rule_id="measure.balance",
        severity=Severity.ERROR,
        message="m",
        candidates=(_suggestion(anchor=_anchor(2)),),
    )
    deletion = EditEvent(
        id="e1",
        document_id="d",
        seq=1,
        anchor=_anchor(0),
        op=EditOp.DELETE_EVENT,
        author="a",
        created_at=datetime(2026, 10, 30, tzinfo=UTC),
        before={"kind": "note", "pitch": "C4", "duration_beats": "1"},
    )
    translated = translate_finding(finding, 1, [deletion])
    assert translated is not None
    assert translated.anchor.event_index == 1
    assert [c.anchor.event_index for c in translated.candidates] == [1]


def test_suggestion_result_pairs_findings_with_their_suggestions() -> None:
    finding = Finding(anchor=_anchor(), rule_id="r", severity=Severity.ERROR, message="m")
    result = SuggestionResult(findings=(SuggestedFinding(finding, (_suggestion(),)),))
    assert result.findings[0].finding is finding
    assert result.findings[0].suggestions[0].op is EditOp.SET_ACCIDENTAL


def test_provenance_suggestions_version_is_optional_and_backwards_compatible() -> None:
    old = Provenance(omr_engine="homr").to_primitive()
    assert "suggestions_version" not in old
    assert Provenance.from_primitive(old).suggestions_version is None
    new = Provenance(omr_engine="homr", suggestions_version="sug-1")
    assert Provenance.from_primitive(new.to_primitive()) == new
