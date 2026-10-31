"""Casos de uso con la capa de sugerencias (ADR-0036 §3, §4, §5, §11)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest
from cadenza.application import (
    Forbidden,
    InMemoryEditEventRepository,
    InMemorySessionRepository,
    InvalidEdit,
    Role,
    SequenceConflict,
    SessionClosed,
    SessionNotFound,
    StaleSuggestion,
    SuggestionConflict,
    SuggestionModel,
    SuggestionNotFound,
    User,
    append_edit,
    finalize_session,
    reject_suggestion,
    revalidate,
    transcribe_score,
)
from cadenza.domain import (
    Anchor,
    EditOp,
    Event,
    EventKind,
    Finding,
    KeySignature,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Severity,
    Staff,
    SuggestedEdit,
    SuggestedFinding,
    SuggestionResult,
    TimeSignature,
    build_anchor_index,
)
from cadenza.omr import OMREngine
from cadenza.validation import ValidationEngine

Repos = tuple[InMemorySessionRepository, InMemoryEditEventRepository]
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
STAFF = "P1-S1"


class ThreeQuartersEngine(OMREngine):
    """4/4 con tres negras: a measure.balance le falta una negra; el Si natural en Fa mayor
    es un error que las reglas no ven."""

    @property
    def engine_id(self) -> str:
        return "fake"

    def transcribe(self, image_path: Path) -> ScoreDocument:
        measures = (
            Measure(
                number=1,
                events=tuple(
                    Event(kind=EventKind.NOTE, pitch=p, duration_beats=Fraction(1))
                    for p in ("C4", "D4", "E4")
                ),
                time_signature=TimeSignature(4, 4),
                key_signature=KeySignature(fifths=-1),
            ),
            Measure(
                number=2,
                events=tuple(
                    Event(kind=EventKind.NOTE, pitch=p, duration_beats=Fraction(1))
                    for p in ("B4", "A4", "G4", "F4")
                ),
            ),
        )
        score = ScoreIR(parts=(Part(id="P1", staves=(Staff(id=STAFF, measures=measures),)),))
        return ScoreDocument(
            id="doc",
            score=score,
            anchors=build_anchor_index(score),
            provenance=Provenance(omr_engine="fake"),
        )


def _anchor(measure: int, index: int) -> Anchor:
    return Anchor(part=0, staff=0, measure=measure, voice=0, event_index=index, staff_id=STAFF)


class FakeModel:
    """Puntúa los candidatos por su orden inverso y señala el Si natural del compás 2."""

    version = "sug-fake"

    def __init__(self, *, invalid: bool = False) -> None:
        self.calls = 0
        self.invalid = invalid

    def suggest(self, document: ScoreDocument, findings: Sequence[Finding]) -> SuggestionResult:
        self.calls += 1
        ranked: list[SuggestedFinding] = []
        for finding in findings:
            candidates = list(reversed(finding.candidates))
            ranked.append(
                SuggestedFinding(
                    finding,
                    tuple(
                        replace(
                            c,
                            confidence=0.9 - 0.1 * i,
                            confidence_level="high",
                            explanation="Cuadra el compás.",
                            source="learned",
                            model_version=self.version,
                        )
                        for i, c in enumerate(candidates)
                    ),
                )
            )
        b_natural = _anchor(2, 0)
        after = {"accidental": "zz"} if self.invalid else {"accidental": "b"}
        learned = SuggestedFinding(
            Finding(
                anchor=b_natural,
                rule_id="learned.accidental",
                severity=Severity.WARNING,
                message="Puede que este Si sea Si♭: la armadura lo pide.",
            ),
            (
                SuggestedEdit(
                    op=EditOp.SET_ACCIDENTAL,
                    anchor=b_natural,
                    after=after,
                    confidence=0.8,
                    confidence_level="high",
                    explanation="Cambiar Si por Si♭.",
                    source="learned",
                    model_version=self.version,
                ),
            ),
        )
        return SuggestionResult(findings=(*ranked, learned))


@pytest.fixture
def owner() -> User:
    return User(id="u1", username="ana", password_hash="h", role=Role.TRANSCRIPTOR)


@pytest.fixture
def researcher() -> User:
    return User(id="u3", username="inv", password_hash="h", role=Role.INVESTIGADOR)


@pytest.fixture
def repos() -> Repos:
    edits = InMemoryEditEventRepository()
    return InMemorySessionRepository(edit_repository=edits), edits


def _transcribe(
    tmp_path: Path,
    sessions: InMemorySessionRepository,
    user: User,
    model: SuggestionModel | None,
    condition: str = "assisted",
) -> str:
    image = tmp_path / "page.png"
    image.write_bytes(PNG)
    result = transcribe_score(
        image,
        omr_engine=ThreeQuartersEngine(),
        validator=ValidationEngine(),
        session_repository=sessions,
        current_user=user,
        suggestion_model=model,
        condition=condition,
    )
    return result.session_id


def test_transcription_stores_ranked_suggestions_and_learned_findings(
    tmp_path: Path,
    repos: Repos,
    owner: User,
) -> None:
    sessions, _ = repos
    model = FakeModel()
    session_id = _transcribe(tmp_path, sessions, owner, model)
    findings = sessions.list_findings(session_id)
    balance = next(f for f in findings if f.rule_id == "measure.balance")
    learned = next(f for f in findings if f.rule_id == "learned.accidental")
    assert 1 <= len(balance.suggestions) <= 3
    assert [s.rank for s in balance.suggestions] == list(range(len(balance.suggestions)))
    # El servidor fija `before` con la instantánea del estado `at_seq` (ADR-0017).
    assert all(s.before is not None or s.op == "InsertEvent" for s in balance.suggestions)
    (fix,) = learned.suggestions
    assert (fix.op, fix.after, fix.before) == (
        "SetAccidental",
        {"accidental": "b"},
        {"accidental": ""},
    )
    assert fix.model_version == "sug-fake" and fix.response is None
    document = sessions.get(session_id)
    assert document is not None
    assert document.document["provenance"]["suggestions_version"] == "sug-fake"


def test_without_model_findings_carry_no_suggestions_not_even_rule_candidates(
    tmp_path: Path,
    repos: Repos,
    owner: User,
) -> None:
    sessions, _ = repos
    session_id = _transcribe(tmp_path, sessions, owner, None)
    findings = sessions.list_findings(session_id)
    assert [f.rule_id for f in findings] == ["measure.balance"]
    assert findings[0].suggestions == ()
    data = sessions.get(session_id)
    assert data is not None and "suggestions_version" not in data.document["provenance"]


def test_unassisted_runs_neither_rules_nor_layer(
    tmp_path: Path,
    repos: Repos,
    owner: User,
) -> None:
    sessions, edits = repos
    model = FakeModel()
    session_id = _transcribe(tmp_path, sessions, owner, model, condition="unassisted")
    revalidate(
        session_id,
        validator=ValidationEngine(),
        session_repository=sessions,
        edit_repository=edits,
        current_user=owner,
        suggestion_model=model,
    )
    assert model.calls == 0
    assert sessions.list_findings(session_id) == ()


def test_an_inadmissible_suggestion_is_dropped_with_its_learned_finding(
    tmp_path: Path,
    repos: Repos,
    owner: User,
) -> None:
    sessions, _ = repos
    session_id = _transcribe(tmp_path, sessions, owner, FakeModel(invalid=True))
    assert [f.rule_id for f in sessions.list_findings(session_id)] == ["measure.balance"]


def test_a_failing_layer_leaves_the_rule_findings_alone(
    tmp_path: Path,
    repos: Repos,
    owner: User,
) -> None:
    class Broken(FakeModel):
        def suggest(self, document: ScoreDocument, findings: Sequence[Finding]) -> SuggestionResult:
            raise RuntimeError("boom")

    sessions, _ = repos
    session_id = _transcribe(tmp_path, sessions, owner, Broken())
    findings = sessions.list_findings(session_id)
    assert [f.rule_id for f in findings] == ["measure.balance"]
    assert findings[0].suggestions == ()


def _apply(
    sessions: InMemorySessionRepository,
    edits: InMemoryEditEventRepository,
    user: User,
    session_id: str,
    suggestion_id: int,
    *,
    base_seq: int,
    after: dict[str, object] | None = None,
    anchor: Anchor | None = None,
) -> None:
    suggestion = sessions.get_suggestion(session_id, suggestion_id)
    assert suggestion is not None
    append_edit(
        session_id,
        anchor=anchor or Anchor.from_primitive(suggestion.anchor),
        op=EditOp(suggestion.op),
        after=after if after is not None else suggestion.after,
        base_seq=base_seq,
        session_repository=sessions,
        edit_repository=edits,
        current_user=user,
        suggestion_id=suggestion_id,
    )


def _learned_fix(sessions: InMemorySessionRepository, session_id: str) -> int:
    learned = next(f for f in sessions.list_findings(session_id) if f.rule_id.startswith("learned"))
    return learned.suggestions[0].id


def test_applying_a_suggestion_is_an_edit_of_the_person_and_marks_it_accepted(
    tmp_path: Path,
    repos: Repos,
    owner: User,
) -> None:
    sessions, edits = repos
    session_id = _transcribe(tmp_path, sessions, owner, FakeModel())
    sid = _learned_fix(sessions, session_id)
    _apply(sessions, edits, owner, session_id, sid, base_seq=0)
    (edit,) = edits.list_events(session_id)
    assert edit.author == "ana" and edit.op is EditOp.SET_ACCIDENTAL
    accepted = sessions.get_suggestion(session_id, sid)
    assert accepted is not None
    assert (accepted.response, accepted.responded_by, accepted.applied_seq) == (
        "accepted",
        "ana",
        1,
    )


def test_apply_checks_base_seq_then_staleness_then_the_proposal(
    tmp_path: Path,
    repos: Repos,
    owner: User,
) -> None:
    sessions, edits = repos
    session_id = _transcribe(tmp_path, sessions, owner, FakeModel())
    sid = _learned_fix(sessions, session_id)
    # 1. base_seq manda: aunque la sugerencia no exista, es un conflicto de secuencia.
    with pytest.raises(SequenceConflict):
        _apply(sessions, edits, owner, session_id, sid, base_seq=7)
    # 2. Una sugerencia que no existe o ya respondida: antigua.
    with pytest.raises(StaleSuggestion):
        append_edit(
            session_id,
            anchor=_anchor(2, 0),
            op=EditOp.SET_ACCIDENTAL,
            after={"accidental": "b"},
            base_seq=0,
            session_repository=sessions,
            edit_repository=edits,
            current_user=owner,
            suggestion_id=999,
        )
    # 3. Una edición que no es la propuesta: 422.
    with pytest.raises(InvalidEdit):
        _apply(sessions, edits, owner, session_id, sid, base_seq=0, after={"accidental": "#"})
    with pytest.raises(InvalidEdit):
        _apply(sessions, edits, owner, session_id, sid, base_seq=0, anchor=_anchor(2, 1))
    assert edits.list_events(session_id) == ()
    # La propuesta se compara normalizada: «-» es «b».
    _apply(sessions, edits, owner, session_id, sid, base_seq=0, after={"accidental": "-"})
    # Ya respondida: antigua; y una sugerencia de una validación anterior a base_seq, también.
    with pytest.raises(StaleSuggestion):
        _apply(sessions, edits, owner, session_id, sid, base_seq=1)
    balance = next(f for f in sessions.list_findings(session_id) if f.rule_id == "measure.balance")
    with pytest.raises(StaleSuggestion):
        _apply(sessions, edits, owner, session_id, balance.suggestions[0].id, base_seq=1)


def test_rejecting_a_suggestion(
    tmp_path: Path,
    repos: Repos,
    owner: User,
    researcher: User,
) -> None:
    sessions, edits = repos
    session_id = _transcribe(tmp_path, sessions, owner, FakeModel())
    balance = next(f for f in sessions.list_findings(session_id) if f.rule_id == "measure.balance")
    sid = balance.suggestions[0].id
    with pytest.raises(Forbidden):
        reject_suggestion(session_id, sid, session_repository=sessions, current_user=researcher)
    other = User(id="u2", username="otro", password_hash="h", role=Role.TRANSCRIPTOR)
    with pytest.raises(SessionNotFound):
        reject_suggestion(session_id, sid, session_repository=sessions, current_user=other)
    with pytest.raises(SuggestionNotFound):
        reject_suggestion(session_id, 999, session_repository=sessions, current_user=owner)
    rejected = reject_suggestion(session_id, sid, session_repository=sessions, current_user=owner)
    assert (rejected.response, rejected.responded_by) == ("rejected", "ana")
    # Rechazar no descarta el hallazgo.
    assert any(f.id == balance.id for f in sessions.list_findings(session_id))
    # Aceptada: 409.
    accepted = _learned_fix(sessions, session_id)
    _apply(sessions, edits, owner, session_id, accepted, base_seq=0)
    with pytest.raises(SuggestionConflict):
        reject_suggestion(session_id, accepted, session_repository=sessions, current_user=owner)
    # Una de una validación anterior: 200, como descartar.
    assert (
        reject_suggestion(
            session_id, balance.suggestions[1].id, session_repository=sessions, current_user=owner
        ).response
        == "rejected"
    )
    finalize_session(
        session_id,
        validator=ValidationEngine(),
        session_repository=sessions,
        edit_repository=edits,
        current_user=owner,
    )
    with pytest.raises(SessionClosed):
        reject_suggestion(session_id, sid, session_repository=sessions, current_user=owner)


def _suggestion_key(s: object) -> tuple[str, int, str]:
    return (s.op, s.anchor["event_index"], str(s.after))  # type: ignore[attr-defined]


def test_revalidation_inherits_rejections_only_from_the_current_validation(
    tmp_path: Path,
    repos: Repos,
    owner: User,
) -> None:
    sessions, edits = repos
    model = FakeModel()
    session_id = _transcribe(tmp_path, sessions, owner, model)
    balance = next(f for f in sessions.list_findings(session_id) if f.rule_id == "measure.balance")
    rejected = balance.suggestions[0]
    reject_suggestion(session_id, rejected.id, session_repository=sessions, current_user=owner)

    def run() -> None:
        revalidate(
            session_id,
            validator=ValidationEngine(),
            session_repository=sessions,
            edit_repository=edits,
            current_user=owner,
            suggestion_model=model,
        )

    run()  # misma secuencia: la respuesta se conserva y se hereda
    again = next(f for f in sessions.list_findings(session_id) if f.rule_id == "measure.balance")
    same = next(s for s in again.suggestions if _suggestion_key(s) == _suggestion_key(rejected))
    assert same.id != rejected.id and same.response == "rejected"
    # La respuesta original no se pierde: queda desvinculada.
    original = sessions.get_suggestion(session_id, rejected.id)
    assert original is not None and original.finding_id is None
    assert original.response == "rejected"
    assert model.calls == 2

    # Una edición en otro compás no toca el evento: se sigue heredando.
    sid = _learned_fix(sessions, session_id)
    _apply(sessions, edits, owner, session_id, sid, base_seq=0)
    run()
    later = next(f for f in sessions.list_findings(session_id) if f.rule_id == "measure.balance")
    assert any(
        s.response == "rejected"
        for s in later.suggestions
        if _suggestion_key(s) == _suggestion_key(rejected)
    )


def test_a_rejection_is_not_inherited_after_editing_its_event(
    tmp_path: Path,
    repos: Repos,
    owner: User,
) -> None:
    sessions, edits = repos
    model = FakeModel()
    session_id = _transcribe(tmp_path, sessions, owner, model)
    balance = next(f for f in sessions.list_findings(session_id) if f.rule_id == "measure.balance")
    target = next(s for s in balance.suggestions if s.op == "SetDuration")
    reject_suggestion(session_id, target.id, session_repository=sessions, current_user=owner)
    append_edit(
        session_id,
        anchor=Anchor.from_primitive(target.anchor),
        op=EditOp.SET_PITCH,
        after={"pitch": "G4"},
        base_seq=0,
        session_repository=sessions,
        edit_repository=edits,
        current_user=owner,
    )
    revalidate(
        session_id,
        validator=ValidationEngine(),
        session_repository=sessions,
        edit_repository=edits,
        current_user=owner,
        suggestion_model=model,
    )
    again = next(f for f in sessions.list_findings(session_id) if f.rule_id == "measure.balance")
    assert all(s.response is None for s in again.suggestions)


def test_finalize_runs_the_layer_and_inherits_rejections(
    tmp_path: Path,
    repos: Repos,
    owner: User,
) -> None:
    sessions, edits = repos
    model = FakeModel()
    session_id = _transcribe(tmp_path, sessions, owner, model)
    balance = next(f for f in sessions.list_findings(session_id) if f.rule_id == "measure.balance")
    reject_suggestion(
        session_id, balance.suggestions[0].id, session_repository=sessions, current_user=owner
    )
    result = finalize_session(
        session_id,
        validator=ValidationEngine(),
        session_repository=sessions,
        edit_repository=edits,
        current_user=owner,
        suggestion_model=model,
    )
    assert model.calls == 2
    final_balance = next(f for f in result.findings if f.rule_id == "measure.balance")
    assert final_balance.suggestions[0].response == "rejected"
    assert any(f.rule_id == "learned.accidental" for f in result.findings)


def test_suggestion_registry_keeps_a_single_promoted_version() -> None:
    from cadenza.application import InMemorySuggestionModelRegistry, SuggestionModelVersionData

    registry = InMemorySuggestionModelRegistry()
    for name in ("s1", "s2"):
        registry.register(
            SuggestionModelVersionData(
                version=name,
                artifact_hash="a" * 64,
                dataset_hash="d" * 64,
                config_hash="c" * 64,
                seed=7,
                model_type="frequency_backoff",
                feature_version=1,
                metrics={"families": {}},
            )
        )
    with pytest.raises(ValueError):
        registry.register(registry.versions()[0])
    assert registry.active() is None
    registry.promote("s1")
    registry.promote("s2")
    active = registry.active()
    assert active is not None and active.version == "s2"
    assert [v.promoted for v in registry.versions()] == [False, True]
    with pytest.raises(KeyError):
        registry.promote("nope")


def test_the_validation_layer_model_satisfies_the_port() -> None:
    from cadenza.validation.learned import FrequencyBackoffModel

    def accepts(model: SuggestionModel) -> str:
        return model.version

    artifact = {
        "format": "cadenza.suggestions",
        "format_version": 1,
        "model_type": "frequency_backoff",
        "feature_version": 1,
        "params": {},
        "families": {},
    }
    assert accepts(FrequencyBackoffModel(artifact, version="v1")) == "v1"
