"""Construcción del dataset de aprendizaje activo (ADR-0008, D16, D18).

Traduce `(ScoreDocument, EditEvents, Findings)` o sesiones de repositorio a
`TrainingSample` alineadas por ancla y cubriendo todas las operaciones de `EditOp`.
Es lógica pura: no toca GPU ni el pipeline de HOMR, ni accede directamente al ORM.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Any, Final

from cadenza.application.ports import EditEventRepository, SessionRepository
from cadenza.domain import (
    Anchor,
    EditEvent,
    EditOp,
    Finding,
    ScoreDocument,
    origin_anchor,
)

from .pitch import pitch_to_midi, semitone_distance

_ACCIDENTAL_SEMITONES: Final[dict[str, float]] = {
    "##": 2.0,
    "x": 2.0,
    "#": 1.0,
    "": 0.0,
    "natural": 0.0,
    "b": -1.0,
    "-": -1.0,
    "bb": -2.0,
    "--": -2.0,
}


def _parse_duration(val: Any) -> float | None:
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            return float(val)
        return float(Fraction(str(val)))
    except (ValueError, ZeroDivisionError):
        return None


def _extract_fifths(data: Any) -> int | None:
    if isinstance(data, Mapping):
        if "fifths" in data:
            try:
                return int(data["fifths"])
            except (ValueError, TypeError):
                pass
        if "key_signature" in data and isinstance(data["key_signature"], Mapping):
            try:
                return int(data["key_signature"]["fifths"])
            except (ValueError, TypeError):
                pass
    return None


def compute_correction_magnitude(
    op: EditOp,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
) -> float:
    """Calcula la magnitud de corrección de una operación de edición (D18).

    Cada `EditOp` cuenta con una métrica fundamentada:
    - `SET_PITCH`: distancia absoluta en semitonos entre alturas.
    - `SET_DURATION`: diferencia absoluta en duración en tiempos (beats).
    - `SET_ACCIDENTAL`: diferencia absoluta en semitonos producida por la alteración.
    - `INSERT_EVENT`: duración del evento insertado (o 1.0 por defecto).
    - `DELETE_EVENT`: duración del evento eliminado (o 1.0 por defecto).
    - `SET_CLEF`: magnitud unitaria 1.0 (cambio estructural discreto).
    - `SET_KEY`: diferencia absoluta en el círculo de quintas (o 1.0 si no es parseable).
    """
    if op is EditOp.SET_PITCH:
        before_p = before.get("pitch") if isinstance(before, Mapping) else None
        after_p = after.get("pitch") if isinstance(after, Mapping) else None
        before_str = str(before_p) if before_p is not None else None
        after_str = str(after_p) if after_p is not None else None
        dist = semitone_distance(before_str, after_str)
        if dist > 0.0:
            return dist
        return 0.0 if before_str == after_str and before_str is not None else 1.0

    if op is EditOp.SET_DURATION:
        b_dur = _parse_duration(
            before.get("duration_beats") if isinstance(before, Mapping) else None
        )
        a_dur = _parse_duration(after.get("duration_beats") if isinstance(after, Mapping) else None)
        if b_dur is not None and a_dur is not None:
            return abs(a_dur - b_dur)
        if a_dur is not None:
            return a_dur
        if b_dur is not None:
            return b_dur
        return 1.0

    if op is EditOp.SET_ACCIDENTAL:
        b_acc = (
            str(before.get("accidental", "") or "")
            if isinstance(before, Mapping) and before.get("accidental") is not None
            else ""
        )
        a_acc = (
            str(after.get("accidental", "") or "")
            if isinstance(after, Mapping) and after.get("accidental") is not None
            else ""
        )
        b_semi = _ACCIDENTAL_SEMITONES.get(b_acc)
        a_semi = _ACCIDENTAL_SEMITONES.get(a_acc)
        if b_semi is not None and a_semi is not None:
            diff = abs(a_semi - b_semi)
            return diff if diff > 0.0 else (0.0 if b_acc == a_acc else 1.0)
        return 1.0 if b_acc != a_acc else 0.0

    if op is EditOp.INSERT_EVENT:
        dur = _parse_duration(after.get("duration_beats") if isinstance(after, Mapping) else None)
        return dur if dur is not None and dur > 0.0 else 1.0

    if op is EditOp.DELETE_EVENT:
        dur = _parse_duration(before.get("duration_beats") if isinstance(before, Mapping) else None)
        return dur if dur is not None and dur > 0.0 else 1.0

    if op is EditOp.SET_CLEF:
        return 1.0

    if op is EditOp.SET_KEY:
        b_fifths = _extract_fifths(before)
        a_fifths = _extract_fifths(after)
        if b_fifths is not None and a_fifths is not None:
            diff = float(abs(a_fifths - b_fifths))
            return diff if diff > 0.0 else (0.0 if b_fifths == a_fifths else 1.0)
        return 1.0

    return 1.0


def _extract_pitches(
    op: EditOp,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> tuple[str | None, str | None]:
    b_pitch = before.get("pitch") if isinstance(before, Mapping) else None
    a_pitch = after.get("pitch") if isinstance(after, Mapping) else None
    return (
        str(b_pitch) if b_pitch is not None else None,
        str(a_pitch) if a_pitch is not None else None,
    )


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
    op: EditOp = EditOp.SET_PITCH
    image_sha256: str | None = None
    seq: int = 0
    before: Mapping[str, Any] | None = None
    after: Mapping[str, Any] | None = None

    def key(self) -> tuple[str, ...]:
        """Clave de orden determinista (documento + seq + op + ruta lógica del ancla)."""

        return (
            self.document_id,
            str(self.seq),
            str(self.op),
            *(str(part) for part in self.anchor.sort_key()),
        )


def dataset_hash(samples: Sequence[TrainingSample]) -> str:
    """Calcula un hash SHA-256 canónico y determinista sobre una secuencia de muestras."""
    hasher = hashlib.sha256()
    for sample in sorted(samples, key=TrainingSample.key):
        payload = {
            "document_id": sample.document_id,
            "image_sha256": sample.image_sha256 or "",
            "seq": sample.seq,
            "op": sample.op.value,
            "anchor": list(sample.anchor.sort_key()),
            "correction_magnitude": round(sample.correction_magnitude, 6),
            "error_density": round(sample.error_density, 6),
            "features": [round(f, 6) for f in sample.features],
            "before_pitch": sample.before_pitch,
            "after_pitch": sample.after_pitch,
            "before": dict(sample.before) if sample.before is not None else None,
            "after": dict(sample.after) if sample.after is not None else None,
        }
        canonical_bytes = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
        hasher.update(canonical_bytes)
    return hasher.hexdigest()


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
    """Deriva las muestras de entrenamiento de un documento corregido (ADR-0008, D18)."""

    def build(
        self,
        document: ScoreDocument,
        edits: Sequence[EditEvent],
        findings: Sequence[Finding] = (),
        *,
        status: str = "finalized",
        image_sha256: str | None = None,
    ) -> tuple[TrainingSample, ...]:
        if status != "finalized":
            return ()
        effective_image_sha256 = image_sha256 or document.provenance.source_image_hash
        event_counts = _event_counts(document)
        finding_counts = _finding_counts(findings)
        samples: list[TrainingSample] = []

        reverted_ids = {e.reverts_edit_id for e in edits if e.reverts_edit_id is not None}

        for edit in edits:
            if edit.document_id != document.id:
                continue
            if edit.is_reversion or edit.id in reverted_ids:
                continue

            before_pitch, after_pitch = _extract_pitches(edit.op, edit.before, edit.after)
            magnitude = compute_correction_magnitude(edit.op, edit.before, edit.after)

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
                    correction_magnitude=magnitude,
                    error_density=error_density,
                    features=(
                        float(sample_anchor.measure),
                        float(sample_anchor.voice),
                        float(sample_anchor.event_index),
                        float(pitch_to_midi(before_pitch) or 0),
                        float(pitch_to_midi(after_pitch) or 0),
                    ),
                    op=edit.op,
                    image_sha256=effective_image_sha256,
                    seq=edit.seq,
                    before=edit.before,
                    after=edit.after,
                )
            )

        return tuple(sorted(samples, key=TrainingSample.key))

    def read_from_repositories(
        self,
        session_repository: SessionRepository,
        edit_event_repository: EditEventRepository,
        *,
        status: str = "finalized",
        owner_id: str | None = None,
    ) -> tuple[TrainingSample, ...]:
        """Conveniencia para invocar RepositoryDatasetReader sobre este builder."""
        return RepositoryDatasetReader(self).read_dataset(
            session_repository=session_repository,
            edit_event_repository=edit_event_repository,
            status=status,
            owner_id=owner_id,
        )


class RepositoryDatasetReader:
    """Lector que construye un dataset a partir de sesiones y eventos persistidos (D16, ADR-0008).

    Recorre las sesiones finalizadas y sus eventos de edición a través de los
    puertos abstractos `SessionRepository` y `EditEventRepository`, sin acoplarse
    al ORM ni a la base de datos subyacente.
    """

    def __init__(self, dataset_builder: DatasetBuilder | None = None) -> None:
        self._builder = dataset_builder or DatasetBuilder()

    def read_dataset(
        self,
        session_repository: SessionRepository,
        edit_event_repository: EditEventRepository,
        *,
        status: str = "finalized",
        owner_id: str | None = None,
    ) -> tuple[TrainingSample, ...]:
        sessions = session_repository.list(owner_id=owner_id, status=status)
        all_samples: list[TrainingSample] = []

        for s in sessions:
            if s.status != status:
                continue
            document = ScoreDocument.from_primitive(s.document)
            persisted_findings = session_repository.list_findings(
                s.id, latest_only=False, include_dismissed=True
            )
            findings = [
                Finding.from_primitive(
                    {
                        "anchor": pf.anchor,
                        "rule_id": pf.rule_id,
                        "severity": pf.severity,
                        "message": pf.message,
                        "suggested_fix": pf.suggested_fix,
                        "at_seq": pf.at_seq,
                    }
                )
                for pf in persisted_findings
            ]
            edits = edit_event_repository.list_events(s.id)
            image_sha256 = s.image_artifact or document.provenance.source_image_hash

            session_samples = self._builder.build(
                document=document,
                edits=edits,
                findings=findings,
                status=s.status,
                image_sha256=image_sha256,
            )
            all_samples.extend(session_samples)

        return tuple(sorted(all_samples, key=TrainingSample.key))
