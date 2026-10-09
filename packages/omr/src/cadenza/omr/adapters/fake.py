"""Adaptador OMR determinista para tests, CI y fases de UI/validación."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

from cadenza.domain import (
    BBox,
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
from PIL import Image

from ..engine import OMREngine
from ..preprocessing import PreprocessingConfig, preprocess_image

FAKE_ENGINE_ID = "fake"
FAKE_MODEL_VERSION = "fake-1"
FAKE_DOCUMENT_ID = "fake-doc-0001"
FAKE_TIME_SIGNATURE = TimeSignature(4, 4)

_BBOX_WIDTH = 16.0
_BBOX_HEIGHT = 20.0
_BBOX_Y = 40.0
_BBOX_START_X = 20.0
_BBOX_STEP = 30.0


def _bbox(index: int) -> BBox:
    """Rectángulo sintético determinista (x0, y0, x1, y1) para overlays de la UI."""

    x0 = _BBOX_START_X + index * _BBOX_STEP
    return (x0, _BBOX_Y, x0 + _BBOX_WIDTH, _BBOX_Y + _BBOX_HEIGHT)


def _sample_ir() -> ScoreIR:
    """`ScoreIR` hardcodeado y neutral: monofónico, dos compases, notas y silencio.

    Cada evento lleva un `bbox` sintético para que la UI (Fase 3B) pueda probar el
    renderizado de overlays sin depender de coordenadas reales del OMR.
    """

    first_measure = Measure(
        number=1,
        events=(
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="C4",
                duration_beats=Fraction(1),
                bbox=_bbox(0),
            ),
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="D4",
                duration_beats=Fraction(1),
                bbox=_bbox(1),
            ),
            Event(
                kind=EventKind.REST,
                voice=0,
                duration_beats=Fraction(2),
                bbox=_bbox(2),
            ),
        ),
        time_signature=FAKE_TIME_SIGNATURE,
    )
    second_measure = Measure(
        number=2,
        events=(
            Event(
                kind=EventKind.NOTE,
                voice=0,
                pitch="E4",
                duration_beats=Fraction(4),
                bbox=_bbox(3),
            ),
        ),
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

    def __init__(
        self,
        document_id: str = FAKE_DOCUMENT_ID,
        *,
        model_version: str | None = None,
        preprocessing: PreprocessingConfig | None = None,
    ) -> None:
        self._document_id = document_id
        self._model_version = model_version
        self._preprocessing = preprocessing

    @classmethod
    def from_active_model(
        cls,
        model_registry: Any | None,
        artifact_store: Any | None = None,
        *,
        document_id: str = FAKE_DOCUMENT_ID,
        preprocessing: PreprocessingConfig | None = None,
    ) -> FakeOMREngine:
        """Instancia FakeOMREngine con la versión de modelo activa si existe (#21)."""
        if model_registry is None:
            return cls(document_id=document_id, preprocessing=preprocessing)
        active = model_registry.active()
        version_str = active.version if active is not None else None
        return cls(
            document_id=document_id,
            model_version=version_str,
            preprocessing=preprocessing,
        )

    @property
    def engine_id(self) -> str:
        return FAKE_ENGINE_ID

    def transcribe(self, image_path: Path) -> ScoreDocument:
        score = _sample_ir()
        preproc_meta = None
        if self._preprocessing is not None and self._preprocessing.enabled:
            if image_path.is_file():
                try:
                    with Image.open(image_path) as img:
                        _, preproc_meta = preprocess_image(img, self._preprocessing)
                except Exception:
                    preproc_meta = self._preprocessing.to_primitive()
            else:
                preproc_meta = self._preprocessing.to_primitive()

        return ScoreDocument(
            id=self._document_id,
            score=score,
            anchors=build_anchor_index(score),
            provenance=Provenance(
                omr_engine=FAKE_ENGINE_ID,
                model_version=self._model_version or FAKE_MODEL_VERSION,
                device="cpu",
                preprocessing=preproc_meta,
            ),
        )
