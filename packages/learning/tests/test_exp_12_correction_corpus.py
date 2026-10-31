"""Pruebas de `exp_12`: corpus de correcciones a escala y errores de HOMR (#255)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from cadenza.omr import OMRTranscriptionError

from ml.experiments import common
from ml.experiments import exp_12_correction_corpus as exp_12

# (letra, alteración, octava, duración en negras) o ("R", 0, 0, duración) para un silencio.
Note = tuple[str, int, int, int]
_TYPES = {1: "quarter", 2: "half", 4: "whole"}


def _musicxml(fifths: int, *measures: list[Note]) -> str:
    """MusicXML de una voz en 4/4. Sin `<alter>`, la nota se lee natural, como en el MEI."""
    body = []
    for number, notes in enumerate(measures, start=1):
        attributes = ""
        if number == 1:
            attributes = (
                "<attributes><divisions>1</divisions>"
                f"<key><fifths>{fifths}</fifths></key>"
                "<time><beats>4</beats><beat-type>4</beat-type></time>"
                "<clef><sign>G</sign><line>2</line></clef></attributes>"
            )
        xml_notes = []
        for step, alter, octave, beats in notes:
            if step == "R":
                pitch = "<rest/>"
            else:
                alter_xml = f"<alter>{alter}</alter>" if alter else ""
                pitch = f"<pitch><step>{step}</step>{alter_xml}<octave>{octave}</octave></pitch>"
            xml_notes.append(
                f"<note>{pitch}<duration>{beats}</duration><voice>1</voice>"
                f"<type>{_TYPES[beats]}</type></note>"
            )
        body.append(f'<measure number="{number}">{attributes}{"".join(xml_notes)}</measure>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?><score-partwise version="4.0">'
        '<part-list><score-part id="P1"><part-name>M</part-name></score-part></part-list>'
        f'<part id="P1">{"".join(body)}</part></score-partwise>'
    )


def _primus(tmp_path: Path, ids: list[str], *, incomplete: tuple[str, ...] = ()) -> Path:
    data = tmp_path / "data"
    for i, incipit in enumerate(ids):
        folder = data / "primus" / ("package_aa" if i % 2 else "package_ab") / incipit
        folder.mkdir(parents=True)
        (folder / f"{incipit}.png").write_bytes(f"png {incipit}".encode())
        (folder / f"{incipit}.mei").write_text(f"mei {incipit}", encoding="utf-8")
        if incipit not in incomplete:
            (folder / f"{incipit}.semantic").write_text("note-C4_quarter", encoding="utf-8")
    return data


def _exp03_manifest(data: Path, ids: list[str]) -> Path:
    manifest = data / "manifest.json"
    manifest.write_text(
        json.dumps({"corpus": "primus", "entries": [{"id": i} for i in ids]}), encoding="utf-8"
    )
    return manifest


# --- Muestra -----------------------------------------------------------------------------


def test_sample_is_seeded_complete_and_disjoint_from_exp_03(tmp_path: Path) -> None:
    ids = [f"0000{n:05d}-1_1_1" for n in range(40)]
    data = _primus(tmp_path, ids, incomplete=(ids[7],))
    _exp03_manifest(data, ids[:5])

    manifest = exp_12.select_sample(data, size=12, seed=7)
    chosen = [entry["id"] for entry in manifest["entries"]]
    assert len(chosen) == 12
    assert chosen == sorted(chosen)
    assert not set(chosen) & set(ids[:5])  # sin solaparse con exp_03
    assert ids[7] not in chosen  # sin `.semantic` no hay altura que suena
    assert manifest["selection"]["candidates"] == 34
    assert manifest["selection"]["excluded_exp_03"] == 5
    entry = manifest["entries"][0]
    assert entry["image"].endswith(".png") and len(entry["image_sha256"]) == 64
    assert entry["ground_truth"].endswith(".mei") and entry["semantic"].endswith(".semantic")

    written = json.loads((data / "primus" / "exp_12" / "manifest.json").read_text("utf-8"))
    assert [e["id"] for e in written["entries"]] == chosen
    # La misma semilla da la misma muestra; otra semilla, otra.
    assert exp_12.select_sample(data, size=12, seed=7)["entries"] == manifest["entries"]
    other = exp_12.select_sample(data, size=12, seed=8)
    assert [e["id"] for e in other["entries"]] != chosen


def test_sample_fails_without_the_exp_03_manifest(tmp_path: Path) -> None:
    data = _primus(tmp_path, ["a", "b"])
    with pytest.raises(FileNotFoundError, match="exp_03"):
        exp_12.select_sample(data, size=1, seed=1)


def test_sample_fails_when_there_are_not_enough_incipits(tmp_path: Path) -> None:
    data = _primus(tmp_path, ["a", "b", "c"])
    _exp03_manifest(data, ["a"])
    with pytest.raises(ValueError, match="2 incipits"):
        exp_12.select_sample(data, size=3, seed=1)


# --- Transcripción -----------------------------------------------------------------------


class _Engine:
    """Doble del motor: falla en `fail_on` y cuenta lo que transcribe."""

    engine_id = "homr"
    device = "cpu"

    def __init__(self, *, fail_on: str = "", crash_on: str = "") -> None:
        self.fail_on = fail_on
        self.crash_on = crash_on
        self.calls: list[str] = []

    def transcribe_musicxml(self, image_path: Path) -> str:
        incipit = image_path.stem
        self.calls.append(incipit)
        if incipit == self.crash_on:
            raise RuntimeError("se acabó la memoria")
        if incipit == self.fail_on:
            raise OMRTranscriptionError("Exception: No staffs found")
        return _musicxml(0, [("C", 0, 4, 4)])


def _sampled(tmp_path: Path, n: int = 4) -> tuple[Path, list[str]]:
    ids = [f"0000{k:05d}-1_1_1" for k in range(n + 1)]
    data = _primus(tmp_path, ids)
    _exp03_manifest(data, ids[:1])
    exp_12.select_sample(data, size=n, seed=3)
    manifest = data / "primus" / "exp_12" / "manifest.json"
    chosen = [e["id"] for e in json.loads(manifest.read_text("utf-8"))["entries"]]
    return manifest, chosen


def test_transcription_records_failures_and_resumes(tmp_path: Path) -> None:
    manifest, chosen = _sampled(tmp_path)
    engine = _Engine(fail_on=chosen[1])
    result = exp_12.transcribe(manifest, engine=engine)
    assert result == {"written": 3, "reused": 0, "failures": 1}

    predictions = manifest.parent / "predictions"
    failures = json.loads((predictions / "failures.json").read_text("utf-8"))
    assert failures == [
        {"id": chosen[1], "error": "OMRTranscriptionError: Exception: No staffs found"}
    ]
    info = json.loads((predictions / "run_info.json").read_text("utf-8"))
    assert info["engine"] == "homr" and info["device"] == "cpu" and info["preprocessing"] is None

    # Reanudar no repite nada; con `retry_failures` solo se repiten los fallos.
    again = _Engine()
    assert exp_12.transcribe(manifest, engine=again)["reused"] == 4
    assert again.calls == []
    retry = _Engine()
    exp_12.transcribe(manifest, engine=retry, retry_failures=True)
    assert retry.calls == [chosen[1]]
    assert json.loads((predictions / "failures.json").read_text("utf-8")) == []


def test_transcription_stops_on_an_environment_error(tmp_path: Path) -> None:
    """Solo un error del motor es un fallo del incipit; los demás detienen la ejecución."""
    manifest, chosen = _sampled(tmp_path)
    with pytest.raises(RuntimeError, match="memoria"):
        exp_12.transcribe(manifest, engine=_Engine(crash_on=chosen[2]))
    predictions = manifest.parent / "predictions"
    assert json.loads((predictions / "failures.json").read_text("utf-8")) == []
    assert not (predictions / f"{chosen[2]}.musicxml").exists()


def test_transcription_refuses_predictions_of_another_device(tmp_path: Path) -> None:
    manifest, _ = _sampled(tmp_path)
    exp_12.transcribe(manifest, engine=_Engine())
    gpu = _Engine()
    gpu.device = "cuda"
    with pytest.raises(ValueError, match="otro motor o dispositivo"):
        exp_12.transcribe(manifest, engine=gpu)


# --- Corpus y análisis -------------------------------------------------------------------

# G mayor: la verdad suena F#4. El MEI la escribe sin alteración, como `_musicxml`.
_GT_MEI_LIKE = _musicxml(1, [("G", 0, 4, 1), ("A", 0, 4, 1), ("F", 0, 4, 1), ("G", 0, 4, 1)])
_SEMANTIC = "clef-G2 keySignature-GM timeSignature-4/4 note-G4_quarter note-A4_quarter "
_SEMANTIC += "note-F#4_quarter note-G4_quarter barline"


def _corpus(
    tmp_path: Path, predictions: dict[str, str | None], *, semantic: str = _SEMANTIC
) -> Path:
    """Manifiesto de exp_12 con una predicción por incipit (None: fallo de HOMR)."""
    root = tmp_path / "data"
    folder = root / "primus" / "exp_12"
    (folder / "predictions").mkdir(parents=True)
    entries = []
    failures = []
    for incipit, prediction in predictions.items():
        gt_dir = root / "primus" / "package_aa" / incipit
        gt_dir.mkdir(parents=True)
        (gt_dir / f"{incipit}.musicxml").write_text(_GT_MEI_LIKE, encoding="utf-8")
        text = semantic if incipit != "mismatch" else "note-G4_quarter"
        (gt_dir / f"{incipit}.semantic").write_text(text, encoding="utf-8")
        entries.append(
            {
                "id": incipit,
                "image": f"primus/package_aa/{incipit}/{incipit}.png",
                "ground_truth": f"primus/package_aa/{incipit}/{incipit}.musicxml",
                "semantic": f"primus/package_aa/{incipit}/{incipit}.semantic",
            }
        )
        if prediction is None:
            failures.append({"id": incipit, "error": "OMRTranscriptionError: No staffs found"})
        else:
            (folder / "predictions" / f"{incipit}.musicxml").write_text(prediction, "utf-8")
    (folder / "predictions" / "failures.json").write_text(json.dumps(failures), "utf-8")
    (folder / "predictions" / "run_info.json").write_text(
        json.dumps({"engine": "homr", "engine_version": "0.7.0", "device": "cpu"}), "utf-8"
    )
    manifest = folder / "manifest.json"
    manifest.write_text(
        json.dumps({"corpus": "primus", "seed": 5, "entries": entries}), encoding="utf-8"
    )
    return manifest


def _read_corpus(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


def test_build_verifies_the_corrections_and_writes_the_corpus(tmp_path: Path) -> None:
    good_but_one_pitch = _musicxml(
        1, [("G", 0, 4, 1), ("A", 0, 4, 1), ("F", 1, 4, 1), ("B", 0, 4, 1)]
    )
    key_missed = _musicxml(0, [("G", 0, 4, 1), ("A", 0, 4, 1), ("F", 0, 4, 1), ("G", 0, 4, 1)])
    manifest = _corpus(
        tmp_path,
        {
            "pitch": good_but_one_pitch,
            "key": key_missed,
            "failed": None,
            "mismatch": good_but_one_pitch,
        },
    )
    summary = exp_12.build(manifest, seed=5)
    results = common.RESULTS_DIR

    assert summary["transcription"]["failures_count"] == 1
    assert summary["transcription"]["failures_by_error"] == {
        "OMRTranscriptionError: No staffs found": 1
    }
    assert summary["ground_truth"]["semantic_mismatch_ids"] == ["mismatch"]
    verification = summary["verification"]
    assert verification["verified_count"] == 2 and verification["derived_count"] == 2
    assert verification["rate"] == 1.0

    # Con la altura que suena, HOMR solo falló una altura y una armadura (con su alteración).
    ops = summary["edit_distribution"]["verified"]["counts"]
    assert ops["SetPitch"] == 1 and ops["SetKey"] == 1 and ops["SetAccidental"] == 1
    # Con la verdad del MEI tal cual, el F# bien leído contaba como error de alteración.
    artifact = summary["ground_truth"]["mei_without_key_accidentals"]
    assert artifact["notes_whose_mei_pitch_is_not_the_sounding_one"] == 2
    assert artifact["edit_distribution_against_mei"]["SetAccidental"] == 1
    assert artifact["edit_distribution_against_sounding"]["SetAccidental"] == 1

    key = summary["context_analysis"]["key_signature"]
    assert key["incipits_with_key_misread"] == 1
    assert key["set_accidental_in_key_misread_incipits"] == 1
    assert key["set_accidental_explained_by_key_misread"] == 1

    records = _read_corpus(results / "correction_corpus.jsonl")
    assert {r["incipit_id"] for r in records} == {"pitch", "key"}
    b4 = next(r for r in records if r["incipit_id"] == "pitch" and r["correction"])
    assert b4["read"]["pitch"] == "B4" and b4["correction"]["pitch"] == "G4"
    assert all(r["verified"] for r in records)

    split = json.loads((results / "correction_corpus_split.json").read_text("utf-8"))
    assert split["seed"] == 5
    assert sorted(split["train"] + split["test"]) == ["failed", "key", "mismatch", "pitch"]

    run_info = json.loads((results / "exp_12_run_info.json").read_text("utf-8"))
    assert run_info["experiment"] == "exp_12" and run_info["seed"] == 5
    assert run_info["corpus_sha256"] == common.sha256_of_file(results / "correction_corpus.jsonl")
    assert run_info["homr"] == {"engine": "homr", "engine_version": "0.7.0", "device": "cpu"}
    assert (results / "correction_corpus_incipits.csv").is_file()
    assert (results / "correction_corpus_summary.json").is_file()


def test_build_registers_a_ground_truth_the_domain_cannot_read(tmp_path: Path) -> None:
    """Un MEI de PrIMuS con un compás 2/3 no detiene el experimento: se registra y no se usa."""
    good = _musicxml(1, [("G", 0, 4, 1), ("A", 0, 4, 1), ("F", 1, 4, 1), ("G", 0, 4, 1)])
    manifest = _corpus(tmp_path, {"ok": good, "odd_meter": good})
    gt_file = tmp_path / "data" / "primus" / "package_aa" / "odd_meter" / "odd_meter.musicxml"
    gt_file.write_text(
        _GT_MEI_LIKE.replace("<beat-type>4</beat-type>", "<beat-type>3</beat-type>"),
        encoding="utf-8",
    )

    summary = exp_12.build(manifest, seed=5)

    ground_truth = summary["ground_truth"]
    assert ground_truth["unreadable_count"] == 1
    assert list(ground_truth["unreadable"]) == ["odd_meter"]
    assert "power of two" in ground_truth["unreadable"]["odd_meter"]
    assert summary["verification"]["derived_count"] == 1
    records = _read_corpus(common.RESULTS_DIR / "correction_corpus.jsonl")
    assert {r["incipit_id"] for r in records} == {"ok"}


def test_build_fails_without_manifest_or_predictions(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="select_sample"):
        exp_12.build(tmp_path / "manifest.json", seed=1)
    manifest = _corpus(tmp_path, {"failed": None})
    with pytest.raises(ValueError, match="ninguna predicción"):
        exp_12.build(manifest, seed=1)
    assert not (common.RESULTS_DIR / "correction_corpus.jsonl").exists()


def test_build_fails_when_an_entry_was_never_transcribed(tmp_path: Path) -> None:
    good = _musicxml(1, [("G", 0, 4, 1), ("A", 0, 4, 1), ("F", 1, 4, 1), ("G", 0, 4, 1)])
    manifest = _corpus(tmp_path, {"ok": good, "pending": good})
    (manifest.parent / "predictions" / "pending.musicxml").unlink()
    with pytest.raises(ValueError, match="sin predicción ni fallo"):
        exp_12.build(manifest, seed=1)
    # Con `limit`, solo cuentan las primeras entradas, las que ya se transcribieron.
    summary = exp_12.build(manifest, seed=1, limit=1)
    assert summary["sample"]["size"] == 1
    assert summary["verification"]["verified_count"] == 1
