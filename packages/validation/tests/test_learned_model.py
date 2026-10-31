"""La inferencia de la capa de sugerencias (ADR-0036 §1, §3, §8)."""

from __future__ import annotations

import hashlib
import json
from fractions import Fraction
from typing import Any

import pytest
from cadenza.domain import (
    EditOp,
    Event,
    EventKind,
    KeySignature,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Staff,
    TimeSignature,
    build_anchor_index,
)
from cadenza.validation import ValidationEngine
from cadenza.validation.learned import (
    ARTIFACT_FORMAT,
    ARTIFACT_FORMAT_VERSION,
    FEATURE_VERSION,
    MODEL_TYPE,
    FrequencyBackoffModel,
    InvalidSuggestionArtifact,
    ScoreFeatures,
    discretize,
    label_of_edit,
)

ACCIDENTAL_LEVELS = [["letter", "accidental", "key_fifths", "prev_acc"], ["acc_vs_key"], []]
DURATION_LEVELS = [["figure", "balance_sign"], []]


def _note(pitch: str, beats: str = "1") -> Event:
    return Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=Fraction(beats))


def _document(*measures_events: tuple[Event, ...], fifths: int = -1) -> ScoreDocument:
    measures = tuple(
        Measure(
            number=index + 1,
            events=events,
            time_signature=TimeSignature(4, 4) if index == 0 else None,
            key_signature=KeySignature(fifths=fifths) if index == 0 else None,
        )
        for index, events in enumerate(measures_events)
    )
    score = ScoreIR(parts=(Part(id="P1", staves=(Staff(id="P1-S1", measures=measures),)),))
    return ScoreDocument(
        id="doc", score=score, anchors=build_anchor_index(score), provenance=Provenance("fake")
    )


def _artifact(
    *,
    accidental_threshold: float | None = 0.5,
    accidental_active: bool = True,
    against_key: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Un artefacto pequeño: un Si natural leído en Fa mayor suele ser Si bemol."""
    return {
        "format": ARTIFACT_FORMAT,
        "format_version": ARTIFACT_FORMAT_VERSION,
        "model_type": MODEL_TYPE,
        "feature_version": FEATURE_VERSION,
        "params": {"alpha": 1.0, "min_support": 5},
        "families": {
            "accidental": {
                "levels": ACCIDENTAL_LEVELS,
                "tables": [
                    {"B||-1|-": {"=key": 30, "none": 10}},
                    {
                        "against_key": against_key or {"=key": 40, "none": 20},
                        "in_key": {"none": 900, "abs:#": 10},
                    },
                    {"": {"none": 920, "=key": 40, "abs:#": 10}},
                ],
                "threshold": accidental_threshold,
                "high_threshold": 0.7,
                "active": accidental_active,
            },
            "duration": {
                "levels": DURATION_LEVELS,
                "tables": [
                    {"1/2|under": {"x2": 6, "none": 4}},
                    {"": {"none": 900, "x2": 10, "x1/2": 5}},
                ],
                "threshold": None,
                "high_threshold": None,
                "active": False,
            },
            "insertion": {
                "levels": [["balance_sign"], []],
                "tables": [{"under": {"rest:1/2": 2, "note:1/2": 8}}, {"": {"rest:1/2": 8}}],
                "threshold": None,
                "high_threshold": None,
                "active": False,
            },
        },
    }


def _model(**kwargs: Any) -> FrequencyBackoffModel:
    return FrequencyBackoffModel(_artifact(**kwargs), version="sug-test")


def test_backoff_uses_the_most_specific_key_with_support_smoothed_toward_the_general() -> None:
    model = _model()
    document = _document((_note("B4"), _note("C5"), _note("D5"), _note("E5")))
    view = ScoreFeatures.of(document.score).events[(0, 0, 1, 0, 0)]
    score = model.score("accidental", view.features, "=key")
    assert score is not None
    # Nivel específico (B, natural, -1, sin previa): 30 de 40, suavizado hacia el general.
    general = (40 + 1.0 * ((40 + 1.0 / 3) / (970 + 1.0))) / (60 + 1.0)
    assert score.probability == pytest.approx((30 + 1.0 * general) / (40 + 1.0))
    assert (score.count, score.support) == (30, 40)


def test_a_key_below_min_support_backs_off_to_the_next_level() -> None:
    model = _model()
    document = _document((_note("E4"), _note("C5"), _note("D5"), _note("E5")), fifths=-2)
    # Mi natural en Si bemol mayor: la clave específica no existe; se usa `against_key`.
    view = ScoreFeatures.of(document.score).events[(0, 0, 1, 0, 0)]
    score = model.score("accidental", view.features, "=key")
    assert score is not None and score.support == 60


def test_learned_finding_for_an_accidental_the_rules_do_not_see() -> None:
    model = _model()
    document = _document((_note("B4"), _note("C5"), _note("D5"), _note("E5")))
    findings = ValidationEngine().validate(document)
    assert findings == []  # las reglas no ven el Si natural en Fa mayor
    result = model.suggest(document, findings)
    (learned,) = result.findings
    assert learned.finding.rule_id == "learned.accidental"
    assert learned.finding.severity.value == "warning"
    assert "Si" in learned.finding.message and "Si♭" in learned.finding.message
    assert learned.finding.anchor == document.anchors.anchors()[0]
    (suggestion,) = learned.suggestions
    assert suggestion.op is EditOp.SET_ACCIDENTAL
    assert dict(suggestion.after or {}) == {"accidental": "b"}
    assert suggestion.source == "learned"
    assert suggestion.model_version == "sug-test"
    assert suggestion.confidence is not None and suggestion.confidence > 0.7
    assert suggestion.confidence_level == "high"
    assert "30 de 40" in suggestion.explanation


def test_no_learned_finding_below_the_threshold_or_for_inactive_families() -> None:
    document = _document((_note("B4"), _note("C5"), _note("D5"), _note("E5")))
    assert _model(accidental_threshold=0.95).suggest(document, []).findings == ()
    assert _model(accidental_active=False).suggest(document, []).findings == ()
    assert _model(accidental_threshold=None).suggest(document, []).findings == ()


def test_rule_candidates_are_all_ranked_by_the_layer() -> None:
    model = _model()
    # 4/4 con 3 negras y una corchea: measure.balance ofrece alargar cada nota y un silencio.
    document = _document((_note("B4"), _note("C5"), _note("D5"), _note("E5", "1/2")))
    findings = ValidationEngine().validate(document)
    (balance,) = [f for f in findings if f.rule_id == "measure.balance"]
    assert len(balance.candidates) > 3
    result = model.suggest(document, findings)
    ranked = next(sf for sf in result.findings if sf.finding is balance)
    # Todas, ordenadas: los casos de uso descartan las inadmisibles y se quedan con tres.
    assert len(ranked.suggestions) == len(balance.candidates)
    first = ranked.suggestions[0]
    # La corchea que pasa a negra (x2, con 6 de 10 en su contexto) gana.
    assert (first.op, first.anchor.event_index) == (EditOp.SET_DURATION, 3)
    confidences = [s.confidence for s in ranked.suggestions if s.confidence is not None]
    assert confidences == sorted(confidences, reverse=True)
    assert all(s.model_version == "sug-test" for s in ranked.suggestions)


def test_no_learned_finding_on_a_rule_anchor_but_yes_on_other_events_of_the_measure() -> None:
    model = _model()
    # El compás está incompleto y el Si natural es el segundo evento: measure.balance ancla
    # el primero, y el Si no tiene candidato de alteración de esa regla.
    document = _document((_note("C5"), _note("B4"), _note("D5"), _note("E5", "1/2")))
    findings = ValidationEngine().validate(document)
    result = model.suggest(document, findings)
    learned = [sf for sf in result.findings if sf.finding.rule_id.startswith("learned.")]
    assert [sf.finding.anchor.event_index for sf in learned] == [1]
    # Sobre el ancla de la regla, nunca.
    blocked = _document((_note("B4"), _note("C5"), _note("D5"), _note("E5", "1/2")))
    blocked_findings = ValidationEngine().validate(blocked)
    assert not [
        sf
        for sf in model.suggest(blocked, blocked_findings).findings
        if sf.finding.rule_id.startswith("learned.")
    ]


def test_without_data_the_candidates_keep_the_rule_order_and_no_confidence() -> None:
    artifact = _artifact()
    artifact["families"]["duration"]["tables"] = [{}, {}]
    artifact["families"]["insertion"]["tables"] = [{}, {}]
    model = FrequencyBackoffModel(artifact, version="v")
    document = _document((_note("C5"), _note("C5"), _note("D5"), _note("E5", "1/2")))
    findings = ValidationEngine().validate(document)
    (balance,) = [f for f in findings if f.rule_id == "measure.balance"]
    ranked = next(sf for sf in model.suggest(document, findings).findings if sf.finding is balance)
    assert [s.anchor for s in ranked.suggestions] == [c.anchor for c in balance.candidates]
    assert all(s.confidence is None and s.source == "rule" for s in ranked.suggestions)


def test_label_of_a_candidate_matches_the_label_counted_from_the_corpus() -> None:
    document = _document((_note("B4"), _note("C5"), _note("D5"), _note("E5", "1/2")))
    view = ScoreFeatures.of(document.score).events[(0, 0, 1, 0, 3)]
    assert label_of_edit(EditOp.SET_DURATION, {"duration_beats": "1"}, view) == ("duration", "x2")
    b_view = ScoreFeatures.of(document.score).events[(0, 0, 1, 0, 0)]
    assert label_of_edit(EditOp.SET_ACCIDENTAL, {"accidental": "b"}, b_view) == (
        "accidental",
        "=key",
    )
    assert label_of_edit(EditOp.SET_PITCH, {"pitch": "Bb4"}, b_view) == ("accidental", "=key")
    assert label_of_edit(EditOp.SET_PITCH, {"pitch": "C5"}, b_view) == ("pitch", "+1")


def test_features_never_use_corpus_metadata() -> None:
    features = discretize(
        {"kind": "note", "pitch": "C4", "duration_beats": "1", "verified": True},
        {"split": "test", "incipit_id": "x", "aligned": True},
    )
    assert not {"split", "incipit_id", "aligned", "verified"} & set(features)
    assert not any(value in ("test", "x") for value in features.values())


def test_artifact_checks_sha256_and_feature_version() -> None:
    content = json.dumps(_artifact()).encode()
    digest = hashlib.sha256(content).hexdigest()
    assert FrequencyBackoffModel.from_bytes(content, version="v", expected_sha256=digest)
    with pytest.raises(InvalidSuggestionArtifact, match="sha256"):
        FrequencyBackoffModel.from_bytes(content, version="v", expected_sha256="0" * 64)
    stale = _artifact()
    stale["feature_version"] = FEATURE_VERSION + 1
    with pytest.raises(InvalidSuggestionArtifact, match="rasgos"):
        FrequencyBackoffModel(stale, version="v")
    with pytest.raises(InvalidSuggestionArtifact):
        FrequencyBackoffModel.from_bytes(b"not json", version="v")


def test_inference_does_not_import_application_learning_or_heavy_dependencies() -> None:
    import ast
    from pathlib import Path

    forbidden = {"cadenza.application", "cadenza.learning", "music21", "fastapi", "sqlalchemy"}
    source = Path(__file__).resolve().parents[1] / "src" / "cadenza" / "validation"
    imported: set[str] = set()
    for path in source.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
    assert not {m for m in imported if any(m == f or m.startswith(f + ".") for f in forbidden)}


def test_no_duration_or_deletion_is_proposed_inside_a_chord() -> None:
    artifact = _artifact()
    artifact["families"]["duration"].update({"threshold": 0.1, "active": True})
    artifact["families"]["duration"]["tables"] = [{}, {"": {"x2": 90, "none": 10}}]
    model = FrequencyBackoffModel(artifact, version="v")
    chord = (
        _note("C5"),
        Event(kind=EventKind.NOTE, pitch="E5", duration_beats=Fraction(1), is_chord=True),
        _note("D5"),
        _note("E5"),
        _note("F5"),
    )
    document = _document(chord)
    proposed = {
        sf.finding.anchor.event_index
        for sf in model.suggest(document, []).findings
        if sf.finding.rule_id == "learned.duration"
    }
    assert proposed == {2, 3, 4}


def test_an_inadmissible_family_does_not_hide_an_admissible_one() -> None:
    """Un silencio no tiene alteración: la capa propone la familia siguiente que sí cabe."""
    artifact = _artifact()
    artifact["families"]["accidental"]["levels"] = [[]]
    artifact["families"]["accidental"]["tables"] = [{"": {"abs:#": 90, "none": 10}}]
    artifact["families"]["accidental"].update({"threshold": 0.1, "active": True})
    artifact["families"]["duration"]["tables"] = [{}, {"": {"x2": 60, "none": 40}}]
    artifact["families"]["duration"].update({"threshold": 0.1, "active": True})
    model = FrequencyBackoffModel(artifact, version="v")
    rest = Event(kind=EventKind.REST, duration_beats=Fraction(1))
    document = _document((rest, _note("C5"), _note("D5"), _note("E5")))
    by_index = {sf.finding.anchor.event_index: sf for sf in model.suggest(document, []).findings}
    assert by_index[0].finding.rule_id == "learned.duration"
    assert by_index[0].suggestions[0].op is EditOp.SET_DURATION
    assert by_index[1].finding.rule_id == "learned.accidental"
