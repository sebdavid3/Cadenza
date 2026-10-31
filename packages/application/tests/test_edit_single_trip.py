"""Una edición en un solo viaje, con el estado en caché y medido por etapas (#275, ADR-0037)."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any

import pytest
from cadenza.application import (
    CachedScoreState,
    InMemoryEditEventRepository,
    InMemoryScoreExporter,
    InMemoryScoreStateCache,
    InMemorySessionRepository,
    InvalidEdit,
    Role,
    ScoreStateKey,
    SequenceConflict,
    SessionData,
    SessionStatus,
    User,
    append_edit,
    append_edit_with_state,
    collect_stage_timings,
    export_score,
    get_session,
    get_timing,
    timed_stage,
    undo_edit,
)
from cadenza.application import score_state as score_state_module
from cadenza.domain import (
    Anchor,
    Clef,
    EditEvent,
    EditOp,
    Event,
    EventKind,
    KeySignature,
    Measure,
    Part,
    ScoreIR,
    Staff,
    TimeSignature,
    compute_timing_map,
    materialize,
)

ANCHOR = Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="staff-1")


def _score() -> ScoreIR:
    events = (
        Event(kind=EventKind.NOTE, voice=0, pitch="C4", duration_beats=Fraction(1)),
        Event(kind=EventKind.NOTE, voice=0, pitch="D4", duration_beats=Fraction(1)),
        Event(kind=EventKind.REST, voice=0, duration_beats=Fraction(2)),
    )
    measure = Measure(
        number=1,
        time_signature=TimeSignature(4, 4),
        clef=Clef.treble(),
        key_signature=KeySignature(fifths=0, mode="major"),
        events=events,
    )
    return ScoreIR(parts=(Part(id="part-1", staves=(Staff(id="staff-1", measures=(measure,)),)),))


class _CountingExporter(InMemoryScoreExporter):
    """Exporta un MusicXML que dice qué estado es, y cuenta las exportaciones."""

    def to_musicxml(self, score: ScoreIR) -> str:
        super().to_musicxml(score)
        pitches = [e.pitch for e in score.parts[0].staves[0].measures[0].events]
        return f"<score-partwise>{pitches}</score-partwise>"


class _FailingExporter(InMemoryScoreExporter):
    def to_musicxml(self, score: ScoreIR) -> str:
        raise RuntimeError("music21 no pudo")


class _NoNextSeq(InMemoryEditEventRepository):
    """El `seq` de la edición nueva sale del log leído, sin otra consulta (#275)."""

    def next_seq(self, session_id: str) -> int:
        raise AssertionError("append_edit no debe pedir next_seq")


def _setup() -> tuple[InMemorySessionRepository, _NoNextSeq, User]:
    sessions = InMemorySessionRepository()
    edits = _NoNextSeq()
    sessions.add(
        SessionData(
            id="sess-1",
            document_id="doc-1",
            omr_engine="fake",
            document={"score": _score().to_primitive()},
            owner_id="user-1",
            status=SessionStatus.TRANSCRIBED,
        ),
        findings=(),
    )
    user = User(id="user-1", username="t1", password_hash="hash", role=Role.TRANSCRIPTOR)
    return sessions, edits, user


def _edit(
    sessions: InMemorySessionRepository,
    edits: InMemoryEditEventRepository,
    user: User,
    *,
    base_seq: int,
    op: EditOp = EditOp.SET_PITCH,
    after: dict[str, Any] | None = None,
    cache: InMemoryScoreStateCache | None = None,
    exporter: InMemoryScoreExporter | None = None,
) -> Any:
    return append_edit_with_state(
        "sess-1",
        anchor=ANCHOR,
        op=op,
        session_repository=sessions,
        edit_repository=edits,
        exporter=exporter or _CountingExporter(),
        current_user=user,
        base_seq=base_seq,
        after=after if after is not None else {"pitch": "G4"},
        score_cache=cache,
    )


def _materialized(edits: InMemoryEditEventRepository) -> ScoreIR:
    return materialize(_score(), edits.list_events("sess-1"))


# --- Caché del estado ------------------------------------------------------------------------


def test_cache_keeps_the_most_recent_entries_and_forgets_a_session() -> None:
    cache = InMemoryScoreStateCache(max_entries=2)
    state = CachedScoreState(score=_score())
    keys = [ScoreStateKey("s", seq, f"e{seq}") for seq in range(3)]
    for key in keys:
        cache.put(key, state)

    assert cache.get(keys[0]) is None
    assert cache.get(keys[1]) is state
    assert cache.get(keys[2]) is state

    cache.put(ScoreStateKey("otra", 1, "x"), state)
    cache.invalidate("s")
    assert cache.get(keys[2]) is None
    assert cache.get(ScoreStateKey("otra", 1, "x")) is state


def test_cache_with_no_room_stores_nothing() -> None:
    cache = InMemoryScoreStateCache(max_entries=0)
    cache.put(ScoreStateKey("s", 0, None), CachedScoreState(score=_score()))
    assert len(cache) == 0
    with pytest.raises(ValueError):
        InMemoryScoreStateCache(max_entries=-1)


def test_cache_is_safe_across_threads() -> None:
    cache = InMemoryScoreStateCache(max_entries=8)
    state = CachedScoreState(score=_score())

    def work(worker: int) -> None:
        for seq in range(200):
            key = ScoreStateKey(f"s{worker}", seq, None)
            cache.put(key, state)
            cache.get(key)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(cache) == 8


# --- Etapas ---------------------------------------------------------------------------------


def test_stages_add_up_inside_a_collection_and_do_nothing_outside() -> None:
    with timed_stage("db"):
        pass
    with collect_stage_timings() as timings:
        with timed_stage("db"):
            pass
        with timed_stage("db"):
            pass
        with timed_stage("export"):
            pass
    assert set(timings) == {"db", "export"}
    assert all(value >= 0 for value in timings.values())


def test_an_edit_reports_its_stages() -> None:
    sessions, edits, user = _setup()
    with collect_stage_timings() as timings:
        _edit(sessions, edits, user, base_seq=0, cache=InMemoryScoreStateCache())
    assert {"db", "materialize", "export", "timing"} <= set(timings)


# --- Un solo viaje --------------------------------------------------------------------------


def test_edit_returns_the_new_state_as_materialize_would() -> None:
    sessions, edits, user = _setup()
    exporter = _CountingExporter()

    applied = _edit(sessions, edits, user, base_seq=0, exporter=exporter)

    assert applied.edit.seq == 1
    assert applied.current_seq == 1
    assert applied.current_score == _materialized(edits)
    assert applied.musicxml == exporter.to_musicxml(_materialized(edits))
    assert applied.status == SessionStatus.CORRECTING
    assert edits.list_events("sess-1") == (applied.edit,)


def test_timing_is_returned_only_when_it_changes() -> None:
    sessions, edits, user = _setup()

    pitch = _edit(sessions, edits, user, base_seq=0)
    assert pitch.timing is None

    duration = _edit(
        sessions,
        edits,
        user,
        base_seq=1,
        op=EditOp.SET_DURATION,
        after={"duration_beats": "2"},
    )
    assert duration.timing == compute_timing_map(_materialized(edits))
    assert duration.timing != compute_timing_map(_score())


def test_edit_reuses_the_cached_state_and_never_rematerializes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions, edits, user = _setup()
    cache = InMemoryScoreStateCache()
    exporter = _CountingExporter()
    _edit(sessions, edits, user, base_seq=0, cache=cache, exporter=exporter)

    calls: list[int] = []
    real = score_state_module.materialize

    def counting(score: ScoreIR, log: Any) -> ScoreIR:
        calls.append(1)
        return real(score, log)

    monkeypatch.setattr(score_state_module, "materialize", counting)
    second = _edit(
        sessions, edits, user, base_seq=1, after={"pitch": "A4"}, cache=cache, exporter=exporter
    )

    assert calls == []
    assert second.current_score == _materialized(edits)
    # El detalle, la exportación y los tiempos de ese estado tampoco lo rehacen ni lo exportan.
    detail = get_session(
        "sess-1",
        session_repository=sessions,
        edit_repository=edits,
        current_user=user,
        include_anchor_index=False,
        score_cache=cache,
    )
    exported = export_score(
        sessions,
        edits,
        exporter,
        session_id="sess-1",
        format="musicxml",
        current_user=user,
        score_cache=cache,
    )
    timing = get_timing(
        "sess-1",
        session_repository=sessions,
        edit_repository=edits,
        current_user=user,
        score_cache=cache,
    )
    assert calls == []
    assert detail.current_score == second.current_score.to_primitive()
    assert detail.anchor_index is None
    assert exported.content == second.musicxml
    assert len(exporter.exported_scores) == 2
    assert timing == compute_timing_map(second.current_score)


def test_a_state_cached_by_an_edit_that_was_never_committed_is_not_used() -> None:
    sessions, edits, user = _setup()
    cache = InMemoryScoreStateCache()
    # Una edición validada cuya transacción se deshizo: su estado quedó en la caché con su id.
    ghost = materialize(
        _score(),
        (
            EditEvent(
                id="fantasma",
                document_id="doc-1",
                seq=1,
                anchor=ANCHOR,
                op=EditOp.SET_PITCH,
                author="t1",
                created_at=datetime.now(UTC),
                after={"pitch": "B4"},
            ),
        ),
    )
    cache.put(ScoreStateKey("sess-1", 1, "fantasma"), CachedScoreState(score=ghost))

    applied = _edit(sessions, edits, user, base_seq=0, after={"pitch": "G4"}, cache=cache)
    second = _edit(
        sessions,
        edits,
        user,
        base_seq=1,
        op=EditOp.SET_ACCIDENTAL,
        cache=cache,
        after={"accidental": "#"},
    )

    assert applied.edit.id != "fantasma"
    assert second.current_score == _materialized(edits)
    events = second.current_score.parts[0].staves[0].measures[0].events
    assert events[0].pitch == "G#4"


def test_the_edit_is_always_validated_even_with_a_cached_state() -> None:
    sessions, edits, user = _setup()
    cache = InMemoryScoreStateCache()
    _edit(sessions, edits, user, base_seq=0, cache=cache)

    with pytest.raises(InvalidEdit):
        _edit(sessions, edits, user, base_seq=1, after={"pitch": "no-es-una-altura"}, cache=cache)
    with pytest.raises(SequenceConflict):
        _edit(sessions, edits, user, base_seq=0, cache=cache)
    assert len(edits.list_events("sess-1")) == 1


def test_an_export_failure_does_not_undo_the_saved_edit() -> None:
    sessions, edits, user = _setup()

    applied = _edit(sessions, edits, user, base_seq=0, exporter=_FailingExporter())

    assert applied.musicxml is None
    assert edits.list_events("sess-1") == (applied.edit,)


def test_append_edit_keeps_returning_the_edit() -> None:
    sessions, edits, user = _setup()
    cache = InMemoryScoreStateCache()

    edit = append_edit(
        "sess-1",
        anchor=ANCHOR,
        op=EditOp.SET_PITCH,
        session_repository=sessions,
        edit_repository=edits,
        current_user=user,
        base_seq=0,
        after={"pitch": "E4"},
        score_cache=cache,
    )

    assert isinstance(edit, EditEvent)
    assert cache.get(ScoreStateKey("sess-1", 1, edit.id)) is not None


def test_undo_returns_the_new_state_with_its_musicxml_and_timing() -> None:
    sessions, edits, user = _setup()
    cache = InMemoryScoreStateCache()
    exporter = _CountingExporter()
    _edit(
        sessions,
        edits,
        user,
        base_seq=0,
        op=EditOp.SET_DURATION,
        after={"duration_beats": "2"},
        cache=cache,
    )

    result = undo_edit(
        "sess-1",
        session_repository=sessions,
        edit_repository=edits,
        current_user=user,
        base_seq=1,
        score_cache=cache,
        exporter=exporter,
    )

    assert result.current_seq == 2
    assert result.current_score == _score().to_primitive()
    assert result.musicxml == exporter.to_musicxml(_score())
    assert result.timing == compute_timing_map(_score())
    assert result.status == SessionStatus.CORRECTING
    assert cache.get(ScoreStateKey("sess-1", 2, result.compensatory_edit.id)) is not None


def test_undo_of_a_pitch_keeps_the_timing() -> None:
    sessions, edits, user = _setup()
    _edit(sessions, edits, user, base_seq=0)

    result = undo_edit(
        "sess-1",
        session_repository=sessions,
        edit_repository=edits,
        current_user=user,
        base_seq=1,
        exporter=_CountingExporter(),
    )

    assert result.timing is None
    assert result.anchor_index is not None


def test_detail_by_default_still_builds_the_anchor_index() -> None:
    sessions, edits, user = _setup()
    _edit(sessions, edits, user, base_seq=0)

    detail = get_session(
        "sess-1", session_repository=sessions, edit_repository=edits, current_user=user
    )

    assert detail.anchor_index is not None
    assert detail.current_seq == 1
    assert detail.current_score == _materialized(edits).to_primitive()
