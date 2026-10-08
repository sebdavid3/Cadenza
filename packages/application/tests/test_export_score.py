"""Pruebas unitarias del caso de uso export_score (Issue #12, ADR-0010, ADR-0012)."""

from __future__ import annotations

from fractions import Fraction

import pytest
from cadenza.application import (
    ExportedScore,
    ExportFormat,
    InMemoryEditEventRepository,
    InMemoryScoreExporter,
    InMemorySessionRepository,
    Role,
    SessionData,
    SessionNotFound,
    UnsupportedExportFormat,
    User,
    export_score,
)
from cadenza.domain import (
    Anchor,
    EditEvent,
    EditOp,
    Event,
    EventKind,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Staff,
    TimeSignature,
    build_anchor_index,
)


def _make_score(pitch: str = "C4") -> ScoreIR:
    return ScoreIR(
        parts=(
            Part(
                id="P1",
                staves=(
                    Staff(
                        id="staff-1",
                        measures=(
                            Measure(
                                number=1,
                                time_signature=TimeSignature(beats=4, beat_type=4),
                                events=(
                                    Event(
                                        kind=EventKind.NOTE,
                                        voice=0,
                                        pitch=pitch,
                                        duration_beats=Fraction(1),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
    )


def _make_setup() -> tuple[
    InMemorySessionRepository,
    InMemoryEditEventRepository,
    InMemoryScoreExporter,
    User,
    User,
    str,
]:
    session_repo = InMemorySessionRepository()
    edit_repo = InMemoryEditEventRepository()
    exporter = InMemoryScoreExporter()

    owner = User(
        id="user-owner",
        username="owner_user",
        password_hash="hash",
        role=Role.TRANSCRIPTOR,
        active=True,
    )
    other = User(
        id="user-other",
        username="other_transcriptor",
        password_hash="hash",
        role=Role.TRANSCRIPTOR,
        active=True,
    )

    score = _make_score("C4")
    doc = ScoreDocument(
        id="doc-1",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(source_image_hash="abc", omr_engine="fake"),
    )
    session_data = SessionData(
        id="sess-1",
        document_id="doc-1",
        omr_engine="fake",
        owner_id=owner.id,
        document=doc.to_primitive(),
    )
    session_repo.add(session_data, findings=[])
    return session_repo, edit_repo, exporter, owner, other, "sess-1"


def test_export_score_session_not_found() -> None:
    session_repo, edit_repo, exporter, owner, _, _ = _make_setup()
    with pytest.raises(SessionNotFound):
        export_score(
            session_repo,
            edit_repo,
            exporter,
            session_id="non-existent",
            format="musicxml",
            current_user=owner,
        )


def test_export_score_transcriptor_access_denied_on_other_session() -> None:
    session_repo, edit_repo, exporter, _, other, sid = _make_setup()
    # Transcriptor ajeno debe recibir SessionNotFound según ADR-0012
    with pytest.raises(SessionNotFound):
        export_score(
            session_repo,
            edit_repo,
            exporter,
            session_id=sid,
            format="musicxml",
            current_user=other,
        )


def test_export_score_investigator_can_export_any_session() -> None:
    session_repo, edit_repo, exporter, _, _, sid = _make_setup()
    investigator = User(
        id="user-inv",
        username="inv_user",
        password_hash="hash",
        role=Role.INVESTIGADOR,
        active=True,
    )
    res = export_score(
        session_repo,
        edit_repo,
        exporter,
        session_id=sid,
        format="musicxml",
        current_user=investigator,
    )
    assert isinstance(res, ExportedScore)
    assert res.media_type == "application/vnd.recordare.musicxml+xml"
    assert res.filename == f"session-{sid}.musicxml"


def test_export_score_unsupported_format_raises_exception() -> None:
    session_repo, edit_repo, exporter, owner, _, sid = _make_setup()
    with pytest.raises(UnsupportedExportFormat) as exc_info:
        export_score(
            session_repo,
            edit_repo,
            exporter,
            session_id=sid,
            format="pdf",
            current_user=owner,
        )
    assert exc_info.value.format == "pdf"


def test_export_score_materializes_edits() -> None:
    session_repo, edit_repo, exporter, owner, _, sid = _make_setup()

    from datetime import UTC, datetime

    # Agregar una edición que cambia C4 -> D4
    edit = EditEvent(
        id="edit-1",
        document_id="doc-1",
        seq=1,
        author=owner.username,
        created_at=datetime.now(UTC),
        anchor=Anchor(
            part=0,
            staff=0,
            measure=1,
            voice=0,
            event_index=0,
            staff_id="part-0-staff-0",
        ),
        op=EditOp.SET_PITCH,
        before={"pitch": "C4"},
        after={"pitch": "D4"},
    )
    edit_repo.append(sid, edit)

    # Exportar MusicXML
    res_mxml = export_score(
        session_repo,
        edit_repo,
        exporter,
        session_id=sid,
        format=ExportFormat.MUSICXML,
        current_user=owner,
    )
    assert res_mxml.filename == f"session-{sid}.musicxml"
    assert len(exporter.exported_scores) == 1
    fmt, exported_ir = exporter.exported_scores[0]
    assert fmt == "musicxml"
    # El ScoreIR exportado debe tener la nota modificada a D4
    note_event = exported_ir.parts[0].staves[0].measures[0].events[0]
    assert note_event.pitch == "D4"

    # Exportar MIDI
    res_midi = export_score(
        session_repo,
        edit_repo,
        exporter,
        session_id=sid,
        format="midi",
        current_user=owner,
    )
    assert res_midi.media_type == "audio/midi"
    assert res_midi.filename == f"session-{sid}.mid"
    assert len(exporter.exported_scores) == 2
    fmt2, exported_ir2 = exporter.exported_scores[1]
    assert fmt2 == "midi"
    note_event2 = exported_ir2.parts[0].staves[0].measures[0].events[0]
    assert note_event2.pitch == "D4"
