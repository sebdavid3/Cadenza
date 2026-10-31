"""Pruebas del motor de validación (aplanado, orden, catálogo y solo lectura)."""

from __future__ import annotations

from pathlib import Path

from cadenza.domain import Finding, ScoreDocument, Severity
from cadenza.omr.testing import FakeOMREngine
from cadenza.validation import (
    DEFAULT_RULES_CATALOG,
    RULES_CATALOG_VERSION,
    ValidationEngine,
    ValidationRule,
    get_default_rules,
)


class _StubRule(ValidationRule):
    def __init__(self, rule_id: str, count: int) -> None:
        self._rule_id = rule_id
        self._count = count

    @property
    def rule_id(self) -> str:
        return self._rule_id

    def evaluate(self, document: ScoreDocument) -> list[Finding]:
        anchor = document.anchors.anchors()[0]
        return [
            Finding(
                anchor=anchor,
                rule_id=self._rule_id,
                severity=Severity.INFO,
                message="stub",
            )
            for _ in range(self._count)
        ]


def _document(tmp_path: Path) -> ScoreDocument:
    return FakeOMREngine().transcribe(tmp_path / "score.png")


def test_no_rules_yields_no_findings(tmp_path: Path) -> None:
    assert ValidationEngine([]).validate(_document(tmp_path)) == []


def test_findings_are_flattened_across_rules(tmp_path: Path) -> None:
    engine = ValidationEngine([_StubRule("a", 1), _StubRule("b", 2)])
    findings = engine.validate(_document(tmp_path))
    assert len(findings) == 3
    assert [finding.rule_id for finding in findings] == ["a", "b", "b"]


def test_rules_are_exposed(tmp_path: Path) -> None:
    rules = [_StubRule("a", 0), _StubRule("b", 0)]
    assert ValidationEngine(rules).rules == tuple(rules)


def test_validation_does_not_mutate_document(tmp_path: Path) -> None:
    document = _document(tmp_path)
    snapshot = document
    ValidationEngine([_StubRule("a", 1)]).validate(document)
    assert document == snapshot


CATALOG = (
    "accidental.repeated",
    "key.consistency",
    "measure.balance",
    "pitch.range",
    "tie.resolution",
    "time.signature",
    "tuplet.incomplete",
    "voice.collision",
)


def test_default_rules_catalog_is_the_one_of_adr_0040() -> None:
    assert len(DEFAULT_RULES_CATALOG) == 8
    assert tuple(sorted(rule.rule_id for rule in get_default_rules())) == CATALOG
    assert RULES_CATALOG_VERSION == 2


def test_engine_initializes_with_default_rules() -> None:
    """`rules_version` sigue siendo la lista de identificadores ordenada: `exp_06` la separa por
    comas para saber qué reglas medir (ADR-0040 §3)."""
    engine = ValidationEngine()
    assert len(engine.rules) == 8
    assert engine.rules_version == ",".join(CATALOG)
    assert engine.rules_version.split(",") == list(CATALOG)


def test_default_engine_validates_fake_omr_cleanly(tmp_path: Path) -> None:
    document = _document(tmp_path)
    findings = ValidationEngine().validate(document)
    assert findings == []
