"""Pruebas de estabilidad de anclas ante ediciones estructurales (ADR-0011, #28)."""

from __future__ import annotations

import random
from datetime import UTC, datetime
from fractions import Fraction

import pytest
from cadenza.domain import (
    Anchor,
    EditEvent,
    EditOp,
    Event,
    EventKind,
    Finding,
    Measure,
    Part,
    ScoreIR,
    Severity,
    Staff,
    TimeSignature,
    apply_edit,
    build_anchor_index,
    materialize,
    origin_anchor,
    translate_anchor,
    translate_finding,
)


def _base_score(pitches: list[str]) -> ScoreIR:
    events = tuple(
        Event(
            kind=EventKind.NOTE,
            voice=0,
            pitch=p,
            duration_beats=Fraction(1),
            bbox=(float(i * 10), 0.0, float((i + 1) * 10), 10.0),
            confidence=0.95,
        )
        for i, p in enumerate(pitches)
    )
    measure = Measure(number=1, events=events, time_signature=TimeSignature(4, 4))
    staff = Staff(id="staff-0", measures=(measure,))
    return ScoreIR(parts=(Part(id="part-0", staves=(staff,)),))


def _anchor(event_index: int) -> Anchor:
    return Anchor(
        part=0,
        staff=0,
        measure=1,
        voice=0,
        event_index=event_index,
        staff_id="staff-0",
    )


def _make_edit(
    op: EditOp,
    event_index: int,
    seq: int,
    *,
    pitch: str | None = None,
) -> EditEvent:
    after = None
    if op is EditOp.INSERT_EVENT:
        after = {"kind": "note", "pitch": pitch or "X4", "duration_beats": "1"}
    elif op is EditOp.SET_PITCH:
        after = {"pitch": pitch or "Y4"}

    return EditEvent(
        id=f"edit-{seq}",
        document_id="doc-1",
        seq=seq,
        anchor=_anchor(event_index),
        op=op,
        author="tester",
        created_at=datetime(2026, 10, 7, tzinfo=UTC),
        before=None,
        after=after,
    )


def test_insert_at_end_of_voice_succeeds() -> None:
    score = _base_score(["C4", "D4"])  # 2 eventos: pos 0 y 1
    # Insertar en pos 2 (al final de la voz) debe ser válido según ADR-0011
    edit = _make_edit(EditOp.INSERT_EVENT, event_index=2, seq=1, pitch="E4")
    updated = apply_edit(score, edit)
    events = updated.parts[0].staves[0].measures[0].events
    assert len(events) == 3
    assert [e.pitch for e in events] == ["C4", "D4", "E4"]


def test_insert_beyond_end_of_voice_raises_index_error() -> None:
    score = _base_score(["C4", "D4"])  # 2 eventos: pos 0 y 1
    # Insertar en pos 3 (más allá del final) debe fallar
    edit = _make_edit(EditOp.INSERT_EVENT, event_index=3, seq=1, pitch="F4")
    with pytest.raises(IndexError, match="fuera de rango"):
        apply_edit(score, edit)


def test_insert_into_empty_voice_succeeds() -> None:
    measure = Measure(number=1, events=(), time_signature=TimeSignature(4, 4))
    score = ScoreIR(parts=(Part(id="part-0", staves=(Staff(id="staff-0", measures=(measure,)),)),))
    edit = _make_edit(EditOp.INSERT_EVENT, event_index=0, seq=1, pitch="C4")
    updated = apply_edit(score, edit)
    events = updated.parts[0].staves[0].measures[0].events
    assert len(events) == 1
    assert events[0].pitch == "C4"


def test_origin_anchor_traces_back_through_inserts_and_deletes() -> None:
    # Estado 0: [N0 (C4), N1 (D4), N2 (E4)]
    # seq 1: INSERT 'Ins1' en pos 1 -> [N0, Ins1, N1, N2]
    # seq 2: DELETE en pos 0 (borra N0) -> [Ins1, N1, N2]
    # seq 3: INSERT 'Ins2' en pos 3 (al final) -> [Ins1, N1, N2, Ins2]
    edits = [
        _make_edit(EditOp.INSERT_EVENT, event_index=1, seq=1, pitch="Ins1"),
        _make_edit(EditOp.DELETE_EVENT, event_index=0, seq=2),
        _make_edit(EditOp.INSERT_EVENT, event_index=3, seq=3, pitch="Ins2"),
    ]

    # Estado 0: at_seq=0
    assert origin_anchor(_anchor(0), at_seq=0, edits=edits) == _anchor(0)
    assert origin_anchor(_anchor(1), at_seq=0, edits=edits) == _anchor(1)
    assert origin_anchor(_anchor(2), at_seq=0, edits=edits) == _anchor(2)

    # Estado 1: [N0, Ins1, N1, N2]
    assert origin_anchor(_anchor(0), at_seq=1, edits=edits) == _anchor(0)  # N0
    assert origin_anchor(_anchor(1), at_seq=1, edits=edits) is None  # Ins1 es nuevo
    assert origin_anchor(_anchor(2), at_seq=1, edits=edits) == _anchor(1)  # N1
    assert origin_anchor(_anchor(3), at_seq=1, edits=edits) == _anchor(2)  # N2

    # Estado 2: [Ins1, N1, N2] (N0 fue borrado)
    assert origin_anchor(_anchor(0), at_seq=2, edits=edits) is None  # Ins1 es nuevo
    assert origin_anchor(_anchor(1), at_seq=2, edits=edits) == _anchor(1)  # N1
    assert origin_anchor(_anchor(2), at_seq=2, edits=edits) == _anchor(2)  # N2

    # Estado 3: [Ins1, N1, N2, Ins2]
    assert origin_anchor(_anchor(0), at_seq=3, edits=edits) is None  # Ins1
    assert origin_anchor(_anchor(1), at_seq=3, edits=edits) == _anchor(1)  # N1
    assert origin_anchor(_anchor(2), at_seq=3, edits=edits) == _anchor(2)  # N2
    assert origin_anchor(_anchor(3), at_seq=3, edits=edits) is None  # Ins2 es nuevo


def test_build_anchor_index_inherits_bbox_and_confidence() -> None:
    raw_score = _base_score(["C4", "D4", "E4"])
    raw_anchors = build_anchor_index(raw_score)

    edits = [
        _make_edit(EditOp.INSERT_EVENT, event_index=0, seq=1, pitch="A4"),  # A4, C4, D4, E4
        _make_edit(EditOp.DELETE_EVENT, event_index=2, seq=2),  # borra D4 -> A4, C4, E4
    ]
    mat_score = materialize(raw_score, edits)

    # Al construir el índice pasando raw_anchors y el log:
    mat_anchors = build_anchor_index(mat_score, raw_anchors=raw_anchors, edits=edits, at_seq=2)

    # pos 0 es 'A4' (insertado): no tiene origen en raw_anchors
    ref_0 = mat_anchors.get(_anchor(0))
    assert ref_0 is not None
    assert ref_0.bbox is None

    # pos 1 es 'C4' (era pos 0 original)
    ref_1 = mat_anchors.get(_anchor(1))
    assert ref_1 is not None
    assert ref_1.bbox == (0.0, 0.0, 10.0, 10.0)
    assert ref_1.confidence == 0.95

    # pos 2 es 'E4' (era pos 2 original)
    ref_2 = mat_anchors.get(_anchor(2))
    assert ref_2 is not None
    assert ref_2.bbox == (20.0, 0.0, 30.0, 10.0)
    assert ref_2.confidence == 0.95


def test_translate_finding_across_edits() -> None:
    # Finding anclado a D4 (pos 1 en estado 0)
    finding = Finding(
        anchor=_anchor(1),
        rule_id="R001",
        severity=Severity.ERROR,
        message="test finding",
        at_seq=0,
    )

    edits = [
        _make_edit(EditOp.INSERT_EVENT, event_index=0, seq=1, pitch="A4"),
    ]
    # Tras insertar en pos 0, D4 pasa a ser pos 2 en seq 1
    translated = translate_finding(finding, to_seq=1, edits=edits)
    assert translated is not None
    assert translated.anchor == _anchor(2)
    assert translated.at_seq == 1

    # Si luego borramos pos 2 (que es D4) en seq 2:
    edits.append(_make_edit(EditOp.DELETE_EVENT, event_index=2, seq=2))
    deleted_translated = translate_finding(finding, to_seq=2, edits=edits)
    assert deleted_translated is None


def test_translate_anchor_between_arbitrary_states() -> None:
    edits = [
        _make_edit(EditOp.INSERT_EVENT, event_index=0, seq=1, pitch="A4"),
        _make_edit(EditOp.DELETE_EVENT, event_index=2, seq=2),
    ]
    # En seq 0, D4 estaba en pos 1. Tras seq 1, pasó a pos 2.
    assert translate_anchor(_anchor(1), from_seq=0, to_seq=1, edits=edits) == _anchor(2)
    # En seq 2, la nota en pos 2 fue borrada:
    assert translate_anchor(_anchor(1), from_seq=0, to_seq=2, edits=edits) is None
    # Traducción hacia atrás: de seq 1 (pos 2) a seq 0 (pos 1)
    assert translate_anchor(_anchor(2), from_seq=1, to_seq=0, edits=edits) == _anchor(1)


def test_property_random_inserts_and_deletes_preserve_origin_mapping() -> None:
    rng = random.Random(42)

    for trial in range(30):
        initial_count = 10
        # Modelamos el estado de los eventos como lista de tags ("orig_0", "orig_1", ..., "ins_k")
        state: list[str] = [f"orig_{i}" for i in range(initial_count)]
        edits: list[EditEvent] = []
        seq = 1

        for _step in range(25):
            op = rng.choice(["insert", "delete", "nop"])
            if op == "insert" or len(state) == 0:
                pos = rng.randint(0, len(state))
                tag = f"ins_{seq}"
                state.insert(pos, tag)
                edits.append(_make_edit(EditOp.INSERT_EVENT, event_index=pos, seq=seq))
                seq += 1
            elif op == "delete":
                pos = rng.randint(0, len(state) - 1)
                del state[pos]
                edits.append(_make_edit(EditOp.DELETE_EVENT, event_index=pos, seq=seq))
                seq += 1
            else:
                pos = rng.randint(0, len(state) - 1)
                edits.append(_make_edit(EditOp.SET_PITCH, event_index=pos, seq=seq))
                seq += 1

        # Verificamos para cada posición en el estado final (seq - 1)
        final_seq = seq - 1
        for final_pos, tag in enumerate(state):
            orig = origin_anchor(_anchor(final_pos), at_seq=final_seq, edits=edits)
            if tag.startswith("orig_"):
                expected_orig_index = int(tag.split("_")[1])
                assert orig == _anchor(expected_orig_index), (
                    f"Trial {trial}: final pos {final_pos} con tag {tag} esperó origen "
                    f"{expected_orig_index}, obtuvo {orig}"
                )
            else:
                assert orig is None, (
                    f"Trial {trial}: final pos {final_pos} con tag {tag} insertado esperó None, "
                    f"obtuvo {orig}"
                )
