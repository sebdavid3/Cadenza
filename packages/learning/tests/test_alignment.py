"""Pruebas unitarias de alineación y derivación de EditEvents (ADR-0008, D21, Issue #20)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest
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
    Tie,
    TimeSignature,
    materialize,
)
from cadenza.learning import (
    align_voice_events,
    count_edits_by_op,
    derive_edit_events,
    is_structurally_equal,
    split_pitch,
)


def _make_score(
    measures: list[Measure],
    *,
    part_id: str = "part-0",
    staff_id: str = "part-0-staff-0",
) -> ScoreIR:
    staff = Staff(id=staff_id, measures=tuple(measures))
    return ScoreIR(parts=(Part(id=part_id, staves=(staff,)),))


def _make_measure(
    number: int,
    events: list[Event],
    *,
    clef: Clef | None = None,
    key_signature: KeySignature | None = None,
    time_signature: TimeSignature | None = None,
) -> Measure:
    return Measure(
        number=number,
        events=tuple(events),
        clef=clef or Clef.treble(),
        key_signature=key_signature or KeySignature(fifths=0),
        time_signature=time_signature or TimeSignature(4, 4),
    )


def _note(
    pitch: str,
    duration: Fraction | int = 1,
    *,
    voice: int = 0,
    tie: Tie | None = None,
    is_chord: bool = False,
) -> Event:
    dur = Fraction(duration) if isinstance(duration, int) else duration
    return Event(
        kind=EventKind.NOTE,
        voice=voice,
        pitch=pitch,
        duration_beats=dur,
        tie=tie,
        is_chord=is_chord,
    )


def _rest(duration: Fraction | int = 1, *, voice: int = 0) -> Event:
    dur = Fraction(duration) if isinstance(duration, int) else duration
    return Event(kind=EventKind.REST, voice=voice, pitch=None, duration_beats=dur)


# ============================================================================
# 1. Pruebas de descomposición de pitch
# ============================================================================


def test_split_pitch_valid_variations() -> None:
    assert split_pitch("C4") == ("C", "", "4")
    assert split_pitch("Bb4") == ("B", "b", "4")
    assert split_pitch("B-4") == ("B", "b", "4")
    assert split_pitch("C#5") == ("C", "#", "5")
    assert split_pitch("Fx4") == ("F", "##", "4")
    assert split_pitch("F##4") == ("F", "##", "4")
    assert split_pitch("Abb3") == ("A", "bb", "3")
    assert split_pitch("A--3") == ("A", "bb", "3")


def test_split_pitch_none_and_invalid() -> None:
    assert split_pitch(None) == ("", "", "")
    assert split_pitch("") == ("", "", "")
    assert split_pitch("invalid") == ("", "", "")
    assert split_pitch("H4") == ("", "", "")


# ============================================================================
# 2. Pruebas de alineación a nivel de voz (Needleman-Wunsch)
# ============================================================================


def test_align_voice_events_identical() -> None:
    evs = [_note("C4"), _note("D4")]
    aligned = align_voice_events(evs, evs)
    assert len(aligned) == 2
    assert aligned == [(evs[0], evs[0]), (evs[1], evs[1])]


def test_align_voice_events_insertions_and_deletions() -> None:
    p = [_note("C4"), _note("E4")]
    g = [_note("C4"), _note("D4"), _note("E4")]
    aligned = align_voice_events(p, g)
    assert len(aligned) == 3
    # Debe alinear C4 con C4, None con D4 (inserción), E4 con E4
    assert aligned[0] == (p[0], g[0])
    assert aligned[1] == (None, g[1])
    assert aligned[2] == (p[1], g[2])


def test_align_voice_events_note_and_rest_forces_delete_insert() -> None:
    p = [_rest(1)]
    g = [_note("C4", 1)]
    aligned = align_voice_events(p, g)
    assert len(aligned) == 2
    assert aligned[0] == (p[0], None)
    assert aligned[1] == (None, g[0])


# ============================================================================
# 3. Pruebas de derivación y propiedad de materialización
# ============================================================================


def test_derive_edit_events_identical_produces_no_edits() -> None:
    score = _make_score([_make_measure(1, [_note("C4"), _note("D4")])])
    edits = derive_edit_events(score, score)
    assert edits == []
    assert materialize(score, edits) == score


def test_derive_edit_events_set_pitch() -> None:
    pred = _make_score([_make_measure(1, [_note("C4"), _note("D4")])])
    gt = _make_score([_make_measure(1, [_note("C4"), _note("E4")])])

    edits = derive_edit_events(pred, gt)
    assert len(edits) == 1
    edit = edits[0]
    assert edit.op == EditOp.SET_PITCH
    assert edit.seq == 1
    assert edit.anchor.measure == 1
    assert edit.anchor.event_index == 1
    assert edit.before == {"pitch": "D4"}
    assert edit.after == {"pitch": "E4"}

    materialized = materialize(pred, edits)
    assert is_structurally_equal(materialized, gt)
    assert materialized == gt


def test_derive_edit_events_set_accidental() -> None:
    # Misma letra y octava, diferente alteración
    pred = _make_score([_make_measure(1, [_note("Bb4")])])
    gt = _make_score([_make_measure(1, [_note("B4")])])

    edits = derive_edit_events(pred, gt)
    assert len(edits) == 1
    edit = edits[0]
    assert edit.op == EditOp.SET_ACCIDENTAL
    assert edit.before == {"accidental": "b"}
    assert edit.after == {"accidental": ""}

    materialized = materialize(pred, edits)
    assert is_structurally_equal(materialized, gt)
    assert materialized == gt


def test_derive_edit_events_set_duration() -> None:
    pred = _make_score([_make_measure(1, [_note("C4", 1)])])
    gt = _make_score([_make_measure(1, [_note("C4", Fraction(1, 2))])])

    edits = derive_edit_events(pred, gt)
    assert len(edits) == 1
    edit = edits[0]
    assert edit.op == EditOp.SET_DURATION
    assert edit.before == {"duration_beats": Fraction(1)}
    assert edit.after == {"duration_beats": Fraction(1, 2)}

    materialized = materialize(pred, edits)
    assert is_structurally_equal(materialized, gt)
    assert materialized == gt


def test_derive_edit_events_combined_pitch_and_duration() -> None:
    pred = _make_score([_make_measure(1, [_note("C4", 1)])])
    gt = _make_score([_make_measure(1, [_note("G4", Fraction(1, 2))])])

    edits = derive_edit_events(pred, gt)
    assert len(edits) == 2
    ops = [e.op for e in edits]
    assert EditOp.SET_PITCH in ops
    assert EditOp.SET_DURATION in ops

    materialized = materialize(pred, edits)
    assert is_structurally_equal(materialized, gt)
    assert materialized == gt


def test_derive_edit_events_insert_and_delete() -> None:
    # Pred tiene C4, D4, F4. GT tiene C4, E4, F4.
    # En este caso Needleman-Wunsch sustituye D4 por E4.
    # Para probar insert y delete forzamos longitudes distintas:
    # Pred: [C4, D4, E4, F4]
    # GT: [C4, F4, G4]
    pred = _make_score([_make_measure(1, [_note("C4"), _note("D4"), _note("E4"), _note("F4")])])
    gt = _make_score([_make_measure(1, [_note("C4"), _note("F4"), _note("G4")])])

    edits = derive_edit_events(pred, gt)
    dist = count_edits_by_op(edits)
    assert dist.total == len(edits)

    materialized = materialize(pred, edits)
    assert is_structurally_equal(materialized, gt)
    assert materialized == gt


def test_derive_edit_events_clef_and_key_change() -> None:
    pred = _make_score(
        [
            _make_measure(
                1,
                [_note("C4")],
                clef=Clef.bass(),
                key_signature=KeySignature(fifths=0),
            )
        ]
    )
    gt = _make_score(
        [
            _make_measure(
                1,
                [_note("C4")],
                clef=Clef.treble(),
                key_signature=KeySignature(fifths=2),
            )
        ]
    )

    edits = derive_edit_events(pred, gt)
    assert len(edits) == 2
    ops = [e.op for e in edits]
    assert EditOp.SET_CLEF in ops
    assert EditOp.SET_KEY in ops

    materialized = materialize(pred, edits)
    assert is_structurally_equal(materialized, gt)
    assert materialized == gt


def test_derive_edit_events_multi_measure_complex() -> None:
    m1_pred = _make_measure(
        1,
        [_note("C4", 1), _note("D4", 1)],
        clef=Clef.treble(),
        key_signature=KeySignature(fifths=1),
    )
    m2_pred = _make_measure(2, [_note("E4", 2)])

    m1_gt = _make_measure(
        1,
        [_note("C4", Fraction(1, 2)), _note("Eb4", Fraction(1, 2)), _note("D4", 1)],
        clef=Clef.treble(),
        key_signature=KeySignature(fifths=0),
    )
    m2_gt = _make_measure(2, [_note("F4", 2)])

    pred = _make_score([m1_pred, m2_pred])
    gt = _make_score([m1_gt, m2_gt])

    edits = derive_edit_events(pred, gt)
    materialized = materialize(pred, edits)

    assert is_structurally_equal(materialized, gt)
    assert materialized == gt


# ============================================================================
# 4. Pruebas de distribución y conteo
# ============================================================================


def test_count_edits_by_op() -> None:
    anchor = Anchor(part=0, staff=0, measure=1, voice=0, event_index=0, staff_id="staff-1")
    edits = [
        EditEvent(
            id="e1",
            document_id="doc",
            seq=1,
            anchor=anchor,
            op=EditOp.SET_PITCH,
            author="tester",
            created_at=pytest.importorskip("datetime").datetime.now(
                pytest.importorskip("datetime").UTC
            ),
        ),
        EditEvent(
            id="e2",
            document_id="doc",
            seq=2,
            anchor=anchor,
            op=EditOp.SET_DURATION,
            author="tester",
            created_at=pytest.importorskip("datetime").datetime.now(
                pytest.importorskip("datetime").UTC
            ),
        ),
        EditEvent(
            id="e3",
            document_id="doc",
            seq=3,
            anchor=anchor,
            op=EditOp.SET_ACCIDENTAL,
            author="tester",
            created_at=pytest.importorskip("datetime").datetime.now(
                pytest.importorskip("datetime").UTC
            ),
        ),
    ]

    dist = count_edits_by_op(edits)
    assert dist.set_pitch == 1
    assert dist.set_duration == 1
    assert dist.set_accidental == 1
    assert dist.insert_event == 0
    assert dist.delete_event == 0
    assert dist.set_clef == 0
    assert dist.set_key == 0
    assert dist.total == 3

    d_dict = dist.to_dict()
    assert d_dict["Total"] == 3
    assert d_dict["SetPitch"] == 1


# ============================================================================
# 5. Integración con par real de PrIMuS (si existe)
# ============================================================================


def test_primus_real_pair_derivation_smoke() -> None:
    pred_path = Path("data/primus/predictions/000051650-1_1_1.musicxml")
    gt_path = Path("data/primus/package_aa/000051650-1_1_1/000051650-1_1_1.mei")

    if not pred_path.is_file() or not gt_path.is_file():
        pytest.skip("Corpus PrIMuS no disponible localmente para smoke de derivación")

    from cadenza.interchange import read_score

    score_pred = read_score(pred_path)
    score_gt = read_score(gt_path)

    edits = derive_edit_events(score_pred, score_gt)
    materialized = materialize(score_pred, edits)

    assert is_structurally_equal(materialized, score_gt)
