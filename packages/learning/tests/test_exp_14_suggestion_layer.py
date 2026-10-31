"""Pruebas de `exp_14`: primera medición de la capa de sugerencias (#257).

El «mundo» de prueba imita la salida de `exp_12` con el corpus sintético de
`suggestions_support`: una predicción MusicXML por incipit, su verdad (MusicXML y
`.semantic`), el corpus de correcciones y la partición fija por obra. Nada se escribe en
`results/` ni en `data/`: todo va a directorios temporales.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from cadenza.domain import EventKind, ScoreIR, materialize
from cadenza.interchange import Music21ScoreExporter, read_score
from cadenza.learning import (
    assign_split,
    build_correction_records,
    derive_edit_events,
    is_structurally_equal,
    primus_work_id,
    semantic_note_pitches,
    with_sounding_pitches,
)
from cadenza.validation.learned import FEATURE_VERSION

from ml.experiments import common
from ml.experiments import exp_14_suggestion_layer as exp_14

from .suggestions_support import SPLIT_SEED, incipit_id, incipit_pair, small_config

WORKS = 30


def _semantic(score: ScoreIR) -> str:
    notes = [
        f"note-{event.pitch}_quarter"
        for part in score.parts
        for staff in part.staves
        for measure in staff.measures
        for event in measure.events
        if event.kind is EventKind.NOTE
    ]
    return "clef-G2 keySignature-FM timeSignature-4/4 " + " ".join(notes)


def _build_world(root: Path) -> dict[str, Path]:
    """Muestra, predicciones, verdad, corpus y partición como los deja `exp_12`."""
    data = root / "data"
    folder = data / "primus" / "exp_12"
    predictions = folder / "predictions"
    predictions.mkdir(parents=True)
    exporter = Music21ScoreExporter()
    entries = []
    corpus: list[dict[str, Any]] = []
    split: dict[str, list[str]] = {"train": [], "test": []}
    for work in range(WORKS):
        for index in (0, 1):
            identifier = incipit_id(work, index)
            read, truth = incipit_pair(work, index)
            gt_dir = data / "primus" / "package_aa" / identifier
            gt_dir.mkdir(parents=True)
            gt_file = gt_dir / f"{identifier}.musicxml"
            gt_file.write_text(exporter.to_musicxml(truth), encoding="utf-8")
            semantic_file = gt_dir / f"{identifier}.semantic"
            semantic_file.write_text(_semantic(truth), encoding="utf-8")
            pred_file = predictions / f"{identifier}.musicxml"
            pred_file.write_text(exporter.to_musicxml(read), encoding="utf-8")
            entries.append(
                {
                    "id": identifier,
                    "image": f"primus/package_aa/{identifier}/{identifier}.png",
                    "ground_truth": f"primus/package_aa/{identifier}/{identifier}.musicxml",
                    "semantic": f"primus/package_aa/{identifier}/{identifier}.semantic",
                }
            )
            # Lo mismo que hace `exp_12 build`, sin escribir en `results/`.
            predicted = read_score(pred_file)
            sounding = with_sounding_pitches(
                read_score(gt_file), semantic_note_pitches(semantic_file.read_text("utf-8"))
            )
            edits = derive_edit_events(predicted, sounding, document_id=identifier)
            verified = is_structurally_equal(materialize(predicted, edits), sounding)
            side = assign_split(primus_work_id(identifier), seed=SPLIT_SEED)
            split[side].append(identifier)
            corpus.extend(
                build_correction_records(
                    predicted, sounding, incipit_id=identifier, split=side, verified=verified
                )
            )
    (predictions / "failures.json").write_text("[]", encoding="utf-8")
    (predictions / "run_info.json").write_text(
        json.dumps({"engine": "homr", "engine_version": "0.7.0", "device": "cpu"}), "utf-8"
    )
    manifest = folder / "manifest.json"
    manifest.write_text(
        json.dumps({"corpus": "primus", "seed": SPLIT_SEED, "entries": entries}), "utf-8"
    )
    results = root / "corpus"
    results.mkdir()
    corpus_path = results / "correction_corpus.jsonl"
    corpus_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in corpus),
        encoding="utf-8",
    )
    split_path = results / "correction_corpus_split.json"
    split_path.write_text(
        json.dumps({"seed": SPLIT_SEED, "train": sorted(split["train"]), "test": split["test"]}),
        encoding="utf-8",
    )
    config = small_config(root / "suggestions.json")
    return {"data": data, "corpus": corpus_path, "split": split_path, "config": config}


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    return _build_world(tmp_path_factory.mktemp("world"))


def _copy(world: dict[str, Path], target: Path) -> dict[str, Path]:
    root = world["data"].parent
    shutil.copytree(root, target, dirs_exist_ok=True)
    return {name: target / path.relative_to(root) for name, path in world.items()}


def _run(paths: dict[str, Path], output: Path, **kwargs: Any) -> dict[str, Any]:
    return exp_14.run(
        corpus_path=paths["corpus"],
        split_path=paths["split"],
        data_dir=paths["data"],
        config_path=paths["config"],
        output_dir=output,
        seed=kwargs.pop("seed", 7),
        **kwargs,
    )


@pytest.fixture(scope="module")
def measured(
    world: dict[str, Path], tmp_path_factory: pytest.TempPathFactory
) -> tuple[dict[str, Any], Path]:
    output = tmp_path_factory.mktemp("measured") / "out"
    return _run(world, output), output


def _side(paths: dict[str, Path], side: str) -> list[str]:
    return list(json.loads(paths["split"].read_text("utf-8"))[side])


# --- La medición -------------------------------------------------------------------------


def test_the_experiment_measures_the_layer_and_writes_its_outputs(
    world: dict[str, Path], measured: tuple[dict[str, Any], Path]
) -> None:
    summary, output = measured

    assert summary["simulated"] is False
    assert summary["experiment"] == "exp_14_suggestion_layer" and summary["issue"] == 257
    tests = _side(world, "test")
    assert summary["corpus"]["test"]["measured_incipits"] == len(tests)

    # 1. El modelo se entrena con train y el artefacto queda en la salida, sin promover.
    artifact = output / exp_14.ARTIFACT_NAME
    model = summary["model"]
    assert model["artifact_sha256"] == common.sha256_of_file(artifact)
    assert model["promoted"] is False
    trained = json.loads(artifact.read_text("utf-8"))["training"]["train_incipits"]
    assert set(trained).isdisjoint(tests)

    # 1. Validación cruzada de 5 pliegues agrupados por obra dentro de train.
    cv = summary["cross_validation"]
    assert cv["k"] == 5 and cv["grouped_by"].startswith("obra")
    assert len(cv["folds"]) == 5
    folds_incipits = [set(fold["incipits"]) for fold in cv["folds"]]
    assert set().union(*folds_incipits) == set(_side(world, "train"))
    assert sum(len(f) for f in folds_incipits) == len(_side(world, "train"))
    for fold in cv["folds"]:
        works = {primus_work_id(i) for i in fold["incipits"]}
        others = {primus_work_id(i) for f in cv["folds"] if f is not fold for i in f["incipits"]}
        assert works.isdisjoint(others)
    assert set(cv["mean"]) == set(cv["stdev"]) == set(cv["folds"][0]["metrics"])

    test = summary["test"]
    # 2. Primera sugerencia y tres primeras frente a la verdad, y la línea base de la regla.
    ranking = test["rule_suggestions"]
    assert ranking["top1"]["over_true_candidate"]["n"] == ranking["with_true_candidate"]
    assert "baseline_rule_order" in ranking
    # 3. Errores que las reglas no ven, por compás, con y sin capa, y por categoría.
    measures = test["rule_blind_measures"]
    assert (
        measures["rules_and_layer"]["global_metrics"]["recall"]
        >= measures["rules"]["global_metrics"]["recall"]
    )
    assert {"accidental", "duration", "pitch", "structure"} <= set(measures["coverage_by_category"])
    # 4. Antes y después, con la SER y el OMR-NED frente a la verdad.
    before_after = summary["before_after"]
    assert before_after["incipits"] == len(tests)
    for variant in ("homr", "homr_with_high", "homr_with_first"):
        assert before_after["ser"][variant]["mean"] is not None
        assert before_after["omr_ned"][variant]["mean"] is not None
    assert before_after["ser"]["homr_with_first"]["mean"] < before_after["ser"]["homr"]["mean"]
    # 5. Daño, de las de confianza alta y de todas las primeras.
    assert set(test["damage"]) == {"high", "first"}
    assert test["damage"]["first"]["damaged_correct_events"] > 0
    # 6. Curva de aprendizaje.
    curve = summary["learning_curve"]
    assert [point["fraction"] for point in curve["points"]] == [0.1, 0.25, 0.5, 1.0]
    curve_works = [point["train_works"] for point in curve["points"]]
    assert curve_works == sorted(curve_works) and curve_works[-1] == len(
        {primus_work_id(i) for i in _side(world, "train")}
    )
    # 7. Sin sesiones del estudio: el resultado lo dice.
    assert summary["study_sessions"]["available"] is False
    assert summary["study_sessions"]["acceptance_rate"] is None
    # 8. Trazabilidad y límites.
    run_info = json.loads((output / "exp_14_run_info.json").read_text("utf-8"))
    assert run_info == summary["run_info"]
    assert run_info["experiment"] == "exp_14" and run_info["seed"] == 7
    assert run_info["corpus_sha256"] == common.sha256_of_file(world["corpus"])
    assert run_info["split_sha256"] == common.sha256_of_file(world["split"])
    assert run_info["artifact_sha256"] == model["artifact_sha256"]
    assert run_info["feature_version"] == FEATURE_VERSION
    assert run_info["config"] == json.loads(world["config"].read_text("utf-8"))
    assert run_info["homr"]["engine"] == "homr"
    assert {"monophonic_printed", "ideal_corrector", "non_independent_corrections"} <= set(
        summary["methodological_limitations"]
    )
    rows = list(csv.DictReader((output / exp_14.CSV_NAME).open(encoding="utf-8")))
    assert sorted(row["id"] for row in rows) == sorted(tests)


def test_the_same_seed_gives_the_same_measurement(
    world: dict[str, Path], measured: tuple[dict[str, Any], Path], tmp_path: Path
) -> None:
    first, _ = measured
    again = _run(world, tmp_path / "again", with_omr_ned=False)
    for key in ("test", "cross_validation", "learning_curve", "model"):
        assert again[key] == first[key]
    assert again["before_after"]["ser"] == first["before_after"]["ser"]
    assert again["before_after"]["omr_ned"] is None
    # Nada en el `results/` del experimento: la salida va a `--output-dir`.
    assert not any(common.RESULTS_DIR.iterdir())


# --- Sin datos no hay medición -----------------------------------------------------------


def test_it_fails_without_the_corpus_or_the_split(world: dict[str, Path], tmp_path: Path) -> None:
    missing = dict(world, corpus=tmp_path / "nope.jsonl")
    with pytest.raises(FileNotFoundError, match="corpus"):
        _run(missing, tmp_path / "out")
    missing = dict(world, split=tmp_path / "nope.json")
    with pytest.raises(FileNotFoundError, match="partición"):
        _run(missing, tmp_path / "out")
    missing = dict(world, data=tmp_path / "no-data")
    with pytest.raises(FileNotFoundError, match="manifest"):
        _run(missing, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_it_fails_when_the_split_is_not_the_one_of_the_corpus(
    world: dict[str, Path], tmp_path: Path
) -> None:
    paths = _copy(world, tmp_path / "w")
    payload = json.loads(paths["split"].read_text("utf-8"))
    moved = payload["test"].pop(0)
    payload["train"].append(moved)
    paths["split"].write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match=moved):
        _run(paths, tmp_path / "out")


def test_it_fails_when_a_prediction_is_missing(world: dict[str, Path], tmp_path: Path) -> None:
    paths = _copy(world, tmp_path / "w")
    incipit = _side(paths, "train")[0]
    (paths["data"] / "primus" / "exp_12" / "predictions" / f"{incipit}.musicxml").unlink()
    with pytest.raises(ValueError, match="predicción"):
        _run(paths, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_it_fails_when_the_truth_is_missing(world: dict[str, Path], tmp_path: Path) -> None:
    paths = _copy(world, tmp_path / "w")
    incipit = _side(paths, "test")[0]
    (paths["data"] / "primus" / "package_aa" / incipit / f"{incipit}.semantic").unlink()
    with pytest.raises(ValueError, match="verdad"):
        _run(paths, tmp_path / "out")


def test_it_fails_when_the_truth_is_not_the_one_of_the_corpus(
    world: dict[str, Path], tmp_path: Path
) -> None:
    paths = _copy(world, tmp_path / "w")
    incipit = _side(paths, "test")[0]
    semantic = paths["data"] / "primus" / "package_aa" / incipit / f"{incipit}.semantic"
    text = semantic.read_text("utf-8")
    semantic.write_text(text.replace("note-F4_", "note-F#4_", 1), encoding="utf-8")
    with pytest.raises(ValueError, match="corpus"):
        _run(paths, tmp_path / "out")
