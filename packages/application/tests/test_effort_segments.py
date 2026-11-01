"""El registro de esfuerzo que acumula la web (#188, ADR-0050, protocolo §3.4).

Un solo registro por sesión: el tiempo lo miden las pestañas por tramos (uno por pestaña, que
sobrevive a las recargas) y el servidor los suma; las intervenciones salen del log, por compás y
por clase; los descartes y las restauraciones se cuentan al guardarse, y las sugerencias
aplicadas y rechazadas, de sus respuestas guardadas.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cadenza.application import (
    ACCEPTED,
    REJECTED,
    EffortMetricsData,
    EffortSegment,
    Forbidden,
    InMemoryEditEventRepository,
    InMemoryEffortRepository,
    InMemorySessionRepository,
    InvalidEffortSegment,
    NewSuggestion,
    Role,
    SessionClosed,
    SessionData,
    SessionNotFound,
    SessionStatus,
    User,
    append_edit,
    dismiss_finding,
    effort_class,
    finalize_session,
    interventions_by_class,
    record_effort_segment,
    reopen_session,
    restore_finding,
    time_to_first_edit_ms,
)
from cadenza.domain import Anchor, EditEvent, EditOp, Finding, Severity, SuggestedEdit
from cadenza.omr.testing import FakeOMREngine
from cadenza.validation import ValidationEngine

SESSION = "s-1"
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def _user(user_id: str, role: Role = Role.TRANSCRIPTOR) -> User:
    return User(id=user_id, username=user_id, password_hash="h", role=role, active=True)


OWNER = _user("owner")


def _anchor(measure: int) -> Anchor:
    return Anchor(
        part=0, staff=0, measure=measure, voice=0, event_index=0, staff_id="part-0-staff-0"
    )


def _finding(measure: int) -> Finding:
    return Finding(
        rule_id="measure.balance",
        severity=Severity.WARNING,
        message="Compás incompleto",
        anchor=_anchor(measure),
    )


class Repos:
    def __init__(self) -> None:
        self.edits = InMemoryEditEventRepository()
        self.sessions = InMemorySessionRepository(edit_repository=self.edits)
        self.effort = InMemoryEffortRepository()
        self.sessions.add(
            SessionData(
                id=SESSION,
                document_id="doc-1",
                omr_engine="fake",
                document=FakeOMREngine().transcribe(Path("sin-imagen.png")).to_primitive(),
                owner_id=OWNER.id,
            ),
            findings=(_finding(1), _finding(2)),
        )

    def edit(self, measure: int, op: EditOp, *, reverts: str | None = None) -> EditEvent:
        seq = self.edits.next_seq(SESSION)
        return self.edits.append(
            SESSION,
            EditEvent(
                id=f"e{seq}",
                document_id="doc-1",
                seq=seq,
                anchor=_anchor(measure),
                op=op,
                author=OWNER.username,
                created_at=NOW,
                reverts_edit_id=reverts,
            ),
        )

    def pitch(self, measure: int) -> None:
        """Una corrección de verdad, que se puede materializar al finalizar."""
        append_edit(
            SESSION,
            anchor=_anchor(measure),
            op=EditOp.SET_PITCH,
            after={"pitch": "G4"},
            base_seq=len(self.edits.list_events(SESSION)),
            session_repository=self.sessions,
            edit_repository=self.edits,
            current_user=OWNER,
        )

    def segment(
        self,
        segment_id: str,
        active_ms: int,
        first_edit_ms: int | None = None,
        *,
        user: User = OWNER,
        idle_threshold_ms: int | None = 120_000,
    ) -> object:
        return record_effort_segment(
            SESSION,
            segment_id,
            active_ms=active_ms,
            first_edit_ms=first_edit_ms,
            session_repository=self.sessions,
            edit_repository=self.edits,
            effort_repository=self.effort,
            current_user=user,
            idle_threshold_ms=idle_threshold_ms,
            now=NOW,
        )

    def finalize(self) -> None:
        finalize_session(
            SESSION,
            validator=ValidationEngine([]),
            session_repository=self.sessions,
            edit_repository=self.edits,
            current_user=OWNER,
            effort_repository=self.effort,
        )

    def record(self) -> EffortMetricsData:
        record = self.effort.get_accumulated(SESSION)
        assert record is not None
        return record


@pytest.fixture
def repos() -> Repos:
    return Repos()


# --- El tiempo, por tramos -----------------------------------------------------------------


def test_the_first_segment_creates_the_single_record(repos: Repos) -> None:
    repos.segment("tab-a", 12_000)

    record = repos.record()
    assert record.accumulated is True
    assert record.duration_ms == 12_000
    assert record.segments == (EffortSegment("tab-a", 12_000, None, 120_000),)
    assert record.updated_at == NOW
    assert len(repos.effort.list_by_session(SESSION)) == 1


def test_a_segment_only_grows_and_a_late_lower_value_changes_nothing(repos: Repos) -> None:
    repos.segment("tab-a", 12_000)
    repos.segment("tab-a", 30_000)
    # Una petición anterior que llega tarde (o repetida) no resta nada.
    repos.segment("tab-a", 20_000)

    assert repos.record().duration_ms == 30_000
    assert len(repos.effort.list_by_session(SESSION)) == 1


def test_segments_from_several_loads_add_up_in_the_same_record(repos: Repos) -> None:
    repos.segment("tab-a", 30_000)
    repos.segment("tab-b", 9_000)

    record = repos.record()
    assert record.duration_ms == 39_000
    assert [s.id for s in record.segments] == ["tab-a", "tab-b"]
    assert len(repos.effort.list_by_session(SESSION)) == 1


def test_time_to_first_edit_adds_the_segments_before_the_first_edit(repos: Repos) -> None:
    repos.segment("tab-a", 30_000)
    repos.segment("tab-b", 9_000, first_edit_ms=5_000)

    assert repos.record().time_to_first_edit_ms == 35_000


def test_the_first_edit_is_kept_once_known(repos: Repos) -> None:
    repos.segment("tab-a", 9_000, first_edit_ms=5_000)
    repos.segment("tab-a", 12_000, first_edit_ms=11_000)
    repos.segment("tab-a", 14_000)

    record = repos.record()
    assert record.segments == (EffortSegment("tab-a", 14_000, 5_000, 120_000),)
    assert record.time_to_first_edit_ms == 5_000


def test_without_a_first_edit_the_latency_is_unknown(repos: Repos) -> None:
    repos.segment("tab-a", 9_000)

    assert repos.record().time_to_first_edit_ms is None
    assert time_to_first_edit_ms(()) is None


@pytest.mark.parametrize(
    ("active_ms", "first_edit_ms"),
    [(-1, None), (1_000, 1_001), (1_000, -1)],
)
def test_an_impossible_segment_is_refused(
    repos: Repos, active_ms: int, first_edit_ms: int | None
) -> None:
    with pytest.raises(InvalidEffortSegment):
        repos.segment("tab-a", active_ms, first_edit_ms)
    assert repos.effort.get_accumulated(SESSION) is None


def test_the_segment_keeps_the_last_idle_threshold_it_was_told(repos: Repos) -> None:
    repos.segment("tab-a", 1_000, idle_threshold_ms=120_000)
    repos.segment("tab-a", 2_000, idle_threshold_ms=None)
    assert repos.record().segments[0].idle_threshold_ms == 120_000
    repos.segment("tab-a", 3_000, idle_threshold_ms=180_000)
    assert repos.record().segments[0].idle_threshold_ms == 180_000
    with pytest.raises(InvalidEffortSegment):
        repos.segment("tab-a", 4_000, idle_threshold_ms=0)


@pytest.mark.parametrize("segment_id", ["", "x" * 65, "tab a", "tab/a"])
def test_a_segment_id_must_be_short_and_plain(repos: Repos, segment_id: str) -> None:
    with pytest.raises(InvalidEffortSegment):
        repos.segment(segment_id, 1_000)


def test_the_total_cannot_overflow_the_column(repos: Repos) -> None:
    repos.segment("tab-a", 2**31 - 1)
    with pytest.raises(InvalidEffortSegment):
        repos.segment("tab-b", 1)
    assert repos.record().duration_ms == 2**31 - 1


def test_the_number_of_segments_is_bounded(repos: Repos, monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("cadenza.application.use_cases.record_effort_segment")
    monkeypatch.setattr(module, "MAX_EFFORT_SEGMENTS", 2)
    repos.segment("tab-a", 1)
    repos.segment("tab-b", 1)
    repos.segment("tab-b", 2)  # el mismo tramo no cuenta como otro
    with pytest.raises(InvalidEffortSegment):
        repos.segment("tab-c", 1)


# --- Quién y cuándo ------------------------------------------------------------------------


def test_only_the_owner_measures(repos: Repos) -> None:
    with pytest.raises(SessionNotFound):
        repos.segment("tab-a", 1_000, user=_user("other"))
    with pytest.raises(Forbidden):
        repos.segment("tab-a", 1_000, user=_user("inv", Role.INVESTIGADOR))
    with pytest.raises(SessionNotFound):
        record_effort_segment(
            "missing",
            "tab-a",
            active_ms=1,
            first_edit_ms=None,
            session_repository=repos.sessions,
            edit_repository=repos.edits,
            effort_repository=repos.effort,
            current_user=OWNER,
        )
    assert repos.effort.get_accumulated(SESSION) is None


def test_a_finalized_session_takes_no_more_time(repos: Repos) -> None:
    repos.segment("tab-a", 10_000)
    repos.finalize()

    with pytest.raises(SessionClosed):
        repos.segment("tab-a", 20_000)
    assert repos.record().duration_ms == 10_000


def test_reopening_keeps_accumulating_in_the_same_record(repos: Repos) -> None:
    repos.segment("tab-a", 10_000)
    repos.pitch(1)
    repos.finalize()
    reopen_session(
        SESSION,
        session_repository=repos.sessions,
        edit_repository=repos.edits,
        current_user=OWNER,
    )
    repos.segment("tab-a", 25_000)
    repos.pitch(2)
    repos.finalize()

    record = repos.record()
    assert record.duration_ms == 25_000
    assert record.interventions == {"1": 1, "2": 1}
    assert len(repos.effort.list_by_session(SESSION)) == 1
    session = repos.sessions.get(SESSION)
    assert session is not None and session.status == SessionStatus.FINALIZED


# --- Las intervenciones, del log -----------------------------------------------------------


def test_every_saved_edit_counts_in_the_measure_of_its_anchor_by_class(repos: Repos) -> None:
    first = repos.edit(1, EditOp.SET_PITCH)
    repos.edit(1, EditOp.SET_PITCH, reverts=first.id)  # deshacer
    repos.edit(1, EditOp.SET_PITCH)  # rehacer: la misma edición, otra vez
    repos.edit(2, EditOp.SET_DYNAMIC)
    repos.edit(3, EditOp.SET_TIME)
    repos.edit(3, EditOp.SET_TUPLET)

    repos.segment("tab-a", 1_000)

    record = repos.record()
    assert record.interventions == {"1": 3, "2": 1, "3": 2}
    assert record.interventions_by_class == {
        "content": {"1": 3},
        "mark": {"2": 1},
        "meter": {"3": 2},
    }


def test_every_operation_has_a_class() -> None:
    assert {effort_class(op) for op in EditOp} == {"content", "mark", "meter"}
    assert effort_class(EditOp.SET_CHORD_DURATION) == "meter"
    assert effort_class(EditOp.SET_SLUR) == "mark"
    assert effort_class(EditOp.SET_KEY) == "content"


def test_interventions_by_class_has_the_three_classes_even_when_empty() -> None:
    assert interventions_by_class(()) == {"content": {}, "mark": {}, "meter": {}}


def test_finalizing_recounts_the_log(repos: Repos) -> None:
    repos.segment("tab-a", 1_000)
    repos.pitch(1)  # sin otro tramo después: lo recuenta finalizar

    repos.finalize()

    assert repos.record().interventions == {"1": 1}


def test_finalizing_without_a_record_creates_none(repos: Repos) -> None:
    repos.pitch(1)

    repos.finalize()

    assert repos.effort.get_accumulated(SESSION) is None


# --- Lo que se cuenta aparte ---------------------------------------------------------------


def test_dismissing_and_restoring_are_counted_when_they_change_something(repos: Repos) -> None:
    finding = repos.sessions.list_findings(SESSION)[0]

    def dismiss() -> None:
        dismiss_finding(
            SESSION,
            finding.id,
            session_repository=repos.sessions,
            current_user=OWNER,
            effort_repository=repos.effort,
        )

    def restore() -> None:
        restore_finding(
            SESSION,
            finding.id,
            session_repository=repos.sessions,
            current_user=OWNER,
            effort_repository=repos.effort,
        )

    dismiss()
    dismiss()  # ya estaba descartado: no es otra acción
    restore()
    restore()  # ya estaba activo
    dismiss()

    record = repos.record()
    assert (record.findings_dismissed, record.findings_restored) == (2, 1)
    # Sin tiempo medido todavía: el registro existe con lo que se contó.
    assert record.duration_ms == 0
    # Un tramo posterior no pisa los contadores.
    repos.segment("tab-a", 5_000)
    record = repos.record()
    assert (record.findings_dismissed, record.findings_restored) == (2, 1)
    assert record.duration_ms == 5_000


def test_applied_and_rejected_suggestions_come_from_their_stored_responses(repos: Repos) -> None:
    findings = repos.sessions.list_findings(SESSION)
    suggestion = NewSuggestion(
        SuggestedEdit(
            op=EditOp.SET_ACCIDENTAL,
            anchor=_anchor(1),
            after={"accidental": "#"},
            confidence=0.9,
            confidence_level="high",
            explanation="en 9 de 10 casos parecidos",
            source="learned",
            model_version="v1",
        )
    )
    repos.sessions.replace_findings(
        SESSION,
        [_finding(1), _finding(2)],
        at_seq=0,
        suggestions=[[suggestion], [suggestion]],
    )
    first, second = (
        s.id for s in repos.sessions.list_suggestions(SESSION) if s.finding_id is not None
    )
    assert findings  # hay posibles errores con sugerencias
    repos.sessions.respond_suggestion(
        SESSION, first, response=ACCEPTED, user="owner", applied_seq=1
    )
    repos.sessions.respond_suggestion(SESSION, second, response=REJECTED, user="owner")

    repos.segment("tab-a", 1_000)

    record = repos.record()
    assert (record.suggestions_applied, record.suggestions_rejected) == (1, 1)
