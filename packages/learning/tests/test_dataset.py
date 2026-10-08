"""Pruebas del `DatasetBuilder` (alineación por ancla, todas las EditOps, hash y features)."""

from __future__ import annotations

from fractions import Fraction

from cadenza.domain import EditOp
from cadenza.learning import (
    DatasetBuilder,
    compute_correction_magnitude,
    dataset_hash,
)

from .support import make_anchor, make_document, make_edit, make_finding


def test_builds_samples_with_magnitude_and_error_density() -> None:
    document = make_document()
    edits = [
        make_edit(1, make_anchor(0), "C4", "D4"),
        make_edit(2, make_anchor(1), "D4", "F4"),
    ]
    findings = [make_finding(make_anchor(0))]

    samples = DatasetBuilder().build(document, edits, findings)

    assert len(samples) == 2
    first, second = samples
    assert first.before_pitch == "C4"
    assert first.after_pitch == "D4"
    assert first.correction_magnitude == 2.0
    assert first.error_density == 0.5  # 1 finding / 2 eventos del compás
    assert second.correction_magnitude == 3.0
    assert second.error_density == 0.5


def test_builds_samples_for_all_edit_ops_with_defined_magnitude() -> None:
    document = make_document()
    anchor = make_anchor(0)

    # 1. SET_PITCH (semitono C4 -> D4 = 2)
    e_pitch = make_edit(1, anchor, "C4", "D4", op=EditOp.SET_PITCH)
    # 2. SET_DURATION (1/4 -> 1/2 = 0.25 de diferencia en tiempos)
    e_dur = make_edit(2, anchor, None, None, op=EditOp.SET_DURATION)
    object.__setattr__(e_dur, "before", {"duration_beats": Fraction(1, 4)})
    object.__setattr__(e_dur, "after", {"duration_beats": Fraction(1, 2)})
    # 3. SET_ACCIDENTAL (natural -> sostenido = 1.0)
    e_acc = make_edit(3, anchor, None, None, op=EditOp.SET_ACCIDENTAL)
    object.__setattr__(e_acc, "before", {"accidental": ""})
    object.__setattr__(e_acc, "after", {"accidental": "#"})
    # 4. INSERT_EVENT (inserta evento de 1 tiempo)
    e_ins = make_edit(4, anchor, None, None, op=EditOp.INSERT_EVENT)
    object.__setattr__(e_ins, "before", None)
    object.__setattr__(
        e_ins, "after", {"kind": "note", "duration_beats": Fraction(1), "pitch": "G4"}
    )
    # 5. DELETE_EVENT (elimina evento de 2 tiempos)
    e_del = make_edit(5, anchor, None, None, op=EditOp.DELETE_EVENT)
    object.__setattr__(
        e_del, "before", {"kind": "note", "duration_beats": Fraction(2), "pitch": "C4"}
    )
    object.__setattr__(e_del, "after", None)
    # 6. SET_CLEF (clave de sol a fa = 1.0)
    e_clef = make_edit(6, anchor, None, None, op=EditOp.SET_CLEF)
    object.__setattr__(e_clef, "before", {"sign": "G", "line": 2})
    object.__setattr__(e_clef, "after", {"sign": "F", "line": 4})
    # 7. SET_KEY (Do mayor [0] a Re mayor [2] = 2.0)
    e_key = make_edit(7, anchor, None, None, op=EditOp.SET_KEY)
    object.__setattr__(e_key, "before", {"fifths": 0})
    object.__setattr__(e_key, "after", {"fifths": 2})

    edits = [e_pitch, e_dur, e_acc, e_ins, e_del, e_clef, e_key]
    samples = DatasetBuilder().build(document, edits)

    assert len(samples) == 7
    by_op = {s.op: s for s in samples}

    assert by_op[EditOp.SET_PITCH].correction_magnitude == 2.0
    assert by_op[EditOp.SET_DURATION].correction_magnitude == 0.25
    assert by_op[EditOp.SET_ACCIDENTAL].correction_magnitude == 1.0
    assert by_op[EditOp.INSERT_EVENT].correction_magnitude == 1.0
    assert by_op[EditOp.DELETE_EVENT].correction_magnitude == 2.0
    assert by_op[EditOp.SET_CLEF].correction_magnitude == 1.0
    assert by_op[EditOp.SET_KEY].correction_magnitude == 2.0


def test_compute_correction_magnitude_stand_alone() -> None:
    # Verificación directa de las funciones puras de cálculo de magnitud
    assert compute_correction_magnitude(EditOp.SET_PITCH, {"pitch": "A4"}, {"pitch": "A4"}) == 0.0
    assert compute_correction_magnitude(EditOp.SET_PITCH, {"pitch": "C4"}, {"pitch": "G4"}) == 7.0
    assert (
        compute_correction_magnitude(
            EditOp.SET_ACCIDENTAL, {"accidental": "b"}, {"accidental": "#"}
        )
        == 2.0
    )
    assert (
        compute_correction_magnitude(
            EditOp.SET_ACCIDENTAL, {"accidental": "bb"}, {"accidental": "##"}
        )
        == 4.0
    )
    assert (
        compute_correction_magnitude(
            EditOp.SET_DURATION, {"duration_beats": "1"}, {"duration_beats": "3/2"}
        )
        == 0.5
    )
    assert compute_correction_magnitude(EditOp.SET_KEY, {"fifths": -1}, {"fifths": 2}) == 3.0
    assert compute_correction_magnitude(EditOp.SET_CLEF) == 1.0


def test_ignores_other_documents() -> None:
    document = make_document()
    edits = [
        make_edit(1, make_anchor(0), "C4", "D4", op=EditOp.SET_DURATION),
        make_edit(2, make_anchor(0), "C4", "D4", document_id="other"),
        make_edit(3, make_anchor(0), "C4", "D4"),
    ]

    samples = DatasetBuilder().build(document, edits)

    # Ambos edits de doc-1 (SET_DURATION y SET_PITCH) se incluyen; 'other' se descarta
    assert [sample.document_id for sample in samples] == ["doc-1", "doc-1"]
    assert {sample.op for sample in samples} == {EditOp.SET_DURATION, EditOp.SET_PITCH}


def test_sample_references_image_sha256() -> None:
    document = make_document()
    edits = [make_edit(1, make_anchor(0), "C4", "D4")]

    # Con hash explícito
    samples = DatasetBuilder().build(document, edits, image_sha256="abc123sha256")
    assert len(samples) == 1
    assert samples[0].image_sha256 == "abc123sha256"

    # Con hash por provenance si no se provee explícito
    doc_with_hash = make_document()
    object.__setattr__(doc_with_hash.provenance, "source_image_hash", "provenance_hash_456")
    samples_prov = DatasetBuilder().build(doc_with_hash, edits)
    assert len(samples_prov) == 1
    assert samples_prov[0].image_sha256 == "provenance_hash_456"


def test_dataset_hash_is_deterministic() -> None:
    document = make_document()
    edits = [
        make_edit(1, make_anchor(0), "C4", "D4"),
        make_edit(2, make_anchor(1), "D4", "E4"),
    ]
    builder = DatasetBuilder()
    samples1 = builder.build(document, edits, image_sha256="sha1")
    samples2 = builder.build(document, edits, image_sha256="sha1")

    # Mismas muestras producen exactamente el mismo hash SHA-256
    hash1 = dataset_hash(samples1)
    hash2 = dataset_hash(samples2)
    assert isinstance(hash1, str)
    assert len(hash1) == 64
    assert hash1 == hash2

    # Inversión de orden en la lista produce el mismo hash (es insensible al orden de entrada)
    reversed_samples = list(reversed(samples1))
    assert dataset_hash(reversed_samples) == hash1

    # Cambio de imagen produce distinto hash
    samples_diff_img = builder.build(document, edits, image_sha256="sha2")
    assert dataset_hash(samples_diff_img) != hash1


def test_build_preserves_origin_bbox_across_structural_edits() -> None:
    document = make_document()
    edits = [
        make_edit(1, make_anchor(0), None, "Bb3", op=EditOp.INSERT_EVENT),
        make_edit(2, make_anchor(2), "D4", "E4", op=EditOp.SET_PITCH),
    ]
    samples = DatasetBuilder().build(document, edits)
    # Tanto INSERT_EVENT como SET_PITCH generan muestras
    pitch_samples = [s for s in samples if s.op == EditOp.SET_PITCH]
    assert len(pitch_samples) == 1
    sample = pitch_samples[0]
    assert sample.anchor.event_index == 1
    assert sample.before_pitch == "D4"
    assert sample.after_pitch == "E4"


def test_build_only_accepts_finalized_sessions() -> None:
    document = make_document()
    edits = [make_edit(1, make_anchor(0), "C4", "D4")]
    builder = DatasetBuilder()

    # Sesión finalizada produce muestras
    assert len(builder.build(document, edits, status="finalized")) == 1

    # Sesiones en corrección, transcritas o fallidas no producen muestras
    assert builder.build(document, edits, status="correcting") == ()
    assert builder.build(document, edits, status="transcribed") == ()
    assert builder.build(document, edits, status="failed") == ()


def test_build_excludes_undone_edits_and_compensatory_reversions() -> None:
    document = make_document()
    edits = [
        # Edit 1 y su reversión compensatoria Edit 2
        make_edit(1, make_anchor(0), "C4", "D4"),
        make_edit(2, make_anchor(0), "D4", "C4", reverts_edit_id="edit-1"),
        # Edit 3 activo que persiste
        make_edit(3, make_anchor(1), "D4", "E4"),
    ]
    builder = DatasetBuilder()
    samples = builder.build(document, edits, status="finalized")

    # Solo Edit 3 debe generar muestra; Edit 1 y Edit 2 se ignoran (#35)
    assert len(samples) == 1
    assert samples[0].before_pitch == "D4"
    assert samples[0].after_pitch == "E4"
    assert samples[0].anchor.event_index == 1
