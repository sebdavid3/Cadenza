"""Pruebas de la medición de la capa de sugerencias de `exp_14` (#257).

Usan el corpus sintético de `suggestions_support`: en Fa mayor, un Si natural leído que casi
siempre es Si bemol (las reglas no lo ven) y, en algunos incipits, una negra leída como
corchea (measure.balance la ve y ofrece candidatos).
"""

from __future__ import annotations

from collections import Counter
from fractions import Fraction
from typing import Any

import pytest
from cadenza.application import PolicySuggestionModel, SuggestionPolicy
from cadenza.application.suggestions import suggest
from cadenza.domain import (
    Anchor,
    EditOp,
    EventKind,
    Provenance,
    ScoreDocument,
    ScoreIR,
    SuggestedEdit,
    SuggestionResult,
    build_anchor_index,
)
from cadenza.learning import (
    assign_split,
    build_correction_records,
    derive_edit_events,
    evaluate_score_measures,
    primus_work_id,
    score_ser_pair,
)
from cadenza.learning.suggestion_measurement import (
    IncipitCase,
    RuleOrderModel,
    apply_suggestions,
    classify_suggestions,
    is_true_fix,
    measure_cases,
    measure_errors,
    measure_incipit,
    principal_metrics,
    select_suggestions,
    subsample_works,
    truth_of,
)
from cadenza.learning.suggestions import load_suggestions_config, train
from cadenza.learning.validation_metrics import evaluate_measures
from cadenza.validation import ValidationEngine
from cadenza.validation.learned import FrequencyBackoffModel, ScoreFeatures

from .suggestions_support import (
    SPLIT_SEED,
    _note,
    _score,
    corpus_records,
    incipit_id,
    incipit_pair,
    small_config,
)


def _records(work: int, index: int) -> tuple[ScoreIR, ScoreIR, list[dict[str, Any]]]:
    read, truth = incipit_pair(work, index)
    identifier = incipit_id(work, index)
    split = assign_split(primus_work_id(identifier), seed=SPLIT_SEED)
    records = build_correction_records(
        read, truth, incipit_id=identifier, split=split, verified=True
    )
    return read, truth, records


def _case(work: int, index: int) -> IncipitCase:
    read, _, records = _records(work, index)
    identifier = incipit_id(work, index)
    return IncipitCase(
        incipit_id=identifier,
        work=primus_work_id(identifier),
        score=read,
        records=tuple(records),
    )


def _find(predicate: Any) -> tuple[int, int]:
    for work in range(60):
        for index in (0, 1):
            if predicate(work, index):
                return work, index
    raise AssertionError("ningún incipit del corpus sintético cumple la condición")


def _case_of(work: int, index: int) -> int:
    return (work * 2 + index) % 10


def _has_eighth(work: int, index: int) -> bool:
    return (work + index) % 3 == 0


@pytest.fixture(scope="module")
def model(tmp_path_factory: pytest.TempPathFactory) -> FrequencyBackoffModel:
    config = load_suggestions_config(small_config(tmp_path_factory.mktemp("cfg") / "c.json"))
    return FrequencyBackoffModel(train(corpus_records(), config, dataset_hash="d"), version="t")


# --- La verdad del corpus ----------------------------------------------------------------


def test_the_truth_is_the_one_of_the_corpus_records() -> None:
    work, index = _find(lambda w, i: _case_of(w, i) < 7 and _has_eighth(w, i))
    _, _, records = _records(work, index)
    truth = truth_of(records)
    # El Si natural leído es un Si bemol: la alteración que pide la armadura.
    assert truth.labels[(0, 0, 1, 0, 3)]["accidental"] == "=key"
    # La corchea leída es una negra.
    assert truth.labels[(0, 0, 2, 0, 2)]["duration"] == "x2"
    assert (0, 0, 1, 0, 0) in truth.correct_events
    assert (0, 0, 1, 0, 3) not in truth.correct_events
    assert truth.correct_events.isdisjoint({(0, 0, 2, 0, 2)})


def test_the_errors_of_each_measure_are_those_of_derive_edit_events() -> None:
    """Las ediciones por compás salen de los registros y son las de `exp_06`."""
    for work, index in [(0, 0), (1, 1), (4, 1), (9, 0)]:
        read, sounding, records = _records(work, index)
        derived = derive_edit_events(read, sounding, document_id="x")
        assert Counter(
            (e.part, e.staff, e.measure, e.op) for e in measure_errors(records)
        ) == Counter((d.anchor.part, d.anchor.staff, d.anchor.measure, d.op.value) for d in derived)


def test_measures_are_evaluated_as_in_exp_06() -> None:
    work, index = _find(lambda w, i: _has_eighth(w, i))
    read, sounding, records = _records(work, index)
    document = ScoreDocument(
        id="x",
        score=read,
        anchors=build_anchor_index(read),
        provenance=Provenance(omr_engine="homr"),
    )
    findings = ValidationEngine().validate(document)
    edits = derive_edit_events(read, sounding, document_id="x")
    assert evaluate_measures("x", read, findings, measure_errors(records)) == (
        evaluate_score_measures("x", read, findings, edits)
    )


# --- Medir un incipit --------------------------------------------------------------------


def test_the_layer_flags_an_accidental_the_rules_do_not_see(model: FrequencyBackoffModel) -> None:
    work, index = _find(lambda w, i: _case_of(w, i) < 7 and not _has_eighth(w, i))
    case = _case(work, index)
    measured = measure_incipit(case, model, ValidationEngine())

    rules = {r.measure_number: r for r in measured.measures_rules}
    layered = {r.measure_number: r for r in measured.measures_with_layer}
    assert rules[1].has_real_error and not rules[1].flagged_global
    assert layered[1].flagged_global
    assert "learned.accidental" in layered[1].flagged_rules
    counts = measured.counts
    assert counts["learned_findings"] == 1 and counts["learned_correct"] == 1
    assert counts["blind_errors"] == 1 and counts["blind_flagged_with_correct_fix"] == 1

    # Aplicar la primera sugerencia de cada hallazgo arregla el incipit. (En el corpus
    # sintético ningún umbral llega a la precisión de la confianza alta.)
    selected = select_suggestions(measured.suggested, "first")
    assert [s.op for s in selected] == [EditOp.SET_ACCIDENTAL]
    fixed, applied, skipped = apply_suggestions(case.score, selected, document_id="x")
    assert (len(applied), skipped) == (1, 0)
    _, sounding, _ = _records(work, index)
    # Las alturas del ScoreIR son las que suenan: la SER se mide sin aplicar la armadura.
    assert score_ser_pair(sounding, case.score, apply_key_signature=False).ser > 0
    assert score_ser_pair(sounding, fixed, apply_key_signature=False).ser == 0
    assert measured.applied["first"]["correct"] == 1
    assert measured.applied["first"]["damaged_correct_events"] == 0
    assert measured.selected["high"]["suggestions"] <= measured.selected["first"]["suggestions"]
    assert measured.fixed["first"] == fixed


def test_a_suggestion_on_a_correct_note_is_damage(model: FrequencyBackoffModel) -> None:
    """Un Si natural que sí era natural: la capa lo cambiaría y estropearía una nota buena."""
    work, index = _find(lambda w, i: _case_of(w, i) in (7, 8) and not _has_eighth(w, i))
    measured = measure_incipit(_case(work, index), model, ValidationEngine())
    assert measured.counts["learned_findings"] == 1
    assert measured.counts["learned_correct"] == 0
    assert measured.applied["first"]["damaged_correct_events"] == 1
    assert measured.applied["first"]["damaged_correct_attributes"] == 1
    assert measured.applied["first"]["correct"] == 0
    assert measured.counts["correct_events"] == 8


def test_the_measurement_follows_the_display_policy_of_production(
    model: FrequencyBackoffModel,
) -> None:
    """Con la capa envuelta en la política de la API, la medición solo ve lo que se mostraría:
    los hallazgos de las reglas siguen, sin los candidatos de otras familias (ADR-0036,
    enmienda 19). En el corpus sintético ninguna familia llega a la confianza alta, así que se
    mide con `medium`."""
    work, index = _find(lambda w, i: _has_eighth(w, i) and _case_of(w, i) < 7)
    case = _case(work, index)
    everything = measure_incipit(case, model, ValidationEngine())
    policy = SuggestionPolicy(min_level="medium", families=frozenset({"accidental"}))
    shown = measure_incipit(case, PolicySuggestionModel(model, policy), ValidationEngine())

    def rules(measured: Any) -> list[str]:
        return [f.rule_id for f, _ in measured.suggested if not f.rule_id.startswith("learned.")]

    assert rules(shown) == rules(everything)
    assert any(
        s.op is not EditOp.SET_ACCIDENTAL
        for _, suggestions in everything.suggested
        for s in suggestions
    )
    assert all(
        s.op is EditOp.SET_ACCIDENTAL for _, suggestions in shown.suggested for s in suggestions
    )
    assert shown.counts["learned_findings"] == everything.counts["learned_findings:accidental"]
    assert shown.selected["first"]["suggestions"] < everything.selected["first"]["suggestions"]


def test_rule_suggestions_are_scored_top1_and_top3_against_the_rule_order(
    model: FrequencyBackoffModel,
) -> None:
    work, index = _find(lambda w, i: _has_eighth(w, i) and _case_of(w, i) < 7)
    measured = measure_incipit(_case(work, index), model, ValidationEngine())
    counts = measured.counts
    assert counts["rule_findings_with_true_candidate"] >= 1
    assert counts["rule_top3_correct"] >= counts["rule_top1_correct"]
    assert counts["baseline_top3_correct"] >= counts["baseline_top1_correct"]
    assert counts["rule_findings_with_suggestions"] >= counts["rule_findings_with_true_candidate"]


def test_the_rule_order_model_keeps_the_candidates_of_the_rules() -> None:
    work, index = _find(lambda w, i: _has_eighth(w, i))
    read, _, _ = _records(work, index)
    document = ScoreDocument(
        id="x", score=read, anchors=build_anchor_index(read), provenance=Provenance("homr")
    )
    findings = ValidationEngine().validate(document)
    suggested = suggest(document, findings, RuleOrderModel())
    with_candidates = [(f, s) for f, s in suggested if f.candidates]
    assert with_candidates
    for finding, suggestions in with_candidates:
        assert [(s.op, s.after) for s in suggestions] == [
            (c.op, c.after) for c in finding.candidates[: len(suggestions)]
        ]


# --- Aplicar sugerencias -----------------------------------------------------------------


def _anchor(measure: int, index: int) -> Anchor:
    return Anchor(part=0, staff=0, measure=measure, voice=0, event_index=index, staff_id="P1-S1")


def test_applying_translates_anchors_and_skips_what_does_not_fit() -> None:
    read, _ = incipit_pair(0, 0)
    insert = SuggestedEdit(
        op=EditOp.INSERT_EVENT,
        anchor=_anchor(1, 0),
        after={"kind": "rest", "duration_beats": "1/2", "voice": 0},
    )
    flat = SuggestedEdit(op=EditOp.SET_ACCIDENTAL, anchor=_anchor(1, 3), after={"accidental": "b"})
    # Una que ya no cabe en el estado al que llega se descarta.
    outside = SuggestedEdit(
        op=EditOp.SET_ACCIDENTAL, anchor=_anchor(1, 6), after={"accidental": "#"}
    )
    fixed, applied, skipped = apply_suggestions(read, [insert, flat, outside], document_id="x")
    assert (applied, skipped) == ([insert, flat], 1)
    events = fixed.parts[0].staves[0].measures[0].events
    assert events[0].kind is EventKind.REST and events[0].duration_beats == Fraction(1, 2)
    # El bemol cae en el Si leído, desplazado por la inserción.
    assert events[4].pitch == "Bb4"


def test_selection_keeps_the_first_suggestion_per_finding_and_position() -> None:
    def edit(index: int, level: str) -> SuggestedEdit:
        return SuggestedEdit(
            op=EditOp.SET_ACCIDENTAL,
            anchor=_anchor(1, index),
            after={"accidental": "flat"},
            confidence=0.5,
            confidence_level=level,
        )

    finding: Any = object()
    suggested = [
        (finding, (edit(3, "high"), edit(2, "high"))),
        (finding, (edit(3, "high"),)),
        (finding, (edit(1, "medium"),)),
        (finding, ()),
    ]
    assert [s.anchor.event_index for s in select_suggestions(suggested, "high")] == [3]
    assert [s.anchor.event_index for s in select_suggestions(suggested, "first")] == [3, 1]


# --- Agregar -----------------------------------------------------------------------------


def test_the_summary_is_measured_and_without_fallback_values(model: FrequencyBackoffModel) -> None:
    records = corpus_records()
    tests = sorted({r["incipit_id"] for r in records if r["split"] == "test"})
    cases = []
    for identifier in tests:
        rows = tuple(r for r in records if r["incipit_id"] == identifier)
        work = int(identifier.split("-")[0]) - 100000
        index = int(identifier.rsplit("_", 1)[1]) - 1
        cases.append(
            IncipitCase(
                incipit_id=identifier,
                work=primus_work_id(identifier),
                score=incipit_pair(work, index)[0],
                records=rows,
            )
        )
    summary = measure_cases(cases, model)
    assert summary["incipits"] == len(cases)
    measures = summary["rule_blind_measures"]
    rules = measures["rules"]["global_metrics"]
    layered = measures["rules_and_layer"]["global_metrics"]
    assert layered["recall"] > rules["recall"]
    assert set(measures["coverage_by_category"]) >= {
        "accidental",
        "duration",
        "pitch",
        "structure",
    }
    accidental = measures["coverage_by_category"]["accidental"]
    assert (
        accidental["rules_and_layer"]["detected_measures"]
        > accidental["rules"]["detected_measures"]
    )
    assert measures["measures_with_error_unseen_by_rules"] > 0
    assert summary["rule_suggestions"]["top1"]["over_true_candidate"]["accuracy"] is not None
    first = summary["damage"]["first"]
    assert first["applied"]["suggestions"] > 0
    assert first["applied"]["suggestions"] <= first["selected"]["suggestions"]
    assert first["applied"]["damaged_correct_attributes"] >= 0
    metrics = principal_metrics(summary)
    assert metrics["measure_recall_rules"] == rules["recall"]
    assert metrics["measure_recall_rules_and_layer"] == layered["recall"]
    assert all(v is None or isinstance(v, float | int) for v in metrics.values())

    empty = measure_cases([], model)
    assert empty["incipits"] == 0
    assert empty["rule_suggestions"]["top1"]["over_true_candidate"]["accuracy"] is None
    assert empty["learned_findings"]["precision"] is None
    # Sin denominador no hay cifra: None, nunca 0.0.
    for side in ("rules", "rules_and_layer"):
        metrics = empty["rule_blind_measures"][side]["global_metrics"]
        assert metrics["precision"] is None and metrics["recall"] is None
        assert metrics["f1"] is None
    coverage = empty["rule_blind_measures"]["coverage_by_category"]["accidental"]
    assert coverage["rules"]["coverage_rate"] is None
    assert empty["damage"]["high"]["applied"]["precision"] is None
    empty_metrics = principal_metrics(empty)
    assert empty_metrics["rule_top1_accuracy"] is None
    assert empty_metrics["measure_recall_rules"] is None


def test_works_are_subsampled_nested_and_seeded() -> None:
    works = [f"w{n:03d}" for n in range(40)]
    ten = subsample_works(works, 0.1, seed=5)
    half = subsample_works(works, 0.5, seed=5)
    assert len(ten) == 4 and len(half) == 20
    assert set(ten) <= set(half)
    assert subsample_works(works, 1.0, seed=5) == sorted(works)
    assert subsample_works(works, 0.5, seed=5) == half
    assert subsample_works(works, 0.5, seed=6) != half
    with pytest.raises(ValueError):
        subsample_works(works, 0.0, seed=5)


# --- Tras la revisión independiente -------------------------------------------------------


def _pair_records(read: ScoreIR, truth: ScoreIR) -> list[dict[str, Any]]:
    return build_correction_records(read, truth, incipit_id="x", split="test", verified=True)


def _edit(op: EditOp, index: int, after: dict[str, Any] | None) -> SuggestedEdit:
    return SuggestedEdit(op=op, anchor=_anchor(1, index), after=after)


class _Broken:
    version = "broken"

    def suggest(self, document: ScoreDocument, findings: Any) -> SuggestionResult:
        raise RuntimeError("la capa se rompió")


class _Dropping:
    version = "dropping"

    def suggest(self, document: ScoreDocument, findings: Any) -> SuggestionResult:
        return SuggestionResult(findings=())


def test_a_layer_that_fails_stops_the_measurement() -> None:
    """En producción, la capa que falla deja los hallazgos sin sugerencias; medirlo así
    contaría una capa rota como una capa que no sugiere nada."""
    work, index = _find(lambda w, i: _has_eighth(w, i))
    case = _case(work, index)
    with pytest.raises(RuntimeError, match="se rompió"):
        measure_incipit(case, _Broken(), ValidationEngine())
    with pytest.raises(ValueError, match="hallazgos de las reglas"):
        measure_incipit(case, _Dropping(), ValidationEngine())


def test_a_true_fix_has_the_value_of_the_truth() -> None:
    """La altura y el evento insertado se comparan con los de la verdad, no solo la familia."""
    read = _score((_note("F4"), _note("G4"), _note("A4"), _note("B4")))
    truth = _score((_note("F4"), _note("G4"), _note("A4"), _note("D5")))
    known, features = truth_of(_pair_records(read, truth)), ScoreFeatures.of(read)
    assert is_true_fix(_edit(EditOp.SET_PITCH, 3, {"pitch": "D5"}), features, known)
    # Una tercera arriba, como la verdad, pero no la misma altura.
    assert not is_true_fix(_edit(EditOp.SET_PITCH, 3, {"pitch": "D#5"}), features, known)

    read = _score((_note("F4"), _note("G4"), _note("A4")))
    truth = _score((_note("F4"), _note("G4"), _note("A4"), _note("C5")))
    known, features = truth_of(_pair_records(read, truth)), ScoreFeatures.of(read)
    note = {"kind": "note", "duration_beats": "1", "voice": 0}
    assert is_true_fix(_edit(EditOp.INSERT_EVENT, 3, {**note, "pitch": "C5"}), features, known)
    assert not is_true_fix(_edit(EditOp.INSERT_EVENT, 3, {**note, "pitch": "D5"}), features, known)


def test_damage_is_counted_by_event_and_by_attribute() -> None:
    read = _score((_note("F4"), _note("G4"), _note("A4"), _note("B4")))
    truth = _score((_note("F4"), _note("G4"), _note("A4")))
    known = truth_of(_pair_records(read, truth))
    deleted = next(p for p, labels in known.labels.items() if labels.get("delete") == "delete")
    features = ScoreFeatures.of(read)
    counts = classify_suggestions(
        [
            # La alteración de un evento que la verdad borra: daño del atributo, no del evento.
            _edit(EditOp.SET_ACCIDENTAL, deleted[4], {"accidental": "#"}),
            # La duración de una nota correcta: daño del evento y del atributo.
            _edit(EditOp.SET_DURATION, 0, {"duration_beats": "2"}),
            _edit(EditOp.DELETE_EVENT, deleted[4], None),
            _edit(EditOp.INSERT_EVENT, 0, {"kind": "rest", "duration_beats": "1", "voice": 0}),
        ],
        features,
        known,
    )
    assert counts["suggestions"] == 4
    assert counts["correct"] == 1 and counts["attribute_correct"] == 1
    assert counts["damaged_correct_events"] == 1
    assert counts["wrong_fix_on_erroneous_event"] == 1
    assert counts["damaged_correct_attributes"] == 2
    assert counts["insertion_where_nothing_is_missing"] == 1

    # La duración de una nota cuyo único error es la altura daña un atributo correcto.
    read = _score((_note("F4"), _note("G4"), _note("A4"), _note("B4")))
    truth = _score((_note("F4"), _note("G4"), _note("A4"), _note("D5")))
    known, features = truth_of(_pair_records(read, truth)), ScoreFeatures.of(read)
    counts = classify_suggestions(
        [
            _edit(EditOp.SET_DURATION, 3, {"duration_beats": "2"}),
            _edit(EditOp.SET_PITCH, 3, {"pitch": "E5"}),
        ],
        features,
        known,
    )
    assert counts["wrong_fix_on_erroneous_event"] == 2
    assert counts["damaged_correct_attributes"] == 1
    assert counts["wrong_value_on_erroneous_attribute"] == 1

    read = _score((_note("F4"), _note("G4"), _note("A4")))
    truth = _score((_note("F4"), _note("G4"), _note("A4"), _note("C5")))
    known, features = truth_of(_pair_records(read, truth)), ScoreFeatures.of(read)
    counts = classify_suggestions(
        [_edit(EditOp.INSERT_EVENT, 3, {"kind": "note", "duration_beats": "1", "pitch": "D5"})],
        features,
        known,
    )
    assert counts["insertion_with_wrong_event"] == 1
