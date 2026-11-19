"""Pruebas de `exp_16`: HOMR sobre la música manuscrita de MUSCIMA++ (#102)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from cadenza.learning.tables import corpus_tables
from cadenza.omr import OMRTranscriptionError

from ml.experiments import common, external_corpus
from ml.experiments import exp_16_muscima_homr as exp_16

from .muscima_support import Page, Staff, melody_musicxml, to_xml


def _melody() -> Page:
    """Un compás de 4/4 en clave de sol: G4 A4 B4 C5, negras."""
    page = Page()
    staff = Staff(page, top=200)
    staff.clef("gClef", 10)
    staff.time(60, 4, 4)
    for i, delta in enumerate((-2, -1, 0, 1)):
        staff.note(delta, 120 + 40 * i)
    staff.separator(300)
    return page


def _grand_staff() -> Page:
    page = Page()
    staff = Staff(page, top=200)
    staff.clef("gClef", 10)
    staff.note(0, 120)
    page.add("brace", 200, 0, 10, 400, (staff.id,))
    return page


def _layout(tmp_path: Path, pages: dict[str, Page], *, white_on_black: bool = True) -> Path:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    data = tmp_path / "data"
    annotations = data / exp_16.ANNOTATIONS
    images = data / exp_16.IMAGES
    annotations.mkdir(parents=True)
    images.mkdir(parents=True)
    for name, page in pages.items():
        (annotations / f"{name}.xml").write_text(to_xml(page.nodes, name), encoding="utf-8")
        image = np.zeros((40, 60), dtype=np.uint8)
        image[10:12, :] = 255
        cv2.imwrite(str(images / f"{name}.png"), image if white_on_black else 255 - image)
    return data


A = "CVC-MUSCIMA_W-01_N-01_D-ideal"
B = "CVC-MUSCIMA_W-02_N-01_D-ideal"
C = "CVC-MUSCIMA_W-01_N-02_D-ideal"


# --- Preparación -------------------------------------------------------------------------


def test_prepare_inverts_white_on_black_images_and_records_hashes(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    data = _layout(tmp_path, {A: _melody(), C: _grand_staff()})

    manifest = exp_16.prepare(data)

    assert manifest["count"] == 2
    entries = {e["id"]: e for e in manifest["entries"]}
    entry = entries[A]
    assert (entry["page"], entry["writer"], entry["inverted"]) == ("01", "01", True)
    assert entry["image"] == f"muscima/exp_16/images/{A}.png"
    assert len(entry["image_sha256"]) == 64 and len(entry["annotation_sha256"]) == 64
    prepared = cv2.imread(str(data / entry["image"]), cv2.IMREAD_GRAYSCALE)
    assert prepared[0, 0] == 255 and prepared[10, 0] == 0  # negro sobre blanco
    written = json.loads((data / "muscima" / "exp_16" / "manifest.json").read_text("utf-8"))
    assert [e["id"] for e in written["entries"]] == [A, C]
    with pytest.raises(FileExistsError, match="--force"):
        exp_16.prepare(data)


def test_prepare_keeps_black_on_white_images(tmp_path: Path) -> None:
    data = _layout(tmp_path, {A: _melody()}, white_on_black=False)
    manifest = exp_16.prepare(data)
    assert manifest["entries"][0]["inverted"] is False


def test_prepare_fails_without_data_or_with_unpaired_files(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="MUSCIMA"):
        exp_16.prepare(tmp_path / "nothing")
    data = _layout(tmp_path, {A: _melody(), C: _grand_staff()})
    (data / exp_16.IMAGES / f"{C}.png").unlink()
    with pytest.raises(ValueError, match="sin pareja"):
        exp_16.prepare(data)


# --- Transcripción y medición ------------------------------------------------------------


class _Engine:
    engine_id = "homr"
    device = "cpu"

    def __init__(self, outputs: dict[str, str], fail_on: set[str]) -> None:
        self.outputs = outputs
        self.fail_on = fail_on
        self.calls: list[str] = []

    def transcribe_musicxml(self, image_path: Path) -> str:
        name = image_path.stem
        self.calls.append(name)
        if name in self.fail_on:
            raise OMRTranscriptionError("No staffs found")
        return self.outputs[name]


def _run(tmp_path: Path) -> tuple[Path, _Engine]:
    data = _layout(tmp_path, {A: _melody(), B: _melody(), C: _grand_staff()})
    exp_16.prepare(data)
    manifest_path = data / "muscima" / "exp_16" / "manifest.json"
    engine = _Engine(
        {
            A: melody_musicxml([("G", 4, 1), ("A", 4, 1), ("D", 5, 1), ("C", 5, 1)]),
            B: melody_musicxml([("G", 4, 1), ("A", 4, 1), ("B", 4, 1), ("C", 5, 1)]),
        },
        fail_on={C},
    )
    result = external_corpus.transcribe(manifest_path, label="exp_16", engine=engine)
    assert result == {"written": 2, "reused": 0, "failures": 1}
    return manifest_path, engine


def test_transcribe_resumes_without_repeating(tmp_path: Path) -> None:
    manifest_path, engine = _run(tmp_path)
    again = external_corpus.transcribe(manifest_path, label="exp_16", engine=engine)
    assert again == {"written": 0, "reused": 3, "failures": 1}
    assert sorted(engine.calls) == sorted([A, B, C])


def test_build_measures_failures_counts_conversion_and_corrections(tmp_path: Path) -> None:
    manifest_path, _ = _run(tmp_path)

    summary = exp_16.build(manifest_path, with_omr_ned=True)

    assert summary["transcription"]["failures"] == {"cases": 1, "n": 3, "rate": 0.3333}
    assert summary["conversion"]["converted"]["cases"] == 2
    assert summary["conversion"]["not_convertible_by_reason"] == {"multi_staff": 1}
    single = summary["counts"]["by_texture"]["single_staff"]
    assert (single["noteheads_annotated"], single["notes_read"]) == (8, 8)
    subset = summary["converted_subset"]
    assert subset["derived"] == 2
    assert subset["verification"]["cases"] == 2
    assert subset["edit_distribution"]["same_measure_count"]["counts"]["SetPitch"] == 1
    assert subset["edit_distribution"]["same_measure_count"]["counts"]["Total"] == 1
    assert subset["measure_count_match"]["rate"] == 1.0
    assert subset["omr_ned"]["count"] == 2 and subset["omr_ned"]["median"] > 0
    assert subset["ser"]["count"] == 2
    quality = summary["truth_quality"]
    assert quality["measures_filled_exactly"] == {"cases": 2, "n": 2, "rate": 1.0}
    agreement = quality["writer_agreement"]["by_page"]["01"]
    assert (agreement["versions"], agreement["pairs"], agreement["mean"]) == (2, 1, 0.0)

    results = common.RESULTS_DIR
    with (results / "muscima_homr_images.csv").open(encoding="utf-8") as handle:
        rows = {row["id"]: row for row in csv.DictReader(handle)}
    assert rows[A]["status"] == "derived" and rows[A]["SetPitch"] == "1"
    assert rows[B]["Total"] == "0" and rows[B]["ser"] == "0.0"
    assert rows[C]["status"] == "failure" and rows[C]["truth_reason"] == "multi_staff"
    assert rows[A]["split"] == rows[B]["split"]  # las versiones de una página, del mismo lado

    lines = (results / "muscima_correction_corpus.jsonl").read_text("utf-8").splitlines()
    records: list[dict[str, Any]] = [json.loads(line) for line in lines]
    assert {r["source"] for r in records} == {"muscima"}
    # `ml export-tables --corpus` lo lee con su origen y su obra.
    tables = corpus_tables(records)
    assert {row["source"] for row in tables["notas"]} == {"muscima"}
    assert {row["work_id"] for row in tables["partituras"]} == {"muscima-N-01"}
    assert {r["work_id"] for r in records} == {"muscima-N-01"}
    assert {r["incipit_id"] for r in records} == {A, B}
    fixed = [r for r in records if r["record"] == "event" and r["correction"]]
    assert [(r["read"]["pitch"], r["correction"]["pitch"]) for r in fixed] == [("D5", "B4")]
    run_info = json.loads((results / "exp_16_run_info.json").read_text("utf-8"))
    assert run_info["homr"]["device"] == "cpu" and len(run_info["corpus_sha256"]) == 64


def test_build_fails_while_the_sample_is_not_fully_transcribed(tmp_path: Path) -> None:
    data = _layout(tmp_path, {A: _melody(), B: _melody()})
    exp_16.prepare(data)
    manifest_path = data / "muscima" / "exp_16" / "manifest.json"
    with pytest.raises(ValueError, match="transcribe"):
        exp_16.build(manifest_path, with_omr_ned=False)
    engine = _Engine({A: melody_musicxml([("G", 4, 4)])}, fail_on=set())
    external_corpus.transcribe(manifest_path, label="exp_16", engine=engine, limit=1)
    with pytest.raises(ValueError, match="1 de 2"):
        exp_16.build(manifest_path, with_omr_ned=False)


def test_prepare_force_clears_the_predictions_of_the_previous_sample(tmp_path: Path) -> None:
    manifest_path, _ = _run(tmp_path)
    predictions = manifest_path.parent / "predictions"
    assert predictions.is_dir()
    exp_16.prepare(manifest_path.parents[2], force=True)
    assert not predictions.exists()


def test_an_omr_ned_failure_keeps_the_derived_corrections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, _ = _run(tmp_path)

    def broken(*_: object, **__: object) -> None:
        raise ValueError("musicdiff no lee el par")

    monkeypatch.setattr(external_corpus, "omr_ned_pair", broken)
    summary = exp_16.build(manifest_path, with_omr_ned=True)

    subset = summary["converted_subset"]
    assert subset["derived"] == 2 and subset["omr_ned"] is None
    assert set(subset["omr_ned_errors"]) == {A, B}
    assert subset["edit_distribution"]["same_measure_count"]["counts"]["SetPitch"] == 1
