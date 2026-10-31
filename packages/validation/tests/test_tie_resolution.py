"""Pruebas de `tie.resolution`: ligadura sin cerrar (ADR-0040 §10)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from cadenza.domain import (
    Clef,
    Event,
    EventKind,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Severity,
    Staff,
    Tie,
    TimeSignature,
    build_anchor_index,
)
from cadenza.validation import TieResolutionRule, ValidationEngine


def _make_document(
    measures_events: list[tuple[Event, ...]],
    staff_id: str = "staff-0",
) -> ScoreDocument:
    measures = tuple(
        Measure(
            number=i + 1,
            events=events,
            time_signature=TimeSignature(4, 4),
            clef=Clef.treble(),
        )
        for i, events in enumerate(measures_events)
    )
    staff = Staff(id=staff_id, measures=measures)
    part = Part(id="part-0", staves=(staff,))
    score = ScoreIR(parts=(part,))
    return ScoreDocument(
        id="test-tie-doc",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="fake", model_version="1.0"),
    )


def test_rule_id() -> None:
    assert TieResolutionRule().rule_id == "tie.resolution"


def test_valid_ties_have_no_findings() -> None:
    # Compás 1: nota con START ligada a STOP en compás 2
    doc = _make_document(
        [
            (
                Event(
                    kind=EventKind.NOTE,
                    voice=0,
                    pitch="C4",
                    duration_beats=Fraction(4),
                    tie=Tie.START,
                ),
            ),
            (
                Event(
                    kind=EventKind.NOTE,
                    voice=0,
                    pitch="C4",
                    duration_beats=Fraction(4),
                    tie=Tie.STOP,
                ),
            ),
        ]
    )
    engine = ValidationEngine([TieResolutionRule()])
    assert engine.validate(doc) == []


def test_valid_three_note_tie_chain_has_no_findings() -> None:
    # START -> CONTINUE -> STOP
    doc = _make_document(
        [
            (
                Event(
                    kind=EventKind.NOTE,
                    voice=0,
                    pitch="G4",
                    duration_beats=Fraction(4),
                    tie=Tie.START,
                ),
            ),
            (
                Event(
                    kind=EventKind.NOTE,
                    voice=0,
                    pitch="G4",
                    duration_beats=Fraction(4),
                    tie=Tie.CONTINUE,
                ),
            ),
            (
                Event(
                    kind=EventKind.NOTE,
                    voice=0,
                    pitch="G4",
                    duration_beats=Fraction(4),
                    tie=Tie.STOP,
                ),
            ),
        ]
    )
    assert ValidationEngine([TieResolutionRule()]).validate(doc) == []


def _note(pitch: str, beats: int, tie: Tie | None = None, voice: int = 0) -> Event:
    return Event(
        kind=EventKind.NOTE, voice=voice, pitch=pitch, duration_beats=Fraction(beats), tie=tie
    )


def _texts(doc: ScoreDocument) -> list[tuple[int, int, str, str | None]]:
    return [
        (f.anchor.measure, f.anchor.event_index, f.message, f.suggested_fix)
        for f in ValidationEngine([TieResolutionRule()]).validate(doc)
    ]


def test_a_tie_leaving_the_last_measure_is_not_flagged() -> None:
    """Sigue en la página siguiente (ADR-0040 §10): antes se señalaba como «nunca cerrada»."""
    doc = _make_document([(_note("C4", 4),), (_note("C4", 4, Tie.START),)])
    assert ValidationEngine([TieResolutionRule()]).validate(doc) == []


def test_a_tie_ending_in_the_first_measure_is_not_flagged() -> None:
    """Viene de la página anterior."""
    doc = _make_document([(_note("D4", 4, Tie.STOP),), (_note("D4", 4),)])
    assert ValidationEngine([TieResolutionRule()]).validate(doc) == []


def test_unmatched_tie_stop_reports_warning() -> None:
    doc = _make_document([(_note("C4", 4),), (_note("D4", 4, Tie.STOP),), (_note("D4", 4),)])
    findings = ValidationEngine([TieResolutionRule()]).validate(doc)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "tie.resolution"
    assert f.severity == Severity.WARNING
    assert f.message == (
        "El Re del tiempo 1 termina una ligadura que no empieza en ninguna nota anterior."
    )
    assert f.suggested_fix == (
        "Revisa si la nota anterior es también un Re ligado; si no, la ligadura sobra."
    )


def test_unmatched_tie_continue_reports_warning() -> None:
    doc = _make_document(
        [(_note("C4", 4),), (_note("E4", 4, Tie.CONTINUE),), (_note("E4", 4, Tie.STOP),)]
    )
    assert [text[:2] for text in _texts(doc)] == [(2, 0)]


def test_rest_with_tie_reports_warning() -> None:
    doc = _make_document(
        [(Event(kind=EventKind.REST, voice=0, duration_beats=Fraction(4), tie=Tie.START),)]
    )
    findings = ValidationEngine([TieResolutionRule()]).validate(doc)
    assert len(findings) == 1
    assert findings[0].message == (
        "El silencio de redonda del tiempo 1 tiene una ligadura, y los silencios no se ligan."
    )


def test_a_tie_reaching_the_same_pitch_without_an_end_mark_is_resolved() -> None:
    """La ligadura está resuelta si la nota siguiente tiene su altura, aunque no lleve la marca
    de final (ADR-0040 §10): antes se señalaba como «interrumpida»."""
    doc = _make_document([(_note("C4", 4, Tie.START),), (_note("C4", 4),)])
    assert ValidationEngine([TieResolutionRule()]).validate(doc) == []


def test_a_tie_inside_the_measure_reaching_another_pitch() -> None:
    doc = _make_document([(_note("G4", 2, Tie.START), _note("A4", 2, Tie.STOP)), (_note("A4", 4),)])
    assert _texts(doc) == [
        (
            1,
            0,
            "La ligadura del Sol del tiempo 1 no llega a otro Sol: lo siguiente es un La.",
            "Si en la partitura une notas distintas, es una ligadura de expresión y este aviso "
            "se puede descartar; si no, revisa la altura del La.",
        )
    ]


def test_a_tie_into_a_chord_matches_the_note_of_its_pitch() -> None:
    chord = (
        _note("C4", 4),
        Event(kind=EventKind.NOTE, voice=0, pitch="E4", duration_beats=Fraction(4), is_chord=True),
    )
    doc = _make_document([(_note("E4", 4, Tie.START),), chord, (_note("C4", 4),)])
    assert ValidationEngine([TieResolutionRule()]).validate(doc) == []


def test_a_tie_across_the_barline_may_reach_another_voice() -> None:
    """Las voces se numeran desde 0 en cada compás (ADR-0032 §3)."""
    doc = _make_document(
        [
            (_note("C4", 4),),
            (_note("G4", 4, Tie.START, voice=0),),
            (_note("E5", 4, voice=0), _note("G4", 4, Tie.STOP, voice=1)),
            (_note("C4", 4),),
        ]
    )
    assert ValidationEngine([TieResolutionRule()]).validate(doc) == []


def test_a_tie_reaching_a_rest() -> None:
    doc = _make_document(
        [
            (_note("C4", 4),),
            (
                _note("G4", 2, Tie.START),
                Event(kind=EventKind.REST, voice=0, duration_beats=Fraction(2)),
            ),
            (_note("C4", 4),),
        ]
    )
    assert [text[2] for text in _texts(doc)] == [
        "La ligadura del Sol del tiempo 1 no llega a otro Sol: lo siguiente es un silencio."
    ]


def test_grace_notes_do_not_count() -> None:
    grace = Event(kind=EventKind.NOTE, voice=0, pitch="A4", duration_beats=Fraction(0))
    doc = _make_document(
        [(_note("C4", 4),), (_note("G4", 2, Tie.START), grace, _note("G4", 2)), (_note("C4", 4),)]
    )
    assert ValidationEngine([TieResolutionRule()]).validate(doc) == []


def test_rule_does_not_mutate_document(tmp_path: Path) -> None:
    doc = _make_document(
        [
            (
                Event(
                    kind=EventKind.NOTE,
                    voice=0,
                    pitch="C4",
                    duration_beats=Fraction(4),
                    tie=Tie.START,
                ),
            ),
        ]
    )
    snapshot = doc
    ValidationEngine([TieResolutionRule()]).validate(doc)
    assert doc == snapshot
