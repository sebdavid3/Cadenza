"""Finalizar conserva los descartes y no valida una sesión no asistida (#187, D65, ADR-0043).

Finalizar valida el estado final como una revalidación (ADR-0035 §13): hereda los descartes de
la validación vigente mientras su evento no cambie, y en una sesión `unassisted` no corren ni las
reglas ni la capa (ADR-0040 §13).
"""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from datetime import timedelta
from fractions import Fraction
from pathlib import Path

import pytest
from cadenza.application import (
    InMemoryArtifactStore,
    InMemoryEditEventRepository,
    InMemorySessionRepository,
    PersistedFinding,
    Role,
    SessionClosed,
    SessionStatus,
    User,
    append_edit,
    dismiss_finding,
    finalize_session,
    restore_finding,
    revalidate,
    transcribe_score,
)
from cadenza.domain import (
    Anchor,
    EditOp,
    Event,
    EventKind,
    Finding,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Staff,
    SuggestedFinding,
    SuggestionResult,
    TimeSignature,
    build_anchor_index,
)
from cadenza.omr import OMREngine
from cadenza.validation import MeasureBalanceRule, ValidationEngine

PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
STAFF = "part-0-staff-0"


class TwoShortMeasuresEngine(OMREngine):
    """Dos compases de 4/4 con tres negras: `measure.balance` señala los dos."""

    @property
    def engine_id(self) -> str:
        return "dummy-omr"

    def transcribe(self, image_path: Path) -> ScoreDocument:
        measures = tuple(
            Measure(
                number=number,
                events=tuple(
                    Event(kind=EventKind.NOTE, voice=0, pitch=p, duration_beats=Fraction(1))
                    for p in ("C4", "D4", "E4")
                ),
                time_signature=TimeSignature(4, 4),
            )
            for number in (1, 2)
        )
        score = ScoreIR(parts=(Part(id="part-0", staves=(Staff(id=STAFF, measures=measures),)),))
        return ScoreDocument(
            id="doc-finalize",
            score=score,
            anchors=build_anchor_index(score),
            provenance=Provenance(omr_engine=self.engine_id),
        )


class CountingValidator(ValidationEngine):
    """El validador de `measure.balance`, contando cuántas veces se ejecuta."""

    def __init__(self) -> None:
        super().__init__([MeasureBalanceRule()])
        self.calls = 0

    def validate(self, document: ScoreDocument) -> list[Finding]:
        self.calls += 1
        return super().validate(document)


class CountingModel:
    """Una capa que no propone nada, contando cuántas veces se ejecuta."""

    version = "sug-count"

    def __init__(self) -> None:
        self.calls = 0

    def suggest(self, document: ScoreDocument, findings: Sequence[Finding]) -> SuggestionResult:
        self.calls += 1
        return SuggestionResult(findings=tuple(SuggestedFinding(f, ()) for f in findings))


Repos = tuple[InMemorySessionRepository, InMemoryEditEventRepository]


@pytest.fixture
def owner() -> User:
    return User(
        id="user-owner",
        username="owner",
        password_hash="h",
        role=Role.TRANSCRIPTOR,
        active=True,
    )


@pytest.fixture
def repos() -> Repos:
    edits = InMemoryEditEventRepository()
    return InMemorySessionRepository(edit_repository=edits), edits


def _transcribe(
    sessions: InMemorySessionRepository,
    owner: User,
    validator: ValidationEngine,
    *,
    condition: str = "assisted",
) -> str:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(PNG_HEADER)
        image = Path(f.name)
    try:
        return transcribe_score(
            image,
            omr_engine=TwoShortMeasuresEngine(),
            validator=validator,
            session_repository=sessions,
            current_user=owner,
            artifact_store=InMemoryArtifactStore(),
            condition=condition,
        ).session_id
    finally:
        image.unlink(missing_ok=True)


def _finding_of(findings: Sequence[PersistedFinding], measure: int) -> PersistedFinding:
    return next(f for f in findings if f.anchor["measure"] == measure)


def _finalize(
    session_id: str,
    repos: Repos,
    owner: User,
    validator: ValidationEngine | None = None,
    model: CountingModel | None = None,
) -> tuple[PersistedFinding, ...]:
    sessions, edits = repos
    return finalize_session(
        session_id,
        validator=validator or ValidationEngine([MeasureBalanceRule()]),
        session_repository=sessions,
        edit_repository=edits,
        current_user=owner,
        suggestion_model=model,
    ).findings


def _set_pitch(
    repos: Repos,
    owner: User,
    session_id: str,
    measure: int,
    *,
    base_seq: int,
    after_dismissal: PersistedFinding,
) -> None:
    sessions, edits = repos
    assert after_dismissal.dismissed_at is not None
    append_edit(
        session_id,
        anchor=Anchor(part=0, staff=0, measure=measure, voice=0, event_index=0, staff_id=STAFF),
        op=EditOp.SET_PITCH,
        after={"pitch": "G4"},
        base_seq=base_seq,
        session_repository=sessions,
        edit_repository=edits,
        current_user=owner,
        # Posterior al descarte sin depender de la resolución del reloj.
        created_at=after_dismissal.dismissed_at + timedelta(seconds=1),
    )


def test_finalize_keeps_the_dismissals_of_the_current_validation(repos: Repos, owner: User) -> None:
    sessions, _ = repos
    session_id = _transcribe(sessions, owner, ValidationEngine([MeasureBalanceRule()]))
    first = _finding_of(sessions.list_findings(session_id), 1)
    dismiss_finding(
        session_id,
        first.id,
        session_repository=sessions,
        current_user=owner,
        reason="Es una anacrusa",
    )

    returned = _finalize(session_id, repos, owner)

    # La respuesta trae solo los activos, como `POST /validate` (ADR-0035).
    assert [f.anchor["measure"] for f in returned] == [2]
    stored = sessions.list_findings(session_id, include_dismissed=True)
    kept = _finding_of(stored, 1)
    assert kept.status == "dismissed"
    assert kept.dismissal_reason == "Es una anacrusa"
    assert kept.dismissed_by == "owner"
    assert _finding_of(stored, 2).status == "active"
    data = sessions.get(session_id)
    assert data is not None and data.status == SessionStatus.FINALIZED


def test_finalize_keeps_a_dismissal_when_another_measure_was_edited(
    repos: Repos, owner: User
) -> None:
    sessions, _ = repos
    session_id = _transcribe(sessions, owner, ValidationEngine([MeasureBalanceRule()]))
    first = _finding_of(sessions.list_findings(session_id), 1)
    dismissed = dismiss_finding(
        session_id, first.id, session_repository=sessions, current_user=owner
    )
    _set_pitch(repos, owner, session_id, 2, base_seq=0, after_dismissal=dismissed)

    returned = _finalize(session_id, repos, owner)

    assert [f.anchor["measure"] for f in returned] == [2]
    stored = sessions.list_findings(session_id, include_dismissed=True)
    assert all(f.at_seq == 1 for f in stored)
    assert _finding_of(stored, 1).status == "dismissed"


def test_finalize_reactivates_a_dismissal_whose_event_changed(repos: Repos, owner: User) -> None:
    sessions, _ = repos
    session_id = _transcribe(sessions, owner, ValidationEngine([MeasureBalanceRule()]))
    first = _finding_of(sessions.list_findings(session_id), 1)
    assert first.anchor["event_index"] == 0
    dismissed = dismiss_finding(
        session_id, first.id, session_repository=sessions, current_user=owner
    )
    _set_pitch(repos, owner, session_id, 1, base_seq=0, after_dismissal=dismissed)

    returned = _finalize(session_id, repos, owner)

    assert sorted(f.anchor["measure"] for f in returned) == [1, 2]


def test_finalize_does_not_bring_back_a_dismissal_restored_in_the_current_validation(
    repos: Repos, owner: User
) -> None:
    sessions, edits = repos
    session_id = _transcribe(sessions, owner, ValidationEngine([MeasureBalanceRule()]))
    first = _finding_of(sessions.list_findings(session_id), 1)
    dismissed = dismiss_finding(
        session_id, first.id, session_repository=sessions, current_user=owner
    )
    _set_pitch(repos, owner, session_id, 2, base_seq=0, after_dismissal=dismissed)
    revalidate(
        session_id,
        validator=ValidationEngine([MeasureBalanceRule()]),
        session_repository=sessions,
        edit_repository=edits,
        current_user=owner,
    )
    inherited = _finding_of(sessions.list_findings(session_id, include_dismissed=True), 1)
    assert inherited.status == "dismissed"
    restore_finding(session_id, inherited.id, session_repository=sessions, current_user=owner)

    returned = _finalize(session_id, repos, owner)

    # El descarte de la validación anterior es historia: la restauración manda (ADR-0035 §13).
    assert sorted(f.anchor["measure"] for f in returned) == [1, 2]


def test_finalize_an_unassisted_session_runs_neither_rules_nor_layer(
    repos: Repos, owner: User
) -> None:
    sessions, _ = repos
    validator = CountingValidator()
    model = CountingModel()
    session_id = _transcribe(sessions, owner, validator, condition="unassisted")
    assert validator.calls == 0

    returned = _finalize(session_id, repos, owner, validator, model)

    assert returned == ()
    assert validator.calls == 0
    assert model.calls == 0
    assert sessions.list_findings(session_id, include_dismissed=True) == ()
    data = sessions.get(session_id)
    assert data is not None
    assert data.status == SessionStatus.FINALIZED
    assert data.validated_at_seq == 0


def test_finalize_an_assisted_session_runs_rules_and_layer(repos: Repos, owner: User) -> None:
    sessions, _ = repos
    validator = CountingValidator()
    model = CountingModel()
    session_id = _transcribe(sessions, owner, validator)

    _finalize(session_id, repos, owner, validator, model)

    assert validator.calls == 2
    assert model.calls == 1


def test_finalize_a_finalized_session_raises_session_closed(repos: Repos, owner: User) -> None:
    sessions, _ = repos
    session_id = _transcribe(sessions, owner, ValidationEngine([MeasureBalanceRule()]))
    _finalize(session_id, repos, owner)
    final = sessions.list_findings(session_id, include_dismissed=True)
    validator = CountingValidator()

    with pytest.raises(SessionClosed):
        _finalize(session_id, repos, owner, validator)

    # La validación final no se rehace: ni corren las reglas ni cambian los id.
    assert validator.calls == 0
    assert sessions.list_findings(session_id, include_dismissed=True) == final
