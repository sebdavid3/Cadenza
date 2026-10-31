"""Pruebas del corpus de correcciones por nota y de la altura que suena de PrIMuS (#255)."""

from __future__ import annotations

import itertools
from fractions import Fraction
from typing import Any

import pytest
from cadenza.domain import (
    Clef,
    EditOp,
    Event,
    EventKind,
    KeySignature,
    Measure,
    Part,
    ScoreIR,
    Staff,
    TimeSignature,
    materialize,
)
from cadenza.learning import (
    SemanticMismatch,
    assign_split,
    build_correction_records,
    classify_pitch_change,
    count_edits_by_op,
    derive_edit_events,
    is_structurally_equal,
    primus_work_id,
    semantic_note_pitches,
    with_sounding_pitches,
)


def _note(pitch: str, beats: str = "1", voice: int = 0) -> Event:
    return Event(kind=EventKind.NOTE, voice=voice, pitch=pitch, duration_beats=Fraction(beats))


def _rest(beats: str = "1") -> Event:
    return Event(kind=EventKind.REST, duration_beats=Fraction(beats))


def _score(*measures: Measure) -> ScoreIR:
    return ScoreIR(parts=(Part(id="p", staves=(Staff(id="p-s0", measures=measures),)),))


def _measure(
    number: int,
    *events: Event,
    key: int | None = None,
    time: TimeSignature | None = None,
    clef: Clef | None = None,
) -> Measure:
    return Measure(
        number=number,
        events=events,
        key_signature=None if key is None else KeySignature(fifths=key),
        time_signature=time,
        clef=clef,
    )


# --- Altura que suena de PrIMuS -------------------------------------------------------


def test_semantic_note_pitches_keeps_notes_and_grace_notes_in_order() -> None:
    """El `.semantic` trae la altura que suena; las notas de adorno cuentan como notas."""
    semantic = (
        "clef-G2\tkeySignature-EbM\ttimeSignature-3/4\tnote-Bb5_quarter\t"
        "gracenote-A4_sixteenth\tnote-Eb5_eighth.\trest-eighth\ttie\tnote-C#6_half_fermata\t"
        "multirest-4\tbarline\tnote-Fbb4_quarter\tnote-Gx4_quarter\t"
    )
    assert semantic_note_pitches(semantic) == ["Bb5", "A4", "Eb5", "C#6", "Fbb4", "G##4"]


def test_semantic_note_pitches_rejects_an_unreadable_pitch() -> None:
    with pytest.raises(SemanticMismatch, match="note-H4_quarter"):
        semantic_note_pitches("note-H4_quarter\tbarline")


def test_with_sounding_pitches_applies_key_and_explicit_naturals() -> None:
    """La verdad leída del MEI no lleva la alteración de la armadura; el `.semantic`, sí."""
    gt_from_mei = _score(
        _measure(1, _note("B4"), _note("E5"), _note("B4"), key=-3),
        _measure(2, _note("A4"), _rest()),
    )
    sounding = with_sounding_pitches(gt_from_mei, ["Bb4", "Eb5", "B4", "A4"])

    pitches = [e.pitch for m in sounding.parts[0].staves[0].measures for e in m.events]
    assert pitches == ["Bb4", "Eb5", "B4", "A4", None]
    # Todo lo demás queda igual.
    assert sounding.parts[0].staves[0].measures[0].key_signature == KeySignature(fifths=-3)


@pytest.mark.parametrize(
    ("pitches", "message"),
    [
        (["Bb4", "Eb5"], "2 alturas para 3 notas"),
        (["Bb4", "Eb5", "B4", "A4"], "4 alturas para 3 notas"),
        (["Bb4", "Fb5", "B4"], "nota 2"),
        (["Bb4", "Eb4", "B4"], "nota 2"),
    ],
)
def test_with_sounding_pitches_refuses_a_ground_truth_that_does_not_match(
    pitches: list[str], message: str
) -> None:
    """Si la letra, la octava o el número de notas no coinciden, no se adivina nada."""
    gt_from_mei = _score(_measure(1, _note("B4"), _note("E5"), _note("B4"), key=-3))
    with pytest.raises(SemanticMismatch, match=message):
        with_sounding_pitches(gt_from_mei, pitches)


def _grace(pitch: str) -> Event:
    return Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=Fraction(0))


def test_with_sounding_pitches_pairs_a_grace_group_by_letter_and_octave() -> None:
    """En un grupo de adornos, el MEI y el `.semantic` no siempre dan el mismo orden."""
    gt_from_mei = _score(
        _measure(1, _grace("C5"), _grace("B4"), _note("C5"), _grace("F4"), _note("B4"), key=-1)
    )
    sounding = with_sounding_pitches(gt_from_mei, ["Bb4", "C5", "C5", "F#4", "Bb4"])
    pitches = [e.pitch for m in sounding.parts[0].staves[0].measures for e in m.events]
    assert pitches == ["C5", "Bb4", "C5", "F#4", "Bb4"]


def test_with_sounding_pitches_refuses_an_ambiguous_grace_group() -> None:
    """Dos adornos de la misma letra y octava con distinta alteración: no se adivina."""
    gt_from_mei = _score(_measure(1, _grace("F4"), _grace("F4"), _note("G4")))
    with pytest.raises(SemanticMismatch, match="ambiguo"):
        with_sounding_pitches(gt_from_mei, ["F#4", "F4", "G4"])
    # Fuera de un grupo de adornos el orden sigue siendo el de la partitura.
    with pytest.raises(SemanticMismatch, match="nota 1"):
        with_sounding_pitches(_score(_measure(1, _note("F4"), _note("G4"))), ["G4", "F4"])


def test_primus_work_id_is_the_rism_record() -> None:
    assert primus_work_id("000051650-1_1_2") == "000051650"
    assert primus_work_id("201008211-1_1_1_") == "201008211"


# --- Partición fija por incipit -------------------------------------------------------


def test_assign_split_is_fixed_per_incipit_and_independent_of_the_sample() -> None:
    ids = [f"0000{n:05d}-1_1_1" for n in range(2000)]
    first = {i: assign_split(i, seed=20260920) for i in ids}
    # Otra muestra que contiene una parte de los mismos incipits: la misma partición.
    again = {i: assign_split(i, seed=20260920) for i in reversed(ids[:500])}
    assert all(first[i] == again[i] for i in again)
    test_share = sum(1 for split in first.values() if split == "test") / len(ids)
    assert 0.17 < test_share < 0.23
    # Otra semilla da otra partición.
    other = {i: assign_split(i, seed=1) for i in ids}
    assert other != first


def test_assign_split_rejects_an_impossible_fraction() -> None:
    with pytest.raises(ValueError, match="test_fraction"):
        assign_split("x", seed=1, test_fraction=1.0)


# --- Registros por nota ----------------------------------------------------------------


def _ops(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        for op in (record["correction"] or {}).get("ops", ()):
            counts[op] = counts.get(op, 0) + 1
    return counts


def _derived_ops(predicted: ScoreIR, truth: ScoreIR) -> dict[str, int]:
    distribution = count_edits_by_op(derive_edit_events(predicted, truth)).to_dict()
    return {op: n for op, n in distribution.items() if op != "Total" and n}


def test_classify_pitch_change_matches_the_derivation() -> None:
    assert classify_pitch_change("F4", "F#4") is EditOp.SET_ACCIDENTAL
    assert classify_pitch_change("Bb4", "B4") is EditOp.SET_ACCIDENTAL
    assert classify_pitch_change("F4", "G4") is EditOp.SET_PITCH
    assert classify_pitch_change("F4", "F5") is EditOp.SET_PITCH
    assert classify_pitch_change("F4", "F4") is None


def test_records_give_each_read_note_its_correction_or_none() -> None:
    three_four = TimeSignature(3, 4)
    predicted = _score(
        _measure(
            1,
            _note("F4", "1"),
            _note("A4", "1"),
            _note("C5", "1/2"),
            key=1,
            time=three_four,
            clef=Clef.treble(),
        ),
        _measure(2, _note("D5", "1"), _note("E5", "1"), _note("G5", "1"), _note("B5", "1")),
    )
    truth = _score(
        _measure(
            1,
            _note("F#4", "1"),
            _note("A4", "1"),
            _note("C5", "1"),
            key=1,
            time=three_four,
            clef=Clef.treble(),
        ),
        _measure(2, _note("D5", "1"), _note("E5", "1"), _note("B5", "1")),
    )
    records = build_correction_records(
        predicted, truth, incipit_id="inc-1", split="train", verified=True
    )
    events = [r for r in records if r["record"] == "event"]
    assert len(events) == 7  # una por evento leído
    assert {r["incipit_id"] for r in records} == {"inc-1"}
    assert {r["split"] for r in records} == {"train"}

    f_sharp, a_natural, c_short = events[0], events[1], events[2]
    assert f_sharp["read"]["pitch"] == "F4"
    assert f_sharp["correction"] == {
        "ops": ["SetAccidental"],
        "pitch": "F#4",
        "accidental": {"before": "", "after": "#"},
    }
    assert a_natural["correction"] is None
    assert c_short["correction"] == {"ops": ["SetDuration"], "duration_beats": "1"}

    context = f_sharp["context"]
    assert context["key_fifths"] == 1
    assert context["time_signature"] == "3/4"
    assert context["clef"] == "G2"
    assert context["measure_index"] == 0
    assert context["event_index"] == 0
    assert context["onset_beats"] == "0"
    assert context["accidental"] == ""
    assert context["key_accidental"] == "#"
    assert context["accidental_vs_key"] == "against_key"
    assert context["prev"] is None
    assert context["next"] == {"kind": "note", "pitch": "A4", "duration_beats": "1"}
    # El compás leído suma 5/2 negras en un 3/4: le falta media negra.
    assert c_short["context"]["measure_beats_read"] == "5/2"
    assert c_short["context"]["measure_balance_beats"] == "-1/2"
    assert c_short["context"]["onset_beats"] == "2"

    # La armadura, el compás y la clave se heredan del compás anterior; las vecinas cruzan
    # la barra de compás.
    d5 = events[3]
    assert d5["context"]["key_fifths"] == 1
    assert d5["context"]["time_signature"] == "3/4"
    assert d5["context"]["prev"] == {"kind": "note", "pitch": "C5", "duration_beats": "1/2"}
    assert d5["context"]["measure_balance_beats"] == "1"

    # Lo que sobra se borra; el anclaje es el del estado leído (seq 0).
    g5 = events[5]
    assert g5["correction"] == {"ops": ["DeleteEvent"]}
    assert g5["anchor"] == {"part": 0, "staff": 0, "measure": 2, "voice": 0, "event_index": 2}


def test_record_context_is_what_was_read_not_the_truth() -> None:
    """El contexto es lo que verá la capa: la clave, la armadura y el compás leídos."""
    predicted = _score(
        _measure(
            1,
            _note("F4", "1"),
            _note("A4", "1"),
            key=0,
            time=TimeSignature(2, 4),
            clef=Clef.treble(),
        )
    )
    truth = _score(
        _measure(
            1,
            _note("F#4", "1/2"),
            _note("A4", "1/2"),
            _note("B4", "1"),
            key=2,
            time=TimeSignature(4, 4),
            clef=Clef.bass(),
        )
    )
    records = build_correction_records(
        predicted, truth, incipit_id="leak", split="train", verified=True
    )
    for record in records:
        context = record["context"]
        if context is None:
            continue
        assert context["key_fifths"] == 0
        assert context["time_signature"] == "2/4"
        assert context["clef"] == "G2"
        assert context["measure_beats_read"] == "2"
        assert context["measure_balance_beats"] == "0"
        assert context["events_in_voice"] == 2
        for neighbour in (context["prev"], context["next"]):
            assert neighbour is None or neighbour["pitch"] in {"F4", "A4"}
    f4 = next(r for r in records if r["record"] == "event")
    assert f4["context"]["key_accidental"] == ""
    assert f4["context"]["accidental_vs_key"] == "in_key"


def test_records_carry_insertions_and_measure_corrections() -> None:
    predicted = _score(
        _measure(1, _note("C5", "1"), _note("E5", "1"), key=0, time=TimeSignature(3, 4)),
    )
    truth = _score(
        _measure(
            1,
            _note("C5", "1"),
            _rest("1"),
            _note("E5", "1"),
            key=2,
            time=TimeSignature(3, 4),
            clef=Clef.bass(),
        ),
    )
    records = build_correction_records(
        predicted, truth, incipit_id="inc-2", split="test", verified=False
    )
    insertion = next(r for r in records if r["record"] == "insertion")
    assert insertion["read"] is None
    assert insertion["anchor"]["event_index"] == 1  # va antes del segundo evento leído
    assert insertion["correction"] == {
        "ops": ["InsertEvent"],
        "event": {
            "kind": "rest",
            "pitch": None,
            "duration_beats": "1",
            "tie": None,
            "is_chord": False,
            "hidden": False,
        },
    }
    assert insertion["context"]["onset_beats"] == "1"
    assert insertion["context"]["prev"]["pitch"] == "C5"
    assert insertion["context"]["next"]["pitch"] == "E5"
    assert insertion["verified"] is False

    measure = next(r for r in records if r["record"] == "measure")
    assert measure["anchor"]["measure"] == 1
    assert measure["read"] == {"clef": None, "key_fifths": 0}
    assert measure["correction"] == {
        "ops": ["SetClef", "SetKey"],
        "clef": Clef.bass().to_primitive(),
        "key_fifths": 2,
    }


def test_records_account_for_every_derived_edit_exactly_once() -> None:
    """Cada edición de `derive_edit_events` está en un registro, y solo en uno."""
    pitches = ["C4", "C#4", "D4", "Bb4", "B4", "G5"]
    durations = ["1/2", "1", "3/2"]
    cases = list(itertools.product(pitches, durations))
    for shift in range(1, 6):
        predicted_events = [_note(p, d) for p, d in cases[shift : shift + 7]]
        truth_events = [_note(p, d) for p, d in cases[shift + 1 : shift + 9]]
        predicted_events.insert(shift % 3, _rest("1/2"))
        predicted = _score(_measure(1, *predicted_events, key=-1, time=TimeSignature(4, 4)))
        truth = _score(_measure(1, *truth_events, key=shift - 3, time=TimeSignature(4, 4)))

        records = build_correction_records(
            predicted, truth, incipit_id=f"c{shift}", split="train", verified=True
        )
        assert _ops(records) == _derived_ops(predicted, truth)
        assert is_structurally_equal(
            materialize(predicted, derive_edit_events(predicted, truth)), truth
        )


def test_records_of_a_measure_without_truth_are_marked_unaligned() -> None:
    """Los compases leídos de más no tienen verdad con que alinearse: no se etiquetan."""
    predicted = _score(_measure(1, _note("C5"), key=0), _measure(2, _note("D5")))
    truth = _score(_measure(1, _note("C5"), key=0))
    records = build_correction_records(
        predicted, truth, incipit_id="c", split="train", verified=False
    )
    extra = [r for r in records if r["anchor"]["measure"] == 2]
    assert len(extra) == 1
    assert extra[0]["aligned"] is False
    assert extra[0]["correction"] is None
    assert all(r["aligned"] for r in records if r["anchor"]["measure"] == 1)
