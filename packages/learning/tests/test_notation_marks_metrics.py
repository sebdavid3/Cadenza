"""Las marcas de notación no cambian las métricas de los experimentos (ADR-0031, #213).

`ml/experiments` (exp_01, exp_03, exp_05 y `common.py`) lee las partituras con `read_score` y
calcula, con estas mismas funciones, la secuencia de símbolos y la SER, las ediciones derivadas
del diff con la verdad, su distribución, la igualdad estructural tras materializarlas, los
hallazgos del validador por compás y las muestras del dataset. Con las mismas partituras, con
y sin marcas, todo debe dar exactamente lo mismo (CLAUDE.md §8). Aquí no se ejecuta ningún
experimento: solo las funciones de las que dependen.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from cadenza.domain import (
    Anchor,
    EditEvent,
    EditOp,
    Provenance,
    ScoreDocument,
    ScoreIR,
    apply_edit,
    build_anchor_index,
    materialize,
)
from cadenza.interchange import read_score
from cadenza.learning import (
    DatasetBuilder,
    count_edits_by_op,
    derive_edit_events,
    evaluate_pair,
    is_structurally_equal,
    score_ser_pair,
    score_to_symbol_sequence,
)
from cadenza.validation import ValidationEngine

# Las fixtures de `interchange` llevan todas las marcas del alcance, en piano y en una voz.
FIXTURES = Path(__file__).resolve().parents[2] / "interchange" / "tests" / "fixtures"
MARKED = ("marks_piano.musicxml", "marks_melody.musicxml")


def _strip_marks(xml_text: str) -> str:
    root = ET.fromstring(xml_text.encode("utf-8"))
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag == "notations":
                for mark in list(child):
                    if mark.tag in ("slur", "articulations", "fermata"):
                        child.remove(mark)
                if len(child) == 0:
                    parent.remove(child)
            elif child.tag == "direction" and (
                child.find("direction-type/dynamics") is not None
                or child.find("direction-type/wedge") is not None
            ):
                parent.remove(child)
    return ET.tostring(root, encoding="unicode")


def _has_marks(score: ScoreIR) -> bool:
    return any(
        measure.dynamics
        or measure.wedges
        or any(e.articulations or e.fermata or e.slurs for e in measure.events)
        for part in score.parts
        for staff in part.staves
        for measure in staff.measures
    )


@pytest.fixture(params=MARKED)
def scores(request: pytest.FixtureRequest, tmp_path: Path) -> tuple[ScoreIR, ScoreIR]:
    """La misma partitura leída con `read_score` con sus marcas y sin ninguna."""

    source = FIXTURES / str(request.param)
    plain_file = tmp_path / f"plain-{source.name}"
    plain_file.write_text(_strip_marks(source.read_text(encoding="utf-8")), encoding="utf-8")
    marked, plain = read_score(source), read_score(plain_file)
    assert _has_marks(marked)
    assert not _has_marks(plain)
    return marked, plain


def _anchor(measure: int, event_index: int) -> Anchor:
    return Anchor(
        part=0,
        staff=0,
        measure=measure,
        voice=0,
        event_index=event_index,
        staff_id="part-0-staff-0",
    )


def _predicted(score: ScoreIR) -> ScoreIR:
    """Una «transcripción» con errores de altura, duración y una nota de menos."""

    edits = [
        (EditOp.SET_PITCH, _anchor(1, 0), {"pitch": "G4"}),
        (EditOp.SET_DURATION, _anchor(2, 0), {"duration_beats": "1"}),
        (EditOp.DELETE_EVENT, _anchor(1, 1), None),
    ]
    for seq, (op, anchor, after) in enumerate(edits, start=1):
        score = apply_edit(
            score,
            EditEvent(
                id=f"p{seq}",
                document_id="pred",
                seq=seq,
                anchor=anchor,
                op=op,
                author="error",
                created_at=datetime(2026, 10, 24, tzinfo=UTC),
                after=after,
            ),
        )
    return score


def _comparable(edits: Sequence[EditEvent]) -> list[tuple[Any, ...]]:
    """Las ediciones sin su identificador ni su fecha, que son aleatorios."""

    return [
        (
            e.seq,
            e.anchor,
            e.op,
            None if e.before is None else dict(e.before),
            None if e.after is None else dict(e.after),
        )
        for e in edits
    ]


def test_symbol_sequence_ignores_marks(scores: tuple[ScoreIR, ScoreIR]) -> None:
    marked, plain = scores
    for apply_key_signature in (True, False):
        assert score_to_symbol_sequence(
            marked, apply_key_signature=apply_key_signature
        ) == score_to_symbol_sequence(plain, apply_key_signature=apply_key_signature)


def test_ser_ignores_marks(scores: tuple[ScoreIR, ScoreIR]) -> None:
    marked, plain = scores
    expected = score_ser_pair(plain, _predicted(plain))
    assert expected.edit_distance > 0
    # La verdad y la transcripción con marcas, sin ellas o solo una con ellas (HOMR no da
    # dinámicas ni reguladores): la misma SER.
    for gt in (marked, plain):
        for pred in (_predicted(marked), _predicted(plain)):
            assert score_ser_pair(gt, pred) == expected


def test_derived_edits_ignore_marks(scores: tuple[ScoreIR, ScoreIR]) -> None:
    marked, plain = scores
    expected = derive_edit_events(_predicted(plain), plain, document_id="d")
    assert expected
    for gt in (marked, plain):
        for pred in (_predicted(marked), _predicted(plain)):
            edits = derive_edit_events(pred, gt, document_id="d")
            assert _comparable(edits) == _comparable(expected)
            assert count_edits_by_op(edits) == count_edits_by_op(expected)
            assert is_structurally_equal(materialize(pred, edits), gt)


def test_validation_records_and_dataset_ignore_marks(scores: tuple[ScoreIR, ScoreIR]) -> None:
    """Hallazgos por compás (exp_01) y muestras del dataset (`common.py`), iguales."""

    marked, plain = scores
    validator = ValidationEngine()
    expected_records = evaluate_pair("d", _predicted(plain), plain, validator)
    assert evaluate_pair("d", _predicted(marked), marked, validator) == expected_records

    def samples(pred: ScoreIR, gt: ScoreIR) -> list[dict[str, Any]]:
        document = ScoreDocument(
            id="d",
            score=pred,
            anchors=build_anchor_index(pred),
            provenance=Provenance(omr_engine="homr", rules_version=validator.rules_version),
        )
        built = DatasetBuilder().build(
            document=document,
            edits=derive_edit_events(pred, gt, document_id="d"),
            findings=validator.validate(document),
        )
        return [
            {**sample.to_primitive(), "before": sample.before, "after": sample.after}
            for sample in built
        ]

    assert samples(_predicted(marked), marked) == samples(_predicted(plain), plain)
