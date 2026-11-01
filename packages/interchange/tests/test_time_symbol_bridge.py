"""El símbolo del compás (C y ¢) al importar y exportar MusicXML (ADR-0044, #236)."""

from __future__ import annotations

from fractions import Fraction

from cadenza.domain import (
    Event,
    EventKind,
    Measure,
    Part,
    ScoreIR,
    Staff,
    TimeSignature,
)
from cadenza.interchange import musicxml_to_score_ir, score_ir_to_musicxml


def _xml(time: str, measures: int = 2) -> str:
    attributes = (
        "<attributes><divisions>1</divisions>"
        + time
        + "<clef><sign>G</sign><line>2</line></clef></attributes>"
    )
    note = (
        "<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration>"
        "<type>whole</type></note>"
    )
    body = "".join(
        f'<measure number="{n}">{attributes if n == 1 else ""}{note}</measure>'
        for n in range(1, measures + 1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list>
  <part id="P1">{body}</part>
</score-partwise>"""


def _signatures(score: ScoreIR) -> list[TimeSignature | None]:
    return [m.time_signature for m in score.parts[0].staves[0].measures]


def _score(signatures: list[TimeSignature]) -> ScoreIR:
    measures = tuple(
        Measure(
            number=n,
            events=(Event(kind=EventKind.NOTE, pitch="C5", duration_beats=Fraction(4)),),
            time_signature=signature,
        )
        for n, signature in enumerate(signatures, start=1)
    )
    return ScoreIR(parts=(Part(id="part-0", staves=(Staff(id="s", measures=measures),)),))


def test_common_time_is_imported_with_its_symbol_in_every_measure() -> None:
    score = musicxml_to_score_ir(
        _xml('<time symbol="common"><beats>4</beats><beat-type>4</beat-type></time>')
    )
    signatures = _signatures(score)
    assert all(s is not None and s.same_notation(TimeSignature(4, 4, "common")) for s in signatures)


def test_cut_time_is_imported_with_its_symbol() -> None:
    score = musicxml_to_score_ir(
        _xml('<time symbol="cut"><beats>2</beats><beat-type>2</beat-type></time>', 1)
    )
    (signature,) = _signatures(score)
    assert signature is not None and signature.same_notation(TimeSignature(2, 2, "cut"))


def test_numbers_are_imported_without_symbol_as_before() -> None:
    score = musicxml_to_score_ir(_xml("<time><beats>4</beats><beat-type>4</beat-type></time>", 1))
    (signature,) = _signatures(score)
    assert signature is not None and signature.symbol is None
    assert score.parts[0].staves[0].measures[0].to_primitive()["time_signature"] == {
        "beats": 4,
        "beat_type": 4,
    }


def test_a_symbol_that_does_not_match_its_meter_is_left_out() -> None:
    score = musicxml_to_score_ir(
        _xml('<time symbol="common"><beats>3</beats><beat-type>4</beat-type></time>', 1)
    )
    (signature,) = _signatures(score)
    assert signature is not None and signature.same_notation(TimeSignature(3, 4))


def test_symbols_are_exported_and_survive_the_roundtrip() -> None:
    common = TimeSignature(4, 4, "common")
    cut = TimeSignature(2, 2, "cut")
    original = _score([common, common, cut, TimeSignature(4, 4)])
    xml = score_ir_to_musicxml(original)
    assert 'symbol="common"' in xml
    assert 'symbol="cut"' in xml
    reparsed = _signatures(musicxml_to_score_ir(xml))
    expected = _signatures(original)
    assert all(
        a is not None and a.same_notation(b) for a, b in zip(reparsed, expected, strict=True)
    )
    # Tres indicaciones escritas: C, ¢ y el 4/4 con números, aunque sea la métrica de C.
    assert xml.count("<time") == 3
