"""Pruebas de estabilidad de anclas y proyecciones en piano (dos pentagramas, acordes, voces)."""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction

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
    apply_edit,
    build_anchor_index,
    translate_anchor,
)


def _make_piano_score() -> ScoreIR:
    # Compás 1:
    # Pentagrama 0 (Sol): C4 (negra), D4 (negra), Acorde E4+G4 (blanca)
    m1_s0 = Measure(
        number=1,
        clef=Clef.treble(),
        key_signature=KeySignature(0),
        time_signature=TimeSignature(4, 4),
        events=(
            Event(kind=EventKind.NOTE, voice=0, pitch="C4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=0, pitch="D4", duration_beats=Fraction(1)),
            Event(
                kind=EventKind.NOTE, voice=0, pitch="E4", duration_beats=Fraction(2), is_chord=False
            ),
            Event(
                kind=EventKind.NOTE, voice=0, pitch="G4", duration_beats=Fraction(2), is_chord=True
            ),
        ),
    )
    # Pentagrama 1 (Fa): C3 (redonda)
    m1_s1 = Measure(
        number=1,
        clef=Clef.bass(),
        key_signature=KeySignature(0),
        time_signature=TimeSignature(4, 4),
        events=(Event(kind=EventKind.NOTE, voice=0, pitch="C3", duration_beats=Fraction(4)),),
    )

    # Compás 2:
    # Pentagrama 0: voz 0 con 2 blancas, voz 1 con 1 redonda
    m2_s0 = Measure(
        number=2,
        time_signature=TimeSignature(4, 4),
        events=(
            Event(kind=EventKind.NOTE, voice=0, pitch="E4", duration_beats=Fraction(2)),
            Event(kind=EventKind.NOTE, voice=0, pitch="G4", duration_beats=Fraction(2)),
            Event(kind=EventKind.NOTE, voice=1, pitch="C4", duration_beats=Fraction(4)),
        ),
    )
    # Pentagrama 1: voz 0 con 2 blancas
    m2_s1 = Measure(
        number=2,
        time_signature=TimeSignature(4, 4),
        events=(
            Event(kind=EventKind.NOTE, voice=0, pitch="C3", duration_beats=Fraction(2)),
            Event(kind=EventKind.NOTE, voice=0, pitch="G3", duration_beats=Fraction(2)),
        ),
    )

    staff_0 = Staff(id="part-0-staff-0", measures=(m1_s0, m2_s0))
    staff_1 = Staff(id="part-0-staff-1", measures=(m1_s1, m2_s1))
    return ScoreIR(parts=(Part(id="part-0", staves=(staff_0, staff_1)),))


def test_piano_anchor_index_structure() -> None:
    score = _make_piano_score()
    index = build_anchor_index(score)

    # Total de eventos:
    # m1_s0: 4, m1_s1: 1
    # m2_s0: 3, m2_s1: 2
    # Total = 10
    assert len(index) == 10

    # Las dos notas del acorde en m1_s0 tienen event_index consecutivos en la misma voz
    q1 = Anchor(part=0, staff=0, measure=1, voice=0, event_index=2, staff_id="part-0-staff-0")
    q2 = Anchor(part=0, staff=0, measure=1, voice=0, event_index=3, staff_id="part-0-staff-0")
    chord_note1 = index.find_anchor(q1)
    chord_note2 = index.find_anchor(q2)
    assert chord_note1 is not None and chord_note2 is not None

    ref1 = index.get(chord_note1)
    ref2 = index.get(chord_note2)
    assert ref1 is not None and ref2 is not None
    assert ref1.kind == EventKind.NOTE and ref2.kind == EventKind.NOTE

    m1_events = score.parts[0].staves[0].measures[0].events
    assert m1_events[2].pitch == "E4" and not m1_events[2].is_chord
    assert m1_events[3].pitch == "G4" and m1_events[3].is_chord

    # En m2_s0, voz 0 y voz 1 tienen event_index independientes empezando en 0
    qv0 = Anchor(part=0, staff=0, measure=2, voice=0, event_index=0, staff_id="part-0-staff-0")
    qv1 = Anchor(part=0, staff=0, measure=2, voice=1, event_index=0, staff_id="part-0-staff-0")
    voice0_ev0 = index.find_anchor(qv0)
    voice1_ev0 = index.find_anchor(qv1)
    assert voice0_ev0 is not None and voice1_ev0 is not None
    assert voice0_ev0.voice == 0 and voice1_ev0.voice == 1


def test_piano_staves_are_isolated_under_edits() -> None:
    score = _make_piano_score()
    raw_index = build_anchor_index(score)

    # Insertar una nota en staff 0 no afecta a los índices de staff 1
    insert_anchor = Anchor(
        part=0, staff=0, measure=1, voice=0, event_index=1, staff_id="part-0-staff-0"
    )
    insert_edit = EditEvent(
        id="edit-1",
        document_id="doc-1",
        seq=1,
        op=EditOp.INSERT_EVENT,
        author="human",
        created_at=datetime.now(UTC),
        anchor=insert_anchor,
        after={"kind": "note", "pitch": "C#4", "duration_beats": "1/2"},
    )
    score_after = apply_edit(score, insert_edit)
    index_after = build_anchor_index(
        score_after, raw_anchors=raw_index, edits=[insert_edit], at_seq=1
    )

    # En staff 1, el ancla del compás 1 sigue siendo idéntica
    bass_anchor = Anchor(
        part=0, staff=1, measure=1, voice=0, event_index=0, staff_id="part-0-staff-1"
    )
    ref = index_after.get(bass_anchor)
    assert ref is not None
    assert ref.kind == EventKind.NOTE
    assert score_after.parts[0].staves[1].measures[0].events[0].pitch == "C3"

    # Y translate_anchor sobre bass_anchor no cambia
    translated_bass = translate_anchor(bass_anchor, from_seq=0, to_seq=1, edits=[insert_edit])
    assert translated_bass == bass_anchor


def test_piano_edit_chord_note_directly() -> None:
    score = _make_piano_score()
    target_anchor = Anchor(
        part=0, staff=0, measure=1, voice=0, event_index=3, staff_id="part-0-staff-0"
    )
    edit = EditEvent(
        id="edit-chord",
        document_id="doc-1",
        seq=1,
        op=EditOp.SET_PITCH,
        author="human",
        created_at=datetime.now(UTC),
        anchor=target_anchor,
        after={"pitch": "G#4"},
    )
    modified = apply_edit(score, edit)
    m1_events = modified.parts[0].staves[0].measures[0].events
    assert m1_events[2].pitch == "E4"
    assert m1_events[2].is_chord is False
    assert m1_events[3].pitch == "G#4"
    assert m1_events[3].is_chord is True
