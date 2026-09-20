"""Validación del adaptador determinista `FakeOMREngine`."""

from __future__ import annotations

from pathlib import Path

from cadenza.domain import EventKind, ScoreDocument
from cadenza.omr import FakeOMREngine


def _fake_document(tmp_path: Path) -> ScoreDocument:
    return FakeOMREngine().transcribe(tmp_path / "missing.png")


def test_returns_score_document(tmp_path: Path) -> None:
    document = _fake_document(tmp_path)
    assert isinstance(document, ScoreDocument)
    assert document.id == "fake-doc-0001"
    assert document.provenance.omr_engine == "fake"


def test_anchor_index_covers_all_events(tmp_path: Path) -> None:
    document = _fake_document(tmp_path)
    assert len(document.anchors) == 4
    for anchor, event in document.anchors.items():
        assert document.anchors.get(anchor) is event
        assert anchor.staff_id == "part-0-staff-0"


def test_expected_structure(tmp_path: Path) -> None:
    document = _fake_document(tmp_path)
    staff = document.score.parts[0].staves[0]
    assert [measure.number for measure in staff.measures] == [1, 2]
    first_measure = staff.measures[0]
    assert [event.kind for event in first_measure.events] == [
        EventKind.NOTE,
        EventKind.NOTE,
        EventKind.REST,
    ]
    assert first_measure.events[0].pitch == "C4"


def test_transcription_is_deterministic(tmp_path: Path) -> None:
    engine = FakeOMREngine()
    assert engine.transcribe(tmp_path / "a.png") == engine.transcribe(tmp_path / "b.png")
