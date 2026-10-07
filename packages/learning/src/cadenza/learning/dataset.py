"""Construcción del dataset de aprendizaje activo (ADR-0008).

Traduce `(ScoreDocument, EditEvents, Findings)` a `TrainingSample` alineadas por
ancla. Es lógica pura: no toca GPU, base de datos ni el pipeline de HOMR.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from cadenza.domain import (
    Anchor,
    EditEvent,
    EditOp,
    Finding,
    ScoreDocument,
    origin_anchor,
)

from .pitch import pitch_to_midi, semitone_distance


@dataclass(frozen=True, slots=True)
class TrainingSample:
    """Par de entrenamiento derivado de una corrección humana."""

    document_id: str
    anchor: Anchor
    before_pitch: str | None
    after_pitch: str | None
    correction_magnitude: float
    error_density: float
    features: tuple[float, ...]

    def key(self) -> tuple[str, ...]:
        """Clave de orden determinista (documento + ruta lógica del ancla)."""

        return (self.document_id, *(str(part) for part in self.anchor.sort_key()))


MeasureKey = tuple[int, int, int]


def _event_counts(document: ScoreDocument) -> dict[MeasureKey, int]:
    counts: dict[MeasureKey, int] = {}
    for part_index, part in enumerate(document.score.parts):
        for staff_index, staff in enumerate(part.staves):
            for measure in staff.measures:
                key = (part_index, staff_index, measure.number)
                counts[key] = counts.get(key, 0) + len(measure.events)
    return counts


def _finding_counts(findings: Sequence[Finding]) -> dict[MeasureKey, int]:
    counts: dict[MeasureKey, int] = {}
    for finding in findings:
        key = (finding.anchor.part, finding.anchor.staff, finding.anchor.measure)
        counts[key] = counts.get(key, 0) + 1
    return counts


class DatasetBuilder:
    """Deriva las muestras de entrenamiento de un documento corregido."""

    def build(
        self,
        document: ScoreDocument,
        edits: Sequence[EditEvent],
        findings: Sequence[Finding] = (),
    ) -> tuple[TrainingSample, ...]:
        event_counts = _event_counts(document)
        finding_counts = _finding_counts(findings)
        samples: list[TrainingSample] = []

        for edit in edits:
            if edit.document_id != document.id or edit.op is not EditOp.SET_PITCH:
                continue
            before = edit.before.get("pitch") if edit.before else None
            after = edit.after.get("pitch") if edit.after else None
            before_pitch = before if isinstance(before, str) else None
            after_pitch = after if isinstance(after, str) else None

            orig = origin_anchor(edit.anchor, at_seq=edit.seq - 1, edits=edits)
            if orig is not None:
                orig_ref = document.anchors.get(orig)
                bbox = orig_ref.bbox if orig_ref is not None else orig.bbox
                confidence = orig_ref.confidence if orig_ref is not None else orig.confidence
                sample_anchor = replace(orig, bbox=bbox, confidence=confidence)
            else:
                sample_anchor = edit.anchor

            key = (sample_anchor.part, sample_anchor.staff, sample_anchor.measure)
            events = event_counts.get(key, 0)
            error_density = finding_counts.get(key, 0) / events if events else 0.0

            samples.append(
                TrainingSample(
                    document_id=document.id,
                    anchor=sample_anchor,
                    before_pitch=before_pitch,
                    after_pitch=after_pitch,
                    correction_magnitude=semitone_distance(before_pitch, after_pitch),
                    error_density=error_density,
                    features=(
                        float(sample_anchor.measure),
                        float(sample_anchor.voice),
                        float(sample_anchor.event_index),
                        float(pitch_to_midi(before_pitch) or 0),
                        float(pitch_to_midi(after_pitch) or 0),
                    ),
                )
            )

        return tuple(sorted(samples, key=TrainingSample.key))
