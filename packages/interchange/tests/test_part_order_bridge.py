"""Las partes se importan en el orden del MusicXML, también con un piano (#239, ADR-0060)."""

from __future__ import annotations

import re
from pathlib import Path

from cadenza.domain import ScoreIR
from cadenza.interchange import musicxml_to_score_ir, read_score, score_ir_to_musicxml

VOICE_PIANO = Path(__file__).parent / "fixtures" / "voice_piano.musicxml"


def _layout(score: ScoreIR) -> list[tuple[str, int, list[str | None]]]:
    """Cada parte con su id, su número de pentagramas y la primera altura de cada uno."""
    return [
        (
            part.id,
            len(part.staves),
            [staff.measures[0].events[0].pitch for staff in part.staves],
        )
        for part in score.parts
    ]


def _piano_first(text: str) -> str:
    """El mismo documento con la parte del piano antes que la de la voz."""
    voice = re.search(r'  <part id="P1">.*?</part>\n', text, re.S)
    piano = re.search(r'  <part id="P2">.*?</part>\n', text, re.S)
    assert voice is not None and piano is not None
    swapped = text.replace(voice.group(0), "@@VOICE@@").replace(piano.group(0), voice.group(0))
    swapped = swapped.replace("@@VOICE@@", piano.group(0))
    p1 = re.search(r'    <score-part id="P1">.*?</score-part>\n', swapped, re.S)
    p2 = re.search(r'    <score-part id="P2">.*?</score-part>\n', swapped, re.S)
    assert p1 is not None and p2 is not None
    return (
        swapped.replace(p1.group(0), "@@P1@@")
        .replace(p2.group(0), p1.group(0))
        .replace("@@P1@@", p2.group(0))
    )


def test_voice_above_piano_keeps_the_page_order() -> None:
    # Antes, el piano (un `StaffGroup` de music21) pasaba delante de la voz.
    score = musicxml_to_score_ir(VOICE_PIANO.read_text(encoding="utf-8"))

    assert _layout(score) == [("part-0", 1, ["A4"]), ("part-1", 2, ["E4", "C3"])]
    assert [staff.id for staff in score.parts[1].staves] == ["part-1-staff-0", "part-1-staff-1"]


def test_read_score_keeps_the_same_order() -> None:
    assert read_score(VOICE_PIANO) == musicxml_to_score_ir(VOICE_PIANO.read_text(encoding="utf-8"))


def test_piano_above_a_single_staff_keeps_that_order() -> None:
    score = musicxml_to_score_ir(_piano_first(VOICE_PIANO.read_text(encoding="utf-8")))

    assert _layout(score) == [("part-0", 2, ["E4", "C3"]), ("part-1", 1, ["A4"])]


def test_export_and_import_keep_the_voice_above_the_piano() -> None:
    score = musicxml_to_score_ir(VOICE_PIANO.read_text(encoding="utf-8"))

    exported = score_ir_to_musicxml(score)

    assert musicxml_to_score_ir(exported) == score
    voice, piano = exported.split('<part id="')[1:]
    assert "<staves>" not in voice
    assert "<staves>2</staves>" in piano
