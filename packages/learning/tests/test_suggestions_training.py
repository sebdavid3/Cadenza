"""Entrenamiento, evaluación, promoción y corpus de la capa de sugerencias (ADR-0036 §2, §6,
§9, §10). Los corpus se escriben en `tmp_path`: nada va a `results/` ni a `data/`."""

from __future__ import annotations

import json
from collections import Counter
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from cadenza.application import (
    InMemoryEditEventRepository,
    InMemorySessionRepository,
    InMemoryUserRepository,
    Role,
    SessionData,
    User,
    append_edit,
    finalize_session,
    reject_suggestion,
    transcribe_score,
)
from cadenza.domain import (
    Anchor,
    EditOp,
    Event,
    EventKind,
    KeySignature,
    Measure,
    Part,
    ScoreIR,
    Staff,
    TimeSignature,
)
from cadenza.learning import assign_split, build_correction_records
from cadenza.learning.suggestions import (
    SuggestionTrainingError,
    artifact_bytes,
    evaluate,
    fold_of,
    gap_examples,
    load_suggestions_config,
    promotion_decision,
    reconstruct_score,
    session_records,
    train,
    work_of,
)
from cadenza.omr import OMREngine
from cadenza.validation import ValidationEngine
from cadenza.validation.learned import FrequencyBackoffModel, ScoreFeatures, discretize

from .suggestions_support import (
    SPLIT_SEED,
    corpus_records,
    incipit_id,
    incipit_pair,
    small_config,
    write_corpus,
)


def _event_records(read: ScoreIR, truth: ScoreIR) -> list[dict[str, Any]]:
    return build_correction_records(read, truth, incipit_id="x-1", split="train", verified=True)


def _two_voices() -> tuple[ScoreIR, ScoreIR]:
    def measure(number: int, *events: Event) -> Measure:
        return Measure(number=number, events=events, time_signature=TimeSignature(3, 4))

    def note(pitch: str, beats: str, voice: int = 0, chord: bool = False) -> Event:
        return Event(
            kind=EventKind.NOTE,
            voice=voice,
            pitch=pitch,
            duration_beats=Fraction(beats),
            is_chord=chord,
        )

    rest = Event(kind=EventKind.REST, voice=1, duration_beats=Fraction(1))
    read = ScoreIR(
        parts=(
            Part(
                id="P1",
                staves=(
                    Staff(
                        id="S",
                        measures=(
                            measure(
                                1, note("C#4", "1"), note("E4", "1", chord=True), note("D4", "1")
                            ),
                            measure(2, note("F4", "3"), rest, note("A3", "2", voice=1)),
                        ),
                    ),
                ),
            ),
        )
    )
    truth = ScoreIR(
        parts=(
            Part(
                id="P1",
                staves=(
                    Staff(
                        id="S",
                        measures=(
                            measure(
                                1,
                                note("C4", "1"),
                                note("E4", "1", chord=True),
                                note("D4", "1"),
                                note("E4", "1"),
                            ),
                            measure(2, note("F4", "3"), rest, note("A3", "2", voice=1)),
                        ),
                    ),
                ),
            ),
        )
    )
    return read, truth


@pytest.mark.parametrize("case", ["incipits", "voices"])
def test_the_context_of_the_features_is_the_one_of_the_corpus(case: str) -> None:
    """La misma función de rasgos para el corpus y la inferencia (ADR-0036 §2)."""
    pairs = (
        [incipit_pair(w, i) for w in range(6) for i in range(2)]
        if case == "incipits"
        else [_two_voices()]
    )
    for read, truth in pairs:
        records = _event_records(read, truth)
        features = ScoreFeatures.of(read)
        for record in records:
            anchor = record["anchor"]
            position = (
                anchor["part"],
                anchor["staff"],
                anchor["measure"],
                anchor["voice"],
                anchor["event_index"],
            )
            if record["record"] == "event":
                view = features.events[position]
                assert dict(view.context) == record["context"]
                assert dict(view.read) == record["read"]
            elif record["record"] == "insertion":
                assert features.gap(position) == discretize(None, record["context"])
        # Los huecos que se cuentan al entrenar son los que ve la inferencia.
        trained = Counter(tuple(sorted(e.features.items())) for e in gap_examples(records))
        seen: Counter[tuple[tuple[str, str], ...]] = Counter()
        for position in features.events:
            gap = features.gap(position)
            assert gap is not None
            seen[tuple(sorted(gap.items()))] += 1
        ends = {p[:4] for p in features.events}
        for part, staff, measure, voice in ends:
            length = features.voice_length(part, staff, measure, voice)
            assert length is not None
            end = features.gap((part, staff, measure, voice, length))
            assert end is not None
            seen[tuple(sorted(end.items()))] += 1
        insertions = sum(1 for r in records if r["record"] == "insertion")
        positions_with_insertions = len(
            {tuple(r["anchor"].values()) for r in records if r["record"] == "insertion"}
        )
        assert sum(trained.values()) == sum(seen.values()) + insertions - positions_with_insertions
        assert set(trained) == set(seen)


def test_corpus_metadata_never_becomes_a_feature() -> None:
    records = corpus_records(2)
    for record in records:
        if record["record"] != "event":
            continue
        features = discretize(record["read"], record["context"])
        for key in ("split", "incipit_id", "verified", "aligned"):
            assert key not in features


def test_folds_group_the_incipits_of_a_work() -> None:
    assert work_of({"incipit_id": "000051650-1_1_1"}) == "000051650"
    assert work_of({"incipit_id": "cadenza:s1", "work_id": "image:abc"}) == "image:abc"
    folds = {
        fold_of(work_of({"incipit_id": incipit_id(w, i)}), seed=3, folds=5)
        for i in (0, 1)
        for w in [7]
    }
    assert len(folds) == 1
    assert {fold_of(str(w), seed=3, folds=5) for w in range(200)} == set(range(5))


def test_training_is_reproducible_and_learns_the_accidental_family(tmp_path: Path) -> None:
    config = load_suggestions_config(small_config(tmp_path / "config.json"))
    records = corpus_records()
    first = train(records, config, dataset_hash="d" * 64)
    second = train(records, config, dataset_hash="d" * 64)
    assert artifact_bytes(first) == artifact_bytes(second)
    accidental = first["families"]["accidental"]
    assert accidental["threshold"] is not None and accidental["active"] is True
    # Solo se activan las familias de la configuración, aunque otras tengan umbral.
    assert first["families"]["duration"]["active"] is False
    training = first["training"]
    assert training["dataset_hash"] == "d" * 64
    assert training["config_hash"] == config.config_hash
    assert training["seed"] == config.seed
    assert training["cross_validation"]["folds"] == 5
    # Solo la partición de entrenamiento: ningún incipit de prueba cuenta.
    train_works = {work_of(r) for r in records if r["split"] == "train"}
    assert training["works"] == len(train_works)


def test_training_without_usable_records_fails() -> None:
    config = load_suggestions_config(
        Path(__file__).resolve().parents[3] / "configs" / "learning" / "suggestions.json"
    )
    unverified = [dict(r, verified=False) for r in corpus_records(3)]
    with pytest.raises(SuggestionTrainingError):
        train(unverified, config, dataset_hash="d")


def test_reconstructed_score_is_the_read_one() -> None:
    read, truth = incipit_pair(3, 0)
    records = _event_records(read, truth)
    rebuilt = reconstruct_score(records)
    for original, again in zip(
        read.parts[0].staves[0].measures, rebuilt.parts[0].staves[0].measures, strict=True
    ):
        assert again.events == original.events
        assert (again.time_signature, again.clef, again.key_signature) == (
            original.time_signature,
            original.clef,
            original.key_signature,
        )


def test_evaluation_is_measured_on_the_test_split_against_no_layer(tmp_path: Path) -> None:
    config = load_suggestions_config(small_config(tmp_path / "config.json"))
    records = corpus_records()
    model = FrequencyBackoffModel(train(records, config, dataset_hash="d"), version="v")
    report = evaluate(model, records)
    assert report["simulated"] is False
    test_incipits = {r["incipit_id"] for r in records if r["split"] == "test"}
    assert report["incipits"] == len(test_incipits) > 0
    learned = report["learned"]
    assert learned["active_families"] == ["accidental"]
    assert learned["f1"] is not None and learned["f1"] > report["baseline"]["learned_f1"] == 0.0
    # El Si natural no lo ve ninguna regla: la capa lo señala con el arreglo bueno.
    blind = report["rule_blind"]
    assert blind["errors"] > 0 and blind["flagged_with_correct_fix"] > 0
    ranking = report["rule_findings"]
    assert ranking["with_true_candidate"] > 0
    assert ranking["top1_accuracy"] > ranking["baseline_top1_accuracy"]


def test_promotion_requires_measured_improvement() -> None:
    base: dict[str, Any] = {
        "simulated": False,
        "split": "test",
        "evaluation_dataset_hash": "e",
        "learned": {"f1": 0.4},
        "rule_findings": {"top1_accuracy": 0.8},
        "baseline": {"learned_f1": 0.0, "top1_accuracy": 0.5},
    }
    assert promotion_decision(base, None)[0] is True
    assert promotion_decision({**base, "simulated": True}, None)[0] is False
    # Solo cuenta la partición de prueba fija, también en la primera promoción.
    assert promotion_decision({**base, "split": "train"}, None)[0] is False
    assert promotion_decision({**base, "learned": {"f1": None}}, None)[0] is False
    assert promotion_decision({**base, "learned": {"f1": 0.0}}, None)[0] is False
    worse_top1 = {**base, "rule_findings": {"top1_accuracy": 0.4}}
    assert promotion_decision(worse_top1, None)[0] is False
    active = {**base, "learned": {"f1": 0.3}}
    assert promotion_decision(base, active)[0] is True
    assert promotion_decision(base, {**base})[0] is False  # mismo F1: no mejora
    assert promotion_decision(base, {**active, "evaluation_dataset_hash": "otra"})[0] is False
    assert promotion_decision({**base, "rule_findings": {"top1_accuracy": 0.7}}, active)[0] is False


def test_the_cli_trains_evaluates_promotes_and_the_api_loads_it(tmp_path: Path) -> None:
    from cadenza.api import Settings
    from cadenza.api.suggestions import load_suggestion_model
    from cadenza.persistence import (
        SqlAlchemySuggestionModelRegistry,
        create_engine_for_url,
        create_schema,
        create_session_factory,
    )

    from ml.cli import main

    corpus = write_corpus(tmp_path / "corpus.jsonl")
    config = small_config(tmp_path / "config.json")
    model_path = tmp_path / "model.json"
    report_path = tmp_path / "report.json"
    db_url = f"sqlite:///{(tmp_path / 'cadenza.db').as_posix()}"
    engine = create_engine_for_url(db_url)
    create_schema(engine)
    artifacts = tmp_path / "artifacts"

    base = ["suggestions"]
    assert (
        main(
            [
                *base,
                "train",
                "--corpus",
                str(corpus),
                "--config",
                str(config),
                "--output",
                str(model_path),
            ]
        )
        == 0
    )
    first_bytes = model_path.read_bytes()
    assert (
        main(
            [
                *base,
                "train",
                "--corpus",
                str(corpus),
                "--config",
                str(config),
                "--output",
                str(model_path),
            ]
        )
        == 0
    )
    assert model_path.read_bytes() == first_bytes
    assert (
        main(
            [
                *base,
                "evaluate",
                "--model",
                str(model_path),
                "--corpus",
                str(corpus),
                "--output",
                str(report_path),
            ]
        )
        == 0
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["simulated"] is False and report["model_sha256"]
    promote = [
        *base,
        "promote",
        "--model",
        str(model_path),
        "--report",
        str(report_path),
        "--db-url",
        db_url,
        "--artifacts-dir",
        str(artifacts),
    ]
    assert main([*promote, "--version", "sug-a"]) == 0
    # La misma medición no mejora a la activa: no se promueve otra vez.
    assert main([*promote, "--version", "sug-b"]) == 1

    factory = create_session_factory(engine)
    with factory() as db:
        active = SqlAlchemySuggestionModelRegistry(db).active()
        assert active is not None and active.version == "sug-a"
        assert active.metrics["learned"]["f1"] == report["learned"]["f1"]
    loaded = load_suggestion_model(
        factory,
        Settings(
            auth_secret_key="secret-key-at-least-32-bytes-long-for-testing",
            artifacts_dir=artifacts,
            suggestions_enabled=True,
        ),
    )
    assert loaded is not None and loaded.version == "sug-a"


def test_the_cli_fails_clearly_without_data(tmp_path: Path) -> None:
    from ml.cli import main

    missing = tmp_path / "missing.jsonl"
    assert (
        main(
            ["suggestions", "train", "--corpus", str(missing), "--output", str(tmp_path / "m.json")]
        )
        == 1
    )
    assert not (tmp_path / "m.json").exists()


class _Engine(OMREngine):
    @property
    def engine_id(self) -> str:
        return "fake"

    def transcribe(self, image_path: Path) -> Any:
        from cadenza.domain import Provenance, ScoreDocument, build_anchor_index

        read, _ = incipit_pair(0, 0)
        return ScoreDocument(
            id="doc",
            score=read,
            anchors=build_anchor_index(read),
            provenance=Provenance(omr_engine="fake"),
        )


def test_build_dataset_adds_finalized_sessions_with_their_responses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load_suggestions_config(small_config(tmp_path / "config.json"))
    model = FrequencyBackoffModel(train(corpus_records(), config, dataset_hash="d"), version="v")
    edits = InMemoryEditEventRepository()
    sessions = InMemorySessionRepository(edit_repository=edits)
    owner = User(id="u1", username="ana", password_hash="h", role=Role.TRANSCRIPTOR)
    outsider = User(
        id="u2", username="pub", password_hash="h", role=Role.TRANSCRIPTOR, self_registered=True
    )
    users = InMemoryUserRepository([owner, outsider])
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    ids = []
    for user, test_score in ((owner, "TS-01"), (owner, "TS-01"), (outsider, "TS-02")):
        result = transcribe_score(
            image,
            omr_engine=_Engine(),
            validator=ValidationEngine(),
            session_repository=sessions,
            current_user=user,
            suggestion_model=model,
            test_score_id=test_score,
        )
        ids.append(result.session_id)
    first = ids[0]
    learned = next(f for f in sessions.list_findings(first) if f.rule_id.startswith("learned"))
    fix = learned.suggestions[0]
    append_edit(
        first,
        anchor=Anchor.from_primitive(fix.anchor),
        op=EditOp(fix.op),
        after=fix.after,
        base_seq=0,
        session_repository=sessions,
        edit_repository=edits,
        current_user=owner,
        suggestion_id=fix.id,
    )
    other = next(f for f in sessions.list_findings(ids[1]) if f.suggestions)
    reject_suggestion(
        ids[1], other.suggestions[0].id, session_repository=sessions, current_user=owner
    )
    for session_id, user in zip(ids, (owner, owner, outsider), strict=True):
        finalize_session(
            session_id,
            validator=ValidationEngine(),
            session_repository=sessions,
            edit_repository=edits,
            current_user=user,
        )
    # Una sesión sin finalizar no entra.
    sessions.add(
        SessionData(id="open", document_id="d", omr_engine="f", document={}, owner_id="u1"), []
    )

    records, left_out = session_records(
        session_repository=sessions,
        edit_repository=edits,
        user_repository=users,
        split_seed=SPLIT_SEED,
        test_fraction=0.2,
    )
    assert left_out == {ids[2]: "cuenta del registro público"}
    assert {r["session_id"] for r in records} == {ids[0], ids[1]}
    assert all(r["source"] == "cadenza" and r["work_id"] == "test_score:TS-01" for r in records)
    expected_split = assign_split("test_score:TS-01", seed=SPLIT_SEED, test_fraction=0.2)
    assert {r["split"] for r in records} == {expected_split}
    events = [r for r in records if r["record"] == "event" and r["session_id"] == first]
    assert all(r["verified"] for r in events)
    corrected = [r for r in events if r["correction"] is not None]
    assert [r["correction"]["ops"] for r in corrected] == [["SetAccidental"]]
    responses = Counter(r["response"] for r in records if r["record"] == "suggestion")
    assert responses["accepted"] == 1 and responses["rejected"] == 1
    assert responses["ignored"] > 0

    # La CLI une el corpus de exp_12 sin modificarlo.
    from cadenza.persistence import create_engine_for_url, create_schema

    from ml import suggestions_cli
    from ml.cli import main

    exp12 = write_corpus(tmp_path / "exp12.jsonl", works=2)
    original = exp12.read_bytes()
    output = tmp_path / "joined.jsonl"
    monkeypatch.setattr(suggestions_cli, "session_records", lambda **_: (records, left_out))
    db_url = f"sqlite:///{(tmp_path / 'empty.db').as_posix()}"
    create_schema(create_engine_for_url(db_url))
    command = ["suggestions", "build-dataset", "--corpus", str(exp12), "--output", str(output)]
    assert main([*command, "--db-url", db_url, "--split-seed", str(SPLIT_SEED)]) == 0
    assert exp12.read_bytes() == original
    assert output.read_bytes().startswith(original)
    assert len(json_lines(output)) == len(json_lines(exp12)) + len(records)
    # La salida nunca es el corpus de exp_12.
    assert main([*command[:-1], str(exp12), "--db-url", db_url, "--split-seed", "1"]) == 1


def json_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_an_accidental_in_an_incomplete_measure_counts_as_unseen_by_the_rules(
    tmp_path: Path,
) -> None:
    """measure.balance propone cambiar la figura de cada evento del compás, no su alteración:
    el Si natural de un compás incompleto es un error que las reglas no ven (enmienda 4)."""
    config = load_suggestions_config(small_config(tmp_path / "config.json"))
    model = FrequencyBackoffModel(train(corpus_records(), config, dataset_hash="d"), version="v")

    def score_of(*pitches: str) -> ScoreIR:
        events = tuple(
            Event(kind=EventKind.NOTE, pitch=p, duration_beats=Fraction(1)) for p in pitches
        )
        measure = Measure(
            number=1,
            events=events,
            time_signature=TimeSignature(4, 4),
            key_signature=KeySignature(fifths=-1),
        )
        return ScoreIR(parts=(Part(id="P1", staves=(Staff(id="P1-S1", measures=(measure,)),)),))

    # Tres negras en 4/4 (incompleto en lo leído y en la verdad) con un Si natural en Fa mayor.
    records = build_correction_records(
        score_of("F4", "B4", "A4"),
        score_of("F4", "Bb4", "A4"),
        incipit_id="999999999-1_1_1",
        split="test",
        verified=True,
    )
    report = evaluate(model, records)
    assert report["rule_blind"]["errors"] >= 1
    assert report["rule_blind"]["flagged_with_correct_fix"] >= 1
