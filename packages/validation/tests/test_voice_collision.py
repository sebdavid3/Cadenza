"""Pruebas de `voice.collision`: acorde mal formado (ADR-0040 §11)."""

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
    TimeSignature,
    build_anchor_index,
)
from cadenza.validation import ValidationEngine, VoiceCollisionRule


def _make_document(
    events: tuple[Event, ...],
    staff_id: str = "staff-0",
) -> ScoreDocument:
    measure = Measure(
        number=1,
        events=events,
        time_signature=TimeSignature(4, 4),
        clef=Clef.treble(),
    )
    staff = Staff(id=staff_id, measures=(measure,))
    part = Part(id="part-0", staves=(staff,))
    score = ScoreIR(parts=(part,))
    return ScoreDocument(
        id="test-collision-doc",
        score=score,
        anchors=build_anchor_index(score),
        provenance=Provenance(omr_engine="fake", model_version="1.0"),
    )


def test_rule_id() -> None:
    assert VoiceCollisionRule().rule_id == "voice.collision"


def test_valid_monophonic_and_chords_have_no_findings() -> None:
    # Compás con una nota sola y luego un acorde de 3 notas con la misma duración
    doc = _make_document(
        (
            Event(kind=EventKind.NOTE, voice=0, pitch="C4", duration_beats=Fraction(1)),
            # Acorde de blanca en tiempo 2: C4, E4, G4
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="C4",
                duration_beats=Fraction(2),
                is_chord=False,
            ),
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="E4",
                duration_beats=Fraction(2),
                is_chord=True,
            ),
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="G4",
                duration_beats=Fraction(2),
                is_chord=True,
            ),
            Event(kind=EventKind.REST, voice=0, duration_beats=Fraction(1)),
        )
    )
    engine = ValidationEngine([VoiceCollisionRule()])
    assert engine.validate(doc) == []


def test_chord_duration_mismatch_reports_error() -> None:
    # Nota base dura 2, pero nota del acorde dura 1 (desincronización temporal)
    doc = _make_document(
        (
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="C4",
                duration_beats=Fraction(2),
                is_chord=False,
            ),
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="G4",
                duration_beats=Fraction(1),
                is_chord=True,
            ),
            Event(kind=EventKind.REST, voice=0, duration_beats=Fraction(2)),
        )
    )
    findings = ValidationEngine([VoiceCollisionRule()]).validate(doc)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "voice.collision"
    assert f.severity == Severity.ERROR
    assert f.message == "En el acorde del tiempo 1, el Sol es una negra y el Do es una blanca."
    assert f.anchor.event_index == 1
    assert f.suggested_fix == (
        "Si en la partitura suenan juntas, iguala la figura; si el Sol va aparte, es de otra voz."
    )


def test_orphaned_chord_event_without_base_reports_error() -> None:
    # Primer evento de la voz marcado como is_chord=True
    doc = _make_document(
        (
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="E4",
                duration_beats=Fraction(4),
                is_chord=True,
            ),
        )
    )
    findings = ValidationEngine([VoiceCollisionRule()]).validate(doc)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "voice.collision"
    assert f.severity == Severity.ERROR
    assert f.message == (
        "El Mi del tiempo 1 está marcado como nota de un acorde, pero no tiene antes otra nota "
        "con la que sonar."
    )
    assert f.suggested_fix == "Revisa si es una nota suelta."


def test_duplicate_pitch_in_same_chord_reports_error() -> None:
    # Acorde con C4 y C4 en la misma voz
    doc = _make_document(
        (
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="C4",
                duration_beats=Fraction(4),
                is_chord=False,
            ),
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="C4",
                duration_beats=Fraction(4),
                is_chord=True,
            ),
        )
    )
    findings = ValidationEngine([VoiceCollisionRule()]).validate(doc)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "voice.collision"
    assert f.severity == Severity.ERROR
    assert f.message == "El acorde del tiempo 1 tiene dos veces el mismo Do."
    assert f.suggested_fix == "Borra uno de los dos."


def test_rest_as_chord_reports_error() -> None:
    # Silencio con is_chord=True
    doc = _make_document(
        (
            Event(
                kind=EventKind.REST,
                voice=0,
                duration_beats=Fraction(4),
                is_chord=True,
            ),
        )
    )
    findings = ValidationEngine([VoiceCollisionRule()]).validate(doc)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "voice.collision"
    assert f.severity == Severity.ERROR
    assert f.message == "El silencio del tiempo 1 está dentro de un acorde."
    assert f.suggested_fix == "Revisa si es una nota del acorde o un silencio de otra voz."


def test_a_note_without_duration_is_a_grace_note_and_not_an_error() -> None:
    """Se retira la «duración no positiva» de una nota (ADR-0040 §11): una nota de duración 0
    o nula es una nota de adorno (ADR-0028). En el corpus hay 524 y ninguna se corrigió."""
    doc = _make_document(
        (
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="C4",
                duration_beats=Fraction(0),
            ),
            Event(kind=EventKind.NOTE, voice=0, pitch="D4", duration_beats=Fraction(4)),
        )
    )
    assert ValidationEngine([VoiceCollisionRule()]).validate(doc) == []


def test_a_rest_without_duration_is_still_flagged() -> None:
    doc = _make_document(
        (
            Event(kind=EventKind.NOTE, voice=0, pitch="D4", duration_beats=Fraction(2)),
            Event(kind=EventKind.REST, voice=0, duration_beats=Fraction(0)),
            Event(kind=EventKind.NOTE, voice=0, pitch="E4", duration_beats=Fraction(1)),
        )
    )
    findings = ValidationEngine([VoiceCollisionRule()]).validate(doc)
    assert [(f.anchor.event_index, f.message, f.suggested_fix) for f in findings] == [
        (1, "El silencio del tiempo 3 no dura nada.", "Revisa su figura en la partitura.")
    ]


def test_rule_does_not_mutate_document(tmp_path: Path) -> None:
    doc = _make_document(
        (
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="C4",
                duration_beats=Fraction(4),
                is_chord=True,
            ),
        )
    )
    snapshot = doc
    ValidationEngine([VoiceCollisionRule()]).validate(doc)
    assert doc == snapshot
