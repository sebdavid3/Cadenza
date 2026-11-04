"""Marcas de notación del `ScoreIR`: valores, serialización y compatibilidad (ADR-0031, #213)."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
from pathlib import Path

import pytest
from cadenza.domain import (
    Articulation,
    Dynamic,
    DynamicMark,
    Event,
    EventKind,
    Measure,
    Part,
    ScoreDocument,
    ScoreIR,
    Slur,
    SlurType,
    Staff,
    TimeSignature,
    Wedge,
    WedgeType,
    build_anchor_index,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _marked_score() -> ScoreIR:
    """Dos compases en una voz con todas las clases de marca."""

    first = Measure(
        number=1,
        time_signature=TimeSignature(beats=4, beat_type=4),
        events=(
            Event(
                kind=EventKind.NOTE,
                pitch="C5",
                duration_beats=Fraction(1),
                articulations=(Articulation.STACCATO,),
                slurs=(Slur(SlurType.START, 1),),
            ),
            Event(kind=EventKind.NOTE, pitch="D5", duration_beats=Fraction(1)),
            Event(
                kind=EventKind.NOTE,
                pitch="E5",
                duration_beats=Fraction(2),
                articulations=(Articulation.TENUTO, Articulation.ACCENT),
                fermata=True,
            ),
        ),
        dynamics=(Dynamic(DynamicMark.P, Fraction(0)),),
        wedges=(Wedge(WedgeType.CRESCENDO, 1, Fraction(1, 2)),),
    )
    second = Measure(
        number=2,
        events=(
            Event(
                kind=EventKind.NOTE,
                pitch="F5",
                duration_beats=Fraction(4),
                slurs=(Slur(SlurType.STOP, 1),),
            ),
        ),
        dynamics=(Dynamic(DynamicMark.MF, Fraction(3)),),
        wedges=(Wedge(WedgeType.STOP, 1, Fraction(0)),),
    )
    staff = Staff(id="part-0-staff-0", measures=(first, second))
    return ScoreIR(parts=(Part(id="part-0", staves=(staff,)),))


def _without_marks(score: ScoreIR) -> ScoreIR:
    parts = []
    for part in score.parts:
        staves = []
        for staff in part.staves:
            measures = tuple(
                replace(
                    measure,
                    dynamics=(),
                    wedges=(),
                    events=tuple(
                        replace(event, articulations=(), fermata=False, slurs=())
                        for event in measure.events
                    ),
                )
                for measure in staff.measures
            )
            staves.append(replace(staff, measures=measures))
        parts.append(replace(part, staves=tuple(staves)))
    return ScoreIR(parts=tuple(parts))


def test_vocabularies_follow_adr_0031() -> None:
    assert [a.value for a in Articulation] == [
        "staccato",
        "staccatissimo",
        "accent",
        "marcato",
        "tenuto",
    ]
    assert [d.value for d in DynamicMark] == [
        "ppp",
        "pp",
        "p",
        "mp",
        "mf",
        "f",
        "ff",
        "fff",
        "sf",
        "sfz",
        "fp",
        "fz",
    ]
    assert [t.value for t in SlurType] == ["start", "stop"]
    assert [t.value for t in WedgeType] == ["crescendo", "diminuendo", "stop"]


def test_value_objects_are_immutable_and_validated() -> None:
    slur = Slur(SlurType.START, 3)
    with pytest.raises(FrozenInstanceError):
        # mypy rechaza, con razón, asignar a un campo congelado: es lo que se comprueba aquí.
        slur.number = 4  # type: ignore[misc]
    with pytest.raises(ValueError, match="number must be >= 1"):
        Slur(SlurType.STOP, 0)
    with pytest.raises(ValueError, match="number must be >= 1"):
        Wedge(WedgeType.STOP, 0, Fraction(0))
    with pytest.raises(ValueError, match="offset_beats must be >= 0"):
        Wedge(WedgeType.CRESCENDO, 1, Fraction(-1, 2))
    with pytest.raises(ValueError, match="offset_beats must be >= 0"):
        Dynamic(DynamicMark.F, Fraction(-1))


def test_value_objects_roundtrip_through_primitives() -> None:
    slur = Slur(SlurType.STOP, 2)
    assert slur.to_primitive() == {"type": "stop", "number": 2}
    assert Slur.from_primitive(slur.to_primitive()) == slur

    dynamic = Dynamic(DynamicMark.SFZ, Fraction(3, 2))
    assert dynamic.to_primitive() == {"mark": "sfz", "offset_beats": "3/2"}
    assert Dynamic.from_primitive(dynamic.to_primitive()) == dynamic

    wedge = Wedge(WedgeType.DIMINUENDO, 4, Fraction(1, 3))
    assert wedge.to_primitive() == {"type": "diminuendo", "number": 4, "offset_beats": "1/3"}
    assert Wedge.from_primitive(wedge.to_primitive()) == wedge


def test_event_marks_are_normalized() -> None:
    """Las articulaciones son un conjunto en orden canónico; los extremos de ligadura, también."""

    event = Event(
        kind=EventKind.NOTE,
        pitch="C4",
        duration_beats=Fraction(1),
        articulations=(Articulation.TENUTO, Articulation.STACCATO, Articulation.TENUTO),
        slurs=(Slur(SlurType.START, 2), Slur(SlurType.STOP, 1)),
    )
    assert event.articulations == (Articulation.STACCATO, Articulation.TENUTO)
    assert event.slurs == (Slur(SlurType.STOP, 1), Slur(SlurType.START, 2))
    assert event == Event(
        kind=EventKind.NOTE,
        pitch="C4",
        duration_beats=Fraction(1),
        articulations=(Articulation.STACCATO, Articulation.TENUTO),
        slurs=(Slur(SlurType.STOP, 1), Slur(SlurType.START, 2)),
    )


def test_measure_marks_are_ordered_by_position() -> None:
    measure = Measure(
        number=1,
        dynamics=(Dynamic(DynamicMark.F, Fraction(2)), Dynamic(DynamicMark.P, Fraction(0))),
        wedges=(
            Wedge(WedgeType.CRESCENDO, 2, Fraction(2)),
            Wedge(WedgeType.STOP, 1, Fraction(2)),
            Wedge(WedgeType.DIMINUENDO, 1, Fraction(0)),
        ),
    )
    assert [d.mark for d in measure.dynamics] == [DynamicMark.P, DynamicMark.F]
    assert measure.wedges == (
        Wedge(WedgeType.DIMINUENDO, 1, Fraction(0)),
        Wedge(WedgeType.STOP, 1, Fraction(2)),
        Wedge(WedgeType.CRESCENDO, 2, Fraction(2)),
    )


def test_marks_roundtrip_through_score_primitives() -> None:
    score = _marked_score()
    primitive = score.to_primitive()
    first_measure = primitive["parts"][0]["staves"][0]["measures"][0]
    assert first_measure["dynamics"] == [{"mark": "p", "offset_beats": "0"}]
    assert first_measure["wedges"] == [{"type": "crescendo", "number": 1, "offset_beats": "1/2"}]
    assert first_measure["events"][0]["articulations"] == ["staccato"]
    assert first_measure["events"][0]["slurs"] == [{"type": "start", "number": 1}]
    assert first_measure["events"][2]["articulations"] == ["accent", "tenuto"]
    assert first_measure["events"][2]["fermata"] is True
    assert ScoreIR.from_primitive(json.loads(json.dumps(primitive))) == score


def test_events_and_measures_without_marks_serialize_as_before() -> None:
    """Sin marcas, la serialización no cambia: ni claves nuevas ni valores vacíos."""

    primitive = _without_marks(_marked_score()).to_primitive()
    for measure in primitive["parts"][0]["staves"][0]["measures"]:
        assert set(measure) == {"number", "events", "time_signature", "clef", "key_signature"}
        for event in measure["events"]:
            assert set(event) == {
                "kind",
                "voice",
                "pitch",
                "duration_beats",
                "tie",
                "is_chord",
                "bbox",
                "confidence",
                "ir_handle",
            }


def test_document_serialized_before_213_reads_with_empty_marks() -> None:
    """Un documento guardado antes de #213 (generado con ce71693) se lee igual y sin marcas."""

    raw = json.loads((FIXTURES / "score_document_before_213.json").read_text(encoding="utf-8"))
    document = ScoreDocument.from_primitive(raw)

    events = [
        event
        for part in document.score.parts
        for staff in part.staves
        for measure in staff.measures
        for event in measure.events
    ]
    measures = [
        measure
        for part in document.score.parts
        for staff in part.staves
        for measure in staff.measures
    ]
    assert events
    assert all(e.articulations == () and not e.fermata and e.slurs == () for e in events)
    assert all(m.dynamics == () and m.wedges == () for m in measures)
    # Leído y vuelto a serializar, es el mismo documento, byte a byte en JSON canónico.
    assert json.dumps(document.to_primitive(), sort_keys=True) == json.dumps(raw, sort_keys=True)


def test_marks_do_not_change_the_anchor_index() -> None:
    """Las marcas son atributos: las anclas y su `event_index` no cambian (ADR-0002, ADR-0011)."""

    score = _marked_score()
    assert build_anchor_index(score) == build_anchor_index(_without_marks(score))
