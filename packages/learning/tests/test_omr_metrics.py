"""Pruebas de la métrica oficial OMR-NED (extra opcional `metrics`)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("musicdiff")

from cadenza.learning import OmrNedResult, omr_ned_pair

FIXTURE = Path(__file__).parent / "fixtures" / "simple.musicxml"


def test_identical_score_has_zero_omr_ned() -> None:
    result = omr_ned_pair(FIXTURE, FIXTURE)
    assert isinstance(result, OmrNedResult)
    assert result.omr_ned == 0.0
    assert result.edit_distance == 0
    assert result.predicted_symbols == result.ground_truth_symbols


def test_pitch_change_increases_omr_ned(tmp_path: Path) -> None:
    altered = tmp_path / "altered.musicxml"
    altered.write_text(
        FIXTURE.read_text(encoding="utf-8").replace("<step>C</step>", "<step>E</step>"),
        encoding="utf-8",
    )
    result = omr_ned_pair(altered, FIXTURE)
    assert result.omr_ned > 0.0
    assert result.edit_distance > 0
    assert result.to_primitive()["omr_ned"] == result.omr_ned
