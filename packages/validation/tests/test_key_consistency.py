"""Pruebas de `key.consistency`: armaduras distintas entre los pentagramas de una parte."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from pathlib import Path

from cadenza.domain import (
    Clef,
    EditOp,
    Event,
    EventKind,
    KeySignature,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Severity,
    Staff,
    TimeSignature,
    build_anchor_index,
    validate_after,
)
from cadenza.validation import KeyConsistencyRule, ValidationEngine


def _make_document(
    events: tuple[Event, ...],
    key_signature: KeySignature | None = None,
    staff_id: str = "staff-0",
) -> ScoreDocument:
    measure = Measure(
        number=1,
        events=events,
        time_signature=TimeSignature(4, 4),
        clef=Clef.treble(),
        key_signature=key_signature,
    )
    staff = Staff(id=staff_id, measures=(measure,))
    part = Part(id="part-0", staves=(staff,))
    score = ScoreIR(parts=(part,))
    return ScoreDocument(
        id="test-key-doc",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="fake", model_version="1.0"),
    )


def test_rule_id() -> None:
    assert KeyConsistencyRule().rule_id == "key.consistency"


def test_consistent_key_signature_notes_have_no_findings() -> None:
    # 2 sostenidos (Re mayor): D4, E4, F#4, A4
    doc = _make_document(
        (
            Event(kind=EventKind.NOTE, voice=0, pitch="D4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=0, pitch="E4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=0, pitch="F#4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=0, pitch="A4", duration_beats=Fraction(1)),
        ),
        key_signature=KeySignature(fifths=2),
    )
    engine = ValidationEngine([KeyConsistencyRule()])
    assert engine.validate(doc) == []


def test_an_accidental_against_the_key_is_no_longer_flagged() -> None:
    """Se retira la comprobación (b) de ADR-0040 §8: un bemol con armadura de sostenidos, o un
    sostenido con armadura de bemoles, suele estar escrito así (la sensible de una tonalidad
    menor). En el recuento, 121 de las 157 notas que señalaba eran correctas, y las otras 36
    las cubre `accidental.repeated`."""
    sharp_key = _make_document(
        (
            Event(kind=EventKind.NOTE, voice=0, pitch="D4", duration_beats=Fraction(2)),
            Event(kind=EventKind.NOTE, voice=0, pitch="Bb4", duration_beats=Fraction(2)),
        ),
        key_signature=KeySignature(fifths=2),
    )
    flat_key = _make_document(
        (
            Event(kind=EventKind.NOTE, voice=0, pitch="Bb3", duration_beats=Fraction(2)),
            Event(kind=EventKind.NOTE, voice=0, pitch="C#4", duration_beats=Fraction(2)),
        ),
        key_signature=KeySignature(fifths=-2),
    )
    engine = ValidationEngine([KeyConsistencyRule()])
    assert engine.validate(sharp_key) == []
    assert engine.validate(flat_key) == []


def test_sharp_and_flat_on_the_same_letter_are_no_longer_flagged() -> None:
    """Se retira la comprobación (c) de ADR-0040 §8: sostenido y bemol sobre la misma letra en
    un compás no aparece en el corpus de correcciones."""
    doc = _make_document(
        (
            Event(kind=EventKind.NOTE, voice=0, pitch="F#4", duration_beats=Fraction(2)),
            Event(kind=EventKind.NOTE, voice=0, pitch="Fb4", duration_beats=Fraction(2)),
        ),
        key_signature=KeySignature(fifths=0),
    )
    assert ValidationEngine([KeyConsistencyRule()]).validate(doc) == []


def _piano(upper: tuple[int | None, ...], lower: tuple[int | None, ...]) -> ScoreDocument:
    """Un piano con la armadura de cada compás (None: la que venga de antes)."""

    def staff(index: int, keys: tuple[int | None, ...], pitch: str, clef: Clef) -> Staff:
        return Staff(
            id=f"piano-staff-{index}",
            measures=tuple(
                Measure(
                    number=number,
                    events=(
                        Event(
                            kind=EventKind.NOTE, voice=0, pitch=pitch, duration_beats=Fraction(4)
                        ),
                    ),
                    time_signature=TimeSignature(4, 4),
                    clef=clef if number == 1 else None,
                    key_signature=None if fifths is None else KeySignature(fifths=fifths),
                )
                for number, fifths in enumerate(keys, start=1)
            ),
        )

    part = Part(
        id="part-0",
        staves=(staff(0, upper, "D4", Clef.treble()), staff(1, lower, "D3", Clef.bass())),
    )
    score = ScoreIR(parts=(part,))
    return ScoreDocument(
        id="piano-key-doc",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="fake", model_version="1.0"),
    )


def test_piano_staves_key_signature_discrepancy() -> None:
    findings = ValidationEngine([KeyConsistencyRule()]).validate(_piano((2,), (0,)))
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "key.consistency"
    assert f.severity == Severity.WARNING
    assert f.message == (
        "En el compás 1, la armadura del pentagrama de abajo (sin alteraciones) no coincide con "
        "la de arriba (dos sostenidos)."
    )
    assert (f.anchor.staff, f.anchor.measure) == (1, 1)


def test_a_discrepancy_is_flagged_once_from_where_it_starts() -> None:
    """Una vez por tramo de discrepancia, en el compás en que empieza; otra si vuelve a empezar."""
    findings = ValidationEngine([KeyConsistencyRule()]).validate(
        _piano((2, None, None, None, None), (2, 1, None, 2, 0))
    )
    assert [(f.anchor.staff, f.anchor.measure) for f in findings] == [(1, 2), (1, 5)]


def test_the_candidate_is_the_key_of_the_upper_staff() -> None:
    (finding,) = KeyConsistencyRule().evaluate(_piano((-3,), (-2,)))
    (candidate,) = finding.candidates
    assert candidate.op is EditOp.SET_KEY
    assert dict(candidate.after or {}) == {"fifths": -3}
    validate_after(_piano((-3,), (-2,)).score, candidate.anchor, candidate.op, candidate.after)


def test_different_parts_may_carry_different_keys() -> None:
    """Un instrumento transpositor lleva otra armadura que el piano (voz y piano, #239)."""
    piano = _piano((2,), (2,))
    voice_staff = replace(piano.score.parts[0].staves[0], id="voice-staff")
    voice = Part(
        id="part-voice",
        staves=(
            replace(
                voice_staff,
                measures=(replace(voice_staff.measures[0], key_signature=KeySignature(fifths=0)),),
            ),
        ),
    )
    score = ScoreIR(parts=(voice, piano.score.parts[0]))
    doc = replace(piano, score=score, anchors=build_anchor_index(score))
    assert ValidationEngine([KeyConsistencyRule()]).validate(doc) == []


def test_rule_does_not_mutate_document(tmp_path: Path) -> None:
    doc = _make_document(
        (Event(kind=EventKind.NOTE, voice=0, pitch="Bb4", duration_beats=Fraction(4)),),
        key_signature=KeySignature(fifths=1),
    )
    snapshot = doc
    ValidationEngine([KeyConsistencyRule()]).validate(doc)
    assert doc == snapshot
