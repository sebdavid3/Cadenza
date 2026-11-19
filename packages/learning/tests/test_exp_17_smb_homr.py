"""Pruebas de `exp_17`: HOMR sobre las regiones de SMB (#102), sin el conjunto real."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from cadenza.learning.tables import corpus_tables
from cadenza.omr import OMRTranscriptionError

from ml.experiments import common, external_corpus
from ml.experiments import exp_17_smb_homr as exp_17

from .muscima_support import melody_musicxml

KERN = "**kern\n*clefG2\n*k[]\n*M4/4\n=1\n4g\n4a\n4b\n4cc\n==\n*-\n"


def _png(width: int = 200, height: int = 100) -> bytes:
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    image = np.full((height, width), 255, dtype=np.uint8)
    image[40:42, :] = 0
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return bytes(encoded.tobytes())


def _pages() -> list[dict[str, Any]]:
    box = {"x": 10.0, "y": 20.0, "width": 50.0, "height": 40.0}
    return [
        {
            "id": "beethoven/sonata 1",
            "original_score": "beethoven/sonata01-1.krn",
            "page_texture": "pianoform",
            "image_bytes": _png(),
            "regions": [
                {"bbox": box, "kern": KERN},
                {"bbox": box, "kern": ""},  # sin verdad: no entra
                {"bbox": {**box, "y": 60.0}, "kern": KERN},
            ],
        },
        {
            "id": "mono/incipit",
            "original_score": "mono/incipit.krn",
            "page_texture": "monophony",
            "image_bytes": _png(),
            "regions": [{"bbox": box, "kern": KERN}],
        },
    ]


def test_prepare_crops_regions_with_kern_and_writes_the_manifest(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    data = tmp_path / "data"

    manifest = exp_17.prepare_pages(_pages(), data, source={"file": "x.parquet"})

    assert manifest["count"] == 3
    assert manifest["pages"] == 2
    assert manifest["skipped_regions"] == {"without_kern": 1}
    first = manifest["entries"][0]
    assert first["id"] == "beethoven_sonata_1_r00"
    assert first["texture"] == "pianoform"
    assert first["work"] == "beethoven/sonata01-1.krn"
    assert first["box_pixels"] == [20, 20, 120, 60]  # porcentajes de 200 x 100
    crop = cv2.imread(str(data / first["image"]), cv2.IMREAD_GRAYSCALE)
    assert crop.shape == (40, 100)
    assert (data / first["ground_truth"]).read_text("utf-8") == KERN
    assert [e["region"] for e in manifest["entries"]] == [0, 2, 0]
    with pytest.raises(FileExistsError, match="--force"):
        exp_17.prepare_pages(_pages(), data, source={})


def test_prepare_needs_the_parquet_and_pyarrow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(FileNotFoundError, match="restringido"):
        exp_17.prepare(tmp_path)
    monkeypatch.setitem(sys.modules, "pyarrow", None)
    with pytest.raises(RuntimeError, match="pyarrow"):
        list(exp_17.read_parquet_pages(tmp_path / "x.parquet"))


class _Engine:
    engine_id = "homr"
    device = "cpu"

    def transcribe_musicxml(self, image_path: Path) -> str:
        if image_path.stem.startswith("mono"):
            raise OMRTranscriptionError("No staffs found")
        if image_path.stem.endswith("r02"):
            return melody_musicxml([("G", 4, 1), ("A", 4, 1), ("B", 4, 1), ("C", 5, 1)])
        return melody_musicxml([("G", 4, 1), ("A", 4, 1), ("D", 5, 1), ("C", 5, 1)])


def test_build_measures_regions_by_texture_and_writes_the_smb_corpus(tmp_path: Path) -> None:
    data = tmp_path / "data"
    exp_17.prepare_pages(_pages(), data, source={"file": "x.parquet"})
    manifest_path = data / "smb" / "exp_17" / "manifest.json"
    assert external_corpus.transcribe(manifest_path, label="exp_17", engine=_Engine()) == {
        "written": 2,
        "reused": 0,
        "failures": 1,
    }

    summary = exp_17.build(manifest_path, with_omr_ned=True)

    assert summary["transcription"]["failures"]["cases"] == 1
    assert summary["by_texture"]["monophony"]["failures"]["rate"] == 1.0
    piano = summary["by_texture"]["pianoform"]
    assert piano["derived"] == 2
    assert piano["verification"]["cases"] == 2
    assert piano["omr_ned"]["count"] == 2 and piano["ser"]["count"] == 2
    assert summary["edit_distribution"]["all_derived"]["counts"]["SetPitch"] == 1

    results = common.RESULTS_DIR
    with (results / "smb_homr_regions.csv").open(encoding="utf-8") as handle:
        rows = {row["id"]: row for row in csv.DictReader(handle)}
    assert rows["beethoven_sonata_1_r00"]["SetPitch"] == "1"
    assert rows["beethoven_sonata_1_r02"]["Total"] == "0"
    assert rows["mono_incipit_r00"]["status"] == "failure"
    lines = (results / "smb_correction_corpus.jsonl").read_text("utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert {r["source"] for r in records} == {"smb"}
    # `ml export-tables --corpus` lo lee con su origen y su obra.
    tables = corpus_tables(records)
    assert {row["source"] for row in tables["notas"]} == {"smb"}
    assert {row["work_id"] for row in tables["partituras"]} == {"smb:beethoven/sonata01-1.krn"}
    assert {r["work_id"] for r in records} == {"smb:beethoven/sonata01-1.krn"}
    assert len({r["split"] for r in records}) == 1  # una obra, un lado de la partición
    assert json.loads((results / "exp_17_run_info.json").read_text("utf-8"))["omr_ned"] is True
