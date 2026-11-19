"""Pruebas de `exp_18`: corpus de correcciones con una muestra de Camera-PrIMuS (#421)."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from cadenza.learning import assign_split, primus_work_id

from ml.experiments import common
from ml.experiments import exp_18_camera_primus as exp_18

from .test_exp_12_correction_corpus import _GT_MEI_LIKE, _SEMANTIC, _Engine, _musicxml

_GOOD = _musicxml(1, [("G", 0, 4, 1), ("A", 0, 4, 1), ("F", 1, 4, 1), ("G", 0, 4, 1)])
_ONE_PITCH = _musicxml(1, [("G", 0, 4, 1), ("A", 0, 4, 1), ("F", 1, 4, 1), ("B", 0, 4, 1)])
_KEY_MISSED = _musicxml(0, [("G", 0, 4, 1), ("A", 0, 4, 1), ("F", 0, 4, 1), ("G", 0, 4, 1)])


def _camera(tmp_path: Path, ids: list[str], *, incomplete: tuple[str, ...] = ()) -> Path:
    """`<data>/camera_primus/Corpus/<id>/` como en la descarga: la imagen limpia, la
    distorsionada, el MEI y el `.semantic` (salvo en `incomplete`)."""
    data = tmp_path / "data"
    for incipit in ids:
        folder = data / "camera_primus" / "Corpus" / incipit
        folder.mkdir(parents=True)
        (folder / f"{incipit}.png").write_bytes(f"png {incipit}".encode())
        (folder / f"{incipit}_distorted.jpg").write_bytes(f"jpg {incipit}".encode())
        (folder / f"{incipit}.mei").write_text(f"mei {incipit}", encoding="utf-8")
        if incipit not in incomplete:
            (folder / f"{incipit}.semantic").write_text("note-C4_quarter", encoding="utf-8")
    return data


def _exp03(data: Path, ids: list[str]) -> None:
    (data / "manifest.json").write_text(
        json.dumps({"corpus": "primus", "entries": [{"id": i} for i in ids]}), encoding="utf-8"
    )


def _ids(n: int) -> list[str]:
    return [f"{k:09d}-1_1_1" for k in range(1, n + 1)]


# --- Muestra -----------------------------------------------------------------------------


def test_the_sample_is_seeded_complete_photo_like_and_disjoint_from_exp_03(
    tmp_path: Path,
) -> None:
    ids = _ids(40)
    data = _camera(tmp_path, ids, incomplete=(ids[7],))
    _exp03(data, ids[:5])

    manifest = exp_18.select_sample(data, size=12, seed=7)

    chosen = [entry["id"] for entry in manifest["entries"]]
    assert len(chosen) == 12 and len(set(chosen)) == 12
    assert not set(chosen) & set(ids[:5])  # sin solaparse con exp_03
    assert ids[7] not in chosen  # sin `.semantic` no hay altura que suena
    assert manifest["selection"]["candidates"] == 34
    assert manifest["selection"]["excluded_exp_03"] == 5
    assert manifest["source"] == "camera-primus" and manifest["seed"] == 7
    entry = manifest["entries"][0]
    # Lo que lee HOMR es la imagen distorsionada, no la limpia de PrIMuS.
    assert entry["image"] == f"camera_primus/Corpus/{entry['id']}/{entry['id']}_distorted.jpg"
    assert entry["ground_truth"].endswith(".mei") and entry["semantic"].endswith(".semantic")
    image = data / entry["image"]
    assert entry["image_sha256"] == common.sha256_of_file(image)
    written = data / "camera_primus" / "exp_18" / "manifest.json"
    assert json.loads(written.read_text("utf-8"))["entries"] == manifest["entries"]


def test_a_larger_sample_with_the_same_seed_starts_with_the_smaller_one(tmp_path: Path) -> None:
    """La muestra es el principio de una ordenación al azar: ampliarla no repite lo leído."""
    data = _camera(tmp_path, _ids(30))
    _exp03(data, [])
    small = [e["id"] for e in exp_18.select_sample(data, size=6, seed=3)["entries"]]
    predictions = data / "camera_primus" / "exp_18" / "predictions"
    predictions.mkdir()
    (predictions / f"{small[0]}.musicxml").write_text(_GOOD, encoding="utf-8")

    with pytest.raises(FileExistsError, match="--force"):
        exp_18.select_sample(data, size=10, seed=3)
    large = [e["id"] for e in exp_18.select_sample(data, size=10, seed=3, force=True)["entries"]]

    assert large[:6] == small
    assert (predictions / f"{small[0]}.musicxml").is_file()  # siguen siendo de esta muestra
    fewer = [e["id"] for e in exp_18.select_sample(data, size=3, seed=3, force=True)["entries"]]
    assert fewer == small[:3] and (predictions / f"{small[0]}.musicxml").is_file()
    other = [e["id"] for e in exp_18.select_sample(data, size=10, seed=4, force=True)["entries"]]
    assert other != large
    assert not predictions.exists()  # las de otra muestra no se mezclan


def test_the_sample_fails_without_exp_03_or_enough_incipits(tmp_path: Path) -> None:
    data = _camera(tmp_path, _ids(3))
    with pytest.raises(FileNotFoundError, match="exp_03"):
        exp_18.select_sample(data, size=1, seed=1)
    _exp03(data, _ids(1))
    with pytest.raises(ValueError, match="2 incipits"):
        exp_18.select_sample(data, size=3, seed=1)


# --- Transcripción -----------------------------------------------------------------------


def test_the_transcription_reads_the_distorted_images_and_resumes(tmp_path: Path) -> None:
    data = _camera(tmp_path, _ids(5))
    _exp03(data, [])
    manifest = exp_18.select_sample(data, size=4, seed=2)
    chosen = [e["id"] for e in manifest["entries"]]
    path = data / "camera_primus" / "exp_18" / "manifest.json"

    engine = _Engine(fail_on=f"{chosen[1]}_distorted")
    assert exp_18.transcribe(path, engine=engine) == {"written": 3, "reused": 0, "failures": 1}
    assert engine.calls == [f"{incipit}_distorted" for incipit in chosen]
    predictions = path.parent / "predictions"
    assert sorted(p.stem for p in predictions.glob("*.musicxml")) == sorted(chosen[:1] + chosen[2:])
    again = _Engine()
    assert exp_18.transcribe(path, engine=again)["reused"] == 4 and again.calls == []


# --- Corpus ------------------------------------------------------------------------------


def _sample(tmp_path: Path, predictions: Mapping[str, str | None], *, seed: int = 5) -> Path:
    """Manifiesto de exp_18 con una predicción por incipit (None: fallo de HOMR)."""
    root = tmp_path / "data"
    folder = root / "camera_primus" / "exp_18"
    (folder / "predictions").mkdir(parents=True)
    entries = []
    failures = []
    for incipit, prediction in predictions.items():
        gt_dir = root / "camera_primus" / "Corpus" / incipit
        gt_dir.mkdir(parents=True)
        (gt_dir / f"{incipit}.musicxml").write_text(_GT_MEI_LIKE, encoding="utf-8")
        (gt_dir / f"{incipit}.semantic").write_text(_SEMANTIC, encoding="utf-8")
        entries.append(
            {
                "id": incipit,
                "image": f"camera_primus/Corpus/{incipit}/{incipit}_distorted.jpg",
                "ground_truth": f"camera_primus/Corpus/{incipit}/{incipit}.musicxml",
                "semantic": f"camera_primus/Corpus/{incipit}/{incipit}.semantic",
            }
        )
        if prediction is None:
            failures.append({"id": incipit, "error": "OMRTranscriptionError: No staffs found"})
        else:
            (folder / "predictions" / f"{incipit}.musicxml").write_text(prediction, "utf-8")
    (folder / "predictions" / "failures.json").write_text(json.dumps(failures), "utf-8")
    (folder / "predictions" / "run_info.json").write_text(
        json.dumps(
            {"engine": "homr", "engine_version": "0.7.0", "device": "cuda", "preprocessing": None}
        ),
        "utf-8",
    )
    manifest = folder / "manifest.json"
    manifest.write_text(
        json.dumps(
            {"corpus": "camera_primus", "source": "camera-primus", "seed": seed, "entries": entries}
        ),
        encoding="utf-8",
    )
    return manifest


def _exp12_split(results: Path, ids: list[str], *, seed: int = 5, fraction: float = 0.2) -> Path:
    """`correction_corpus_split.json` de exp_12 con la regla de #255."""
    split: dict[str, Any] = {"seed": seed, "test_fraction": fraction, "train": [], "test": []}
    for incipit in ids:
        side = assign_split(primus_work_id(incipit), seed=seed, test_fraction=fraction)
        split[side].append(incipit)
    results.mkdir(parents=True, exist_ok=True)
    path = results / "correction_corpus_split.json"
    path.write_text(json.dumps(split), encoding="utf-8")
    return path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


def test_build_writes_a_camera_primus_corpus_apart_from_exp_12(tmp_path: Path) -> None:
    ids = ["000000001-1_1_1", "000000002-1_1_1", "000000003-1_1_1"]
    manifest = _sample(tmp_path, {ids[0]: _ONE_PITCH, ids[1]: _KEY_MISSED, ids[2]: None})
    results = common.RESULTS_DIR
    _exp12_split(results, [ids[0], "000000009-1_1_1"])

    summary = exp_18.build(manifest)

    assert summary["source"] == "camera-primus" and summary["simulated"] is False
    assert summary["transcription"]["failures_count"] == 1
    assert summary["transcription"]["device"] == "cuda"
    assert summary["verification"]["verified_count"] == 2
    ops = summary["edit_distribution"]["verified"]["counts"]
    assert ops["SetPitch"] == 1 and ops["SetKey"] == 1 and ops["SetAccidental"] == 1
    assert summary["ser"]["count"] == 2

    records = _read_jsonl(results / "camera_primus_correction_corpus.jsonl")
    # Los mismos incipits que PrIMuS, con otra imagen: el identificador lleva la fuente para no
    # confundirse con los de exp_12 en las tablas; la obra es la de PrIMuS.
    assert {r["incipit_id"] for r in records} == {f"camera-primus:{i}" for i in ids[:2]}
    assert {r["source"] for r in records} == {"camera-primus"}
    assert {r["work_id"] for r in records} == {primus_work_id(i) for i in ids[:2]}
    assert all(r["verified"] for r in records)

    with (results / "camera_primus_correction_corpus_incipits.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [r["primus_id"] for r in rows] == ids
    assert [r["status"] for r in rows] == ["derived", "derived", "failure"]
    split = json.loads((results / "camera_primus_correction_corpus_split.json").read_text("utf-8"))
    assert sorted(split["train"] + split["test"]) == sorted(f"camera-primus:{i}" for i in ids)

    run_info = json.loads((results / "exp_18_run_info.json").read_text("utf-8"))
    assert run_info["experiment"] == "exp_18" and run_info["simulated"] is False
    assert run_info["homr"]["device"] == "cuda"
    assert run_info["corpus_sha256"] == common.sha256_of_file(
        results / "camera_primus_correction_corpus.jsonl"
    )
    assert summary["run_info"] == run_info
    # exp_12 no se toca: ni su corpus ni su resumen.
    assert not (results / "correction_corpus.jsonl").exists()
    assert not (results / "correction_corpus_summary.json").exists()


def test_build_keeps_the_works_of_exp_12_on_the_same_side(tmp_path: Path) -> None:
    """La partición es la de #255: por obra, con la semilla y la fracción de exp_12."""
    ours = [f"{work:09d}-1_1_2" for work in range(1, 31)]
    theirs = [f"{work:09d}-1_1_1" for work in range(1, 31)]
    manifest = _sample(tmp_path, dict.fromkeys(ours, _GOOD))
    _exp12_split(common.RESULTS_DIR, theirs)

    summary = exp_18.build(manifest, with_omr_ned=False)

    compatibility = summary["exp_12_compatibility"]
    assert compatibility["shared_works"] == 30 and compatibility["disagreements"] == 0
    split = json.loads(
        (common.RESULTS_DIR / "camera_primus_correction_corpus_split.json").read_text("utf-8")
    )
    side = {incipit: name for name in ("train", "test") for incipit in split[name]}
    assert set(side.values()) == {"train", "test"}
    for work in range(1, 31):
        expected = assign_split(primus_work_id(theirs[work - 1]), seed=5, test_fraction=0.2)
        assert side[f"camera-primus:{ours[work - 1]}"] == expected


def test_build_refuses_a_partition_that_does_not_match_exp_12(tmp_path: Path) -> None:
    manifest = _sample(tmp_path, {"000000001-1_1_1": _GOOD})
    with pytest.raises(FileNotFoundError, match="exp_12"):
        exp_18.build(manifest)
    _exp12_split(common.RESULTS_DIR, ["000000001-1_1_1"], seed=6)
    with pytest.raises(ValueError, match="semilla"):
        exp_18.build(manifest)
    _exp12_split(common.RESULTS_DIR, ["000000001-1_1_1"], fraction=0.3)
    with pytest.raises(ValueError, match="fracción"):
        exp_18.build(manifest)
    assert not (common.RESULTS_DIR / "camera_primus_correction_corpus.jsonl").exists()


def test_build_registers_what_the_domain_cannot_read_or_the_semantic_contradicts(
    tmp_path: Path,
) -> None:
    odd = _GOOD.replace("<beat-type>4</beat-type>", "<beat-type>3</beat-type>")
    ids = {"000000001-1_1_1": _GOOD, "000000002-1_1_1": odd, "000000003-1_1_1": _GOOD}
    manifest = _sample(tmp_path, ids)
    semantic = tmp_path / "data" / "camera_primus" / "Corpus" / "000000003-1_1_1"
    (semantic / "000000003-1_1_1.semantic").write_text("note-G4_quarter", encoding="utf-8")
    _exp12_split(common.RESULTS_DIR, [])

    summary = exp_18.build(manifest, with_omr_ned=False)

    assert list(summary["transcription"]["prediction_unreadable"]) == ["000000002-1_1_1"]
    assert summary["ground_truth"]["semantic_mismatch_ids"] == ["000000003-1_1_1"]
    assert summary["verification"]["derived_count"] == 1


def test_build_fails_when_an_entry_was_never_transcribed(tmp_path: Path) -> None:
    manifest = _sample(tmp_path, {"000000001-1_1_1": _GOOD, "000000002-1_1_1": _GOOD})
    (manifest.parent / "predictions" / "000000002-1_1_1.musicxml").unlink()
    _exp12_split(common.RESULTS_DIR, [])
    with pytest.raises(ValueError, match="sin predicción ni fallo"):
        exp_18.build(manifest)
    assert exp_18.build(manifest, limit=1, with_omr_ned=False)["sample"]["size"] == 1
