"""Los candidatos que entregan las reglas (ADR-0036 §3): los arreglos que cuadran."""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction

from cadenza.domain import (
    EditEvent,
    EditOp,
    Event,
    EventKind,
    KeySignature,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Staff,
    TimeSignature,
    apply_edit,
    build_anchor_index,
    validate_after,
)
from cadenza.validation import KeyConsistencyRule, MeasureBalanceRule


def _note(pitch: str, beats: str) -> Event:
    return Event(kind=EventKind.NOTE, pitch=pitch, duration_beats=Fraction(beats))


def _document(*events: Event, fifths: int = 0) -> ScoreDocument:
    measure = Measure(
        number=1,
        events=events,
        time_signature=TimeSignature(4, 4),
        key_signature=KeySignature(fifths=fifths),
    )
    score = ScoreIR(parts=(Part(id="P1", staves=(Staff(id="P1-S1", measures=(measure,)),)),))
    return ScoreDocument(
        id="doc", score=score, anchors=build_anchor_index(score), provenance=Provenance("fake")
    )


def test_missing_half_beat_offers_longer_figures_and_a_rest_at_the_end() -> None:
    # 4/4 con 3 negras y una corchea: falta media negra.
    document = _document(_note("C4", "1"), _note("D4", "1"), _note("E4", "1"), _note("F4", "1/2"))
    (finding,) = MeasureBalanceRule().evaluate(document)
    offered = {
        (c.op, c.anchor.event_index, tuple(sorted((c.after or {}).items())))
        for c in finding.candidates
    }
    assert (EditOp.SET_DURATION, 3, (("duration_beats", "1"),)) in offered
    assert (EditOp.SET_DURATION, 0, (("duration_beats", "3/2"),)) in offered
    assert (
        EditOp.INSERT_EVENT,
        4,
        (("duration_beats", "1/2"), ("kind", "rest")),
    ) in offered


def test_extra_beat_offers_shorter_figures_and_deleting_what_is_left_over() -> None:
    document = _document(*(_note(p, "1") for p in ("C4", "D4", "E4", "F4", "G4")))
    (finding,) = MeasureBalanceRule().evaluate(document)
    ops = {(c.op, c.anchor.event_index) for c in finding.candidates}
    assert (EditOp.DELETE_EVENT, 4) in ops
    # Una negra que pierde una negra se queda en nada: no es candidato.
    assert all(c.op is not EditOp.SET_DURATION for c in finding.candidates)


def test_every_balance_candidate_is_a_valid_edit_that_balances_the_measure() -> None:
    document = _document(_note("C4", "1"), _note("D4", "1"), _note("E4", "1"), _note("F4", "1/2"))
    (finding,) = MeasureBalanceRule().evaluate(document)
    assert finding.candidates
    for candidate in finding.candidates:
        validate_after(document.score, candidate.anchor, candidate.op, candidate.after)
        fixed = apply_edit(
            document.score,
            EditEvent(
                id="e",
                document_id="doc",
                seq=1,
                anchor=candidate.anchor,
                op=candidate.op,
                author="a",
                created_at=datetime(2026, 10, 30, tzinfo=UTC),
                after=candidate.after,
            ),
        )
        repaired = ScoreDocument(
            id="doc", score=fixed, anchors=build_anchor_index(fixed), provenance=Provenance("f")
        )
        assert MeasureBalanceRule().evaluate(repaired) == []


def test_flat_in_a_sharp_key_offers_the_key_accidental_and_natural() -> None:
    # Re mayor (2 sostenidos): un Fa bemol leído; la armadura pide Fa sostenido.
    document = _document(_note("Fb4", "4"), fifths=2)
    findings = KeyConsistencyRule().evaluate(document)
    (finding,) = [f for f in findings if "bemol inconsistente" in f.message]
    targets = [(c.op, (c.after or {}).get("accidental")) for c in finding.candidates]
    assert targets == [(EditOp.SET_ACCIDENTAL, "#"), (EditOp.SET_ACCIDENTAL, "")]
