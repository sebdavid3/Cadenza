"""Título, compositor e instrumentos de una sesión, y el nombre del archivo subido (#235).

ADR-0041: son datos de la sesión, no ediciones del log; los cambia solo el dueño, también con
la sesión finalizada; la exportación los recibe aparte, y cambiarlos invalida la caché del
estado (D66, ADR-0037).
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from fractions import Fraction
from pathlib import Path

import pytest
from cadenza.application import (
    UNCHANGED,
    CachedScoreState,
    Forbidden,
    InMemoryEditEventRepository,
    InMemoryScoreExporter,
    InMemoryScoreStateCache,
    InMemorySessionRepository,
    InvalidSessionMetadata,
    Role,
    ScoreStateKey,
    SessionData,
    SessionNotFound,
    SessionStatus,
    User,
    append_edit_with_state,
    export_score,
    get_session,
    list_sessions,
    transcribe_score,
    undo_edit,
    update_session_metadata,
)
from cadenza.application.score_state import musicxml_of
from cadenza.domain import (
    Anchor,
    EditOp,
    Event,
    EventKind,
    Instrument,
    Measure,
    Part,
    PartMetadata,
    ScoreIR,
    ScoreMetadata,
    Staff,
    TimeSignature,
)
from cadenza.omr.testing import FakeOMREngine
from cadenza.validation import ValidationEngine

PNG_SAMPLE = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
)
ANCHOR = Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="staff-1")
VOICE_AND_PIANO = ScoreMetadata(
    title="Mondnacht",
    composer="Robert Schumann",
    parts=(PartMetadata(Instrument.VOICE), PartMetadata(Instrument.PIANO)),
)


def _user(user_id: str, role: Role = Role.TRANSCRIPTOR) -> User:
    return User(id=user_id, username=user_id, password_hash="h", role=role, active=True)


OWNER = _user("owner")
OTHER = _user("other")
RESEARCHER = _user("researcher", Role.INVESTIGADOR)


def _score(parts: int = 2) -> ScoreIR:
    measure = Measure(
        number=1,
        time_signature=TimeSignature(beats=4, beat_type=4),
        events=(Event(kind=EventKind.NOTE, voice=0, pitch="C4", duration_beats=Fraction(4)),),
    )
    return ScoreIR(
        parts=tuple(
            Part(id=f"P{i + 1}", staves=(Staff(id=f"staff-{i + 1}", measures=(measure,)),))
            for i in range(parts)
        )
    )


def _repos(
    status: str = "transcribed", metadata: ScoreMetadata | None = None
) -> tuple[InMemorySessionRepository, InMemoryEditEventRepository]:
    edits = InMemoryEditEventRepository()
    sessions = InMemorySessionRepository(edit_repository=edits)
    sessions.add(
        SessionData(
            id="sess-1",
            document_id="doc-1",
            omr_engine="fake",
            document={"id": "doc-1", "score": _score().to_primitive()},
            owner_id=OWNER.id,
            status=status,
            metadata=metadata or ScoreMetadata(),
            source_filename="mondnacht.png",
        ),
        findings=[],
    )
    return sessions, edits


@pytest.fixture
def image() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "pagina.png"
        path.write_bytes(PNG_SAMPLE)
        yield path


# --- Al transcribir ---------------------------------------------------------------------------


def test_transcribe_keeps_metadata_and_source_filename(image: Path) -> None:
    sessions = InMemorySessionRepository()
    metadata = ScoreMetadata(title="Mondnacht", parts=(PartMetadata(Instrument.VOICE),))

    result = transcribe_score(
        image,
        omr_engine=FakeOMREngine(),
        validator=ValidationEngine([]),
        session_repository=sessions,
        current_user=OWNER,
        metadata=metadata,
        source_filename="C:\\fakepath\\Mondnacht p1.png",
    )

    stored = sessions.get(result.session_id)
    assert stored is not None
    assert stored.metadata == metadata
    assert stored.source_filename == "Mondnacht p1.png"


def test_transcribe_drops_instruments_of_parts_omr_did_not_find(image: Path) -> None:
    # FakeOMREngine detecta una sola parte: el piano de la segunda no tiene dónde ir.
    sessions = InMemorySessionRepository()

    result = transcribe_score(
        image,
        omr_engine=FakeOMREngine(),
        validator=ValidationEngine([]),
        session_repository=sessions,
        current_user=OWNER,
        metadata=VOICE_AND_PIANO,
    )

    stored = sessions.get(result.session_id)
    assert stored is not None
    assert stored.metadata.parts == (PartMetadata(Instrument.VOICE),)
    assert stored.metadata.title == "Mondnacht"


def test_transcribe_without_metadata_stores_nothing_new(image: Path) -> None:
    sessions = InMemorySessionRepository()
    result = transcribe_score(
        image,
        omr_engine=FakeOMREngine(),
        validator=ValidationEngine([]),
        session_repository=sessions,
        current_user=OWNER,
    )
    stored = sessions.get(result.session_id)
    assert stored is not None
    assert stored.metadata == ScoreMetadata()
    assert stored.source_filename is None


# --- Al leer ----------------------------------------------------------------------------------


def test_detail_and_list_return_metadata() -> None:
    sessions, edits = _repos(metadata=VOICE_AND_PIANO)

    detail = get_session(
        "sess-1", session_repository=sessions, edit_repository=edits, current_user=OWNER
    )
    assert detail.metadata == VOICE_AND_PIANO
    assert detail.source_filename == "mondnacht.png"

    (summary,) = list_sessions(session_repository=sessions, current_user=OWNER)
    assert summary.metadata == VOICE_AND_PIANO
    assert summary.source_filename == "mondnacht.png"


# --- Cambiarlos después ------------------------------------------------------------------------


def test_owner_changes_only_what_is_given() -> None:
    sessions, _ = _repos(metadata=VOICE_AND_PIANO)

    updated = update_session_metadata(
        "sess-1", session_repository=sessions, current_user=OWNER, title="Mondnacht, Op. 39"
    )

    assert updated.metadata.title == "Mondnacht, Op. 39"
    assert updated.metadata.composer == "Robert Schumann"
    assert updated.metadata.parts == VOICE_AND_PIANO.parts
    stored = sessions.get("sess-1")
    assert stored is not None
    assert stored.metadata == updated.metadata


def test_none_clears_a_field() -> None:
    sessions, _ = _repos(metadata=VOICE_AND_PIANO)

    updated = update_session_metadata(
        "sess-1",
        session_repository=sessions,
        current_user=OWNER,
        composer=None,
        parts=(),
    )

    assert updated.metadata == ScoreMetadata(title="Mondnacht")


def test_change_is_not_an_edit_and_keeps_status() -> None:
    sessions, edits = _repos(status=SessionStatus.TRANSCRIBED.value)

    update_session_metadata(
        "sess-1",
        session_repository=sessions,
        current_user=OWNER,
        parts=(PartMetadata(Instrument.CELLO),),
    )

    assert edits.list_events("sess-1") == ()
    stored = sessions.get("sess-1")
    assert stored is not None
    assert stored.status == SessionStatus.TRANSCRIBED.value


def test_finalized_session_can_change_its_metadata() -> None:
    sessions, _ = _repos(status=SessionStatus.FINALIZED.value)

    updated = update_session_metadata(
        "sess-1", session_repository=sessions, current_user=OWNER, title="Otro nombre"
    )

    assert updated.metadata.title == "Otro nombre"
    assert updated.status == SessionStatus.FINALIZED.value


def test_other_transcriptor_does_not_see_the_session() -> None:
    sessions, _ = _repos()
    with pytest.raises(SessionNotFound):
        update_session_metadata(
            "sess-1", session_repository=sessions, current_user=OTHER, title="x"
        )


def test_researcher_cannot_change_others_session() -> None:
    sessions, _ = _repos()
    with pytest.raises(Forbidden):
        update_session_metadata(
            "sess-1", session_repository=sessions, current_user=RESEARCHER, title="x"
        )


def test_missing_session() -> None:
    sessions, _ = _repos()
    with pytest.raises(SessionNotFound):
        update_session_metadata("nope", session_repository=sessions, current_user=OWNER, title="x")


def test_more_parts_than_the_score_has_is_rejected() -> None:
    sessions, _ = _repos()
    with pytest.raises(InvalidSessionMetadata):
        update_session_metadata(
            "sess-1",
            session_repository=sessions,
            current_user=OWNER,
            parts=tuple(PartMetadata(Instrument.PIANO) for _ in range(3)),
        )
    stored = sessions.get("sess-1")
    assert stored is not None
    assert stored.metadata == ScoreMetadata()


def test_too_long_title_is_rejected() -> None:
    sessions, _ = _repos()
    with pytest.raises(InvalidSessionMetadata):
        update_session_metadata(
            "sess-1", session_repository=sessions, current_user=OWNER, title="x" * 201
        )


def test_change_invalidates_the_state_cache() -> None:
    # D66: el MusicXML cambia sin que cambie el `seq`; lo guardado de la sesión se olvida.
    sessions, _ = _repos()
    cache = InMemoryScoreStateCache()
    key = ScoreStateKey(session_id="sess-1", seq=0, last_edit_id=None)
    other = ScoreStateKey(session_id="sess-2", seq=0, last_edit_id=None)
    cache.put(key, CachedScoreState(score=_score(), musicxml="<viejo/>"))
    cache.put(other, CachedScoreState(score=_score(), musicxml="<otra/>"))

    update_session_metadata(
        "sess-1",
        session_repository=sessions,
        current_user=OWNER,
        title="Mondnacht",
        score_cache=cache,
    )

    assert cache.get(key) is None
    assert cache.get(other) is not None


def test_unchanged_is_the_default() -> None:
    sessions, _ = _repos(metadata=VOICE_AND_PIANO)
    updated = update_session_metadata(
        "sess-1",
        session_repository=sessions,
        current_user=OWNER,
        title=UNCHANGED,
        composer=UNCHANGED,
        parts=UNCHANGED,
    )
    assert updated.metadata == VOICE_AND_PIANO


# --- La exportación --------------------------------------------------------------------------


def test_cached_musicxml_is_only_reused_with_the_same_metadata() -> None:
    # Una exportación con los metadatos de antes que llegue a la caché después del cambio no se
    # sirve con los nuevos (ADR-0041 §5).
    exporter = InMemoryScoreExporter()
    cache = InMemoryScoreStateCache()
    key = ScoreStateKey(session_id="sess-1", seq=0, last_edit_id=None)
    state = CachedScoreState(score=_score())

    state, _ = musicxml_of(key, state, exporter, cache, VOICE_AND_PIANO)
    state, _ = musicxml_of(key, state, exporter, cache, VOICE_AND_PIANO)
    assert len(exporter.exported_scores) == 1

    musicxml_of(key, state, exporter, cache, ScoreMetadata(title="Otro"))
    assert exporter.exported_metadata == [VOICE_AND_PIANO, ScoreMetadata(title="Otro")]


def test_export_uses_the_session_metadata() -> None:
    sessions, edits = _repos(metadata=VOICE_AND_PIANO)
    exporter = InMemoryScoreExporter()

    for fmt in ("musicxml", "midi"):
        export_score(
            sessions,
            edits,
            exporter,
            session_id="sess-1",
            format=fmt,
            current_user=OWNER,
        )

    assert exporter.exported_metadata == [VOICE_AND_PIANO, VOICE_AND_PIANO]


def test_export_after_change_is_not_served_from_cache() -> None:
    sessions, edits = _repos()
    exporter = InMemoryScoreExporter()
    cache = InMemoryScoreStateCache()

    def export() -> None:
        export_score(
            sessions,
            edits,
            exporter,
            session_id="sess-1",
            format="musicxml",
            current_user=OWNER,
            score_cache=cache,
        )

    export()
    update_session_metadata(
        "sess-1",
        session_repository=sessions,
        current_user=OWNER,
        title="Mondnacht",
        score_cache=cache,
    )
    export()

    assert exporter.exported_metadata == [ScoreMetadata(), ScoreMetadata(title="Mondnacht")]


def test_edit_and_undo_export_with_the_session_metadata() -> None:
    sessions, edits = _repos(metadata=VOICE_AND_PIANO)
    exporter = InMemoryScoreExporter()
    cache = InMemoryScoreStateCache()

    applied = append_edit_with_state(
        "sess-1",
        anchor=ANCHOR,
        op=EditOp.SET_PITCH,
        after={"pitch": "D4"},
        session_repository=sessions,
        edit_repository=edits,
        exporter=exporter,
        current_user=OWNER,
        base_seq=0,
        score_cache=cache,
    )
    assert applied.musicxml is not None
    undo_edit(
        "sess-1",
        session_repository=sessions,
        edit_repository=edits,
        current_user=OWNER,
        base_seq=1,
        score_cache=cache,
        exporter=exporter,
    )

    assert exporter.exported_metadata == [VOICE_AND_PIANO, VOICE_AND_PIANO]
