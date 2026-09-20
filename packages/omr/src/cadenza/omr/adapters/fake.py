"""Adaptador OMR determinista para tests, CI y fases de UI/validación."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from cadenza.domain import (
    Event,
    EventKind,
    Measure,
    Part,
    Provenance,
    ScoreDocument,
    ScoreIR,
    Staff,
    TimeSignature,
    build_anchor_index,
)

from ..engine import OMREngine

FAKE_ENGINE_ID = "fake"
FAKE_MODEL_VERSION = "fake-1"
FAKE_DOCUMENT_ID = "fake-doc-0001"
FAKE_TIME_SIGNATURE = TimeSignature(4, 4)


def _sample_ir() -> ScoreIR:
    """`ScoreIR` hardcodeado y neutral: monofónico, dos compases, notas y silencio."""

    first_measure = Measure(
        number=1,
        events=(
            Event(kind=EventKind.NOTE, voice=0, pitch="C4", duration_beats=Fraction(1)),
            Event(kind=EventKind.NOTE, voice=0, pitch="D4", duration_beats=Fraction(1)),
            Event(kind=EventKind.REST, voice=0, duration_beats=Fraction(2)),
        ),
        time_signature=FAKE_TIME_SIGNATURE,
    )
    second_measure = Measure(
        number=2,
        events=(Event(kind=EventKind.NOTE, voice=0, pitch="E4", duration_beats=Fraction(4)),),
        time_signature=FAKE_TIME_SIGNATURE,
    )
    staff = Staff(id="part-0-staff-0", measures=(first_measure, second_measure))
    return ScoreIR(parts=(Part(id="part-0", staves=(staff,)),))


class FakeOMREngine(OMREngine):
    """Devuelve siempre el mismo `ScoreDocument` hardcodeado.

    No lee la imagen ni toca red, modelos o GPU. Su propósito es ejercitar la
    UI (Fase 3) y el motor de validación (Fase 2) de forma instantánea y en
    CI/CD, sin descargar pesos ni depender de hardware.
    """

    def __init__(self, document_id: str = FAKE_DOCUMENT_ID) -> None:
        self._document_id = document_id

    @property
    def engine_id(self) -> str:
        return FAKE_ENGINE_ID

    def transcribe(self, image_path: Path) -> ScoreDocument:
        score = _sample_ir()
        return ScoreDocument(
            id=self._document_id,
            score=score,
            anchors=build_anchor_index(score),
            provenance=Provenance(
                omr_engine=FAKE_ENGINE_ID,
                model_version=FAKE_MODEL_VERSION,
            ),
        )
