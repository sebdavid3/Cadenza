"""Pruebas de los experimentos con datos reales y criterios de validez externa (Issue #24)."""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path
from typing import Any

import pytest
from cadenza.domain import CONTENT_EDIT_OPS, Anchor, EditOp
from cadenza.learning import TrainingSample, omr_ned_pair
from cadenza.omr import OMRTranscriptionError

from ml.experiments import common, exp_01_effort, exp_02_active_learning, exp_03_omr_quality

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_MANIFEST = REPO_ROOT / "data" / "manifest.json"


def test_run_info_generation(tmp_path: Path) -> None:
    manifest_stub = tmp_path / "manifest.json"
    manifest_stub.write_text('{"corpus": "test"}', encoding="utf-8")

    info = common.get_run_info("test_exp", seed=123, manifest_path=manifest_stub)
    assert info["experiment"] == "test_exp"
    assert info["seed"] == 123
    assert "timestamp_utc" in info
    assert "git_commit" in info
    assert info["manifest_sha256"] != ""


def _piano_corpus(tmp_path: Path, *, with_predictions: bool = True) -> tuple[Path, Path]:
    """Corpus de una partitura cuya predicción cambia una altura de la verdad de referencia."""
    piano = REPO_ROOT / "packages" / "interchange" / "tests" / "fixtures" / "piano.musicxml"
    piano_xml = piano.read_text(encoding="utf-8")
    gt_dir = tmp_path / "mini" / "gt"
    preds_dir = tmp_path / "mini" / "predictions"
    gt_dir.mkdir(parents=True)
    preds_dir.mkdir(parents=True)
    (gt_dir / "p1.musicxml").write_text(piano_xml, encoding="utf-8")
    if with_predictions:
        (preds_dir / "p1.musicxml").write_text(
            piano_xml.replace("<step>G</step>", "<step>A</step>"), encoding="utf-8"
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {"corpus": "mini", "entries": [{"id": "p1", "ground_truth": "mini/gt/p1.musicxml"}]}
        ),
        encoding="utf-8",
    )
    return manifest, preds_dir


def test_sample_size_justification_derives_standard_errors_from_counts() -> None:
    """El error estándar se calcula con los N de la ejecución, no se escribe a mano (#139)."""
    justification = common.sample_size_justification(
        "mini",
        counts={"total_measures": 50},
        proportions={"measures_with_real_errors": (20, 50)},
        worst_case={"derived_edits": 25},
    )
    assert justification["corpus"] == "mini"
    assert justification["total_measures"] == 50

    observed = justification["standard_errors"]["measures_with_real_errors"]
    assert observed["proportion"] == 0.4
    assert observed["standard_error"] == round(math.sqrt(0.4 * 0.6 / 50), 4)
    assert justification["standard_errors"]["derived_edits"]["worst_case_standard_error"] == 0.1

    text = justification["statistical_power"]
    assert "N = 50" in text and "N = 25" in text
    assert "independencia" in justification["assumptions"]
    assert "544" not in text and "359" not in text


def test_sample_size_justification_without_observations_estimates_nothing() -> None:
    justification = common.sample_size_justification(
        "mini", counts={"total_measures": 0}, proportions={"x": (0, 0)}
    )
    assert justification["standard_errors"]["x"] is None
    assert "Sin observaciones" in justification["statistical_power"]


def test_methodological_limitations_contain_no_figures() -> None:
    """Las limitaciones comunes no llevan recuentos fijos de una ejecución concreta (#139)."""
    for key, text in common.METHODOLOGICAL_LIMITATIONS.items():
        assert not any(ch.isdigit() for ch in text), key


def test_exp_01_fails_without_corpus(tmp_path: Path) -> None:
    """Sin corpus no hay resultado de reserva: el experimento falla (CLAUDE.md §8.1)."""
    missing = tmp_path / "manifest.json"
    with pytest.raises(FileNotFoundError, match="corpus PrIMuS"):
        exp_01_effort.run(manifest_path=missing)


def test_exp_01_fails_without_usable_predictions(tmp_path: Path) -> None:
    """Un manifiesto sin predicciones no produce un resultado con ceros (#139)."""
    manifest, preds_dir = _piano_corpus(tmp_path, with_predictions=False)
    with pytest.raises(ValueError, match="ninguna predicción"):
        exp_01_effort.run(manifest_path=manifest, predictions_dir=preds_dir)
    assert not (common.RESULTS_DIR / "effort_comparison_by_score.csv").exists()


def test_exp_01_reports_counts_and_interpretation_of_this_run(tmp_path: Path) -> None:
    """Justificación muestral e interpretación salen de lo medido en la ejecución (#139)."""
    manifest, preds_dir = _piano_corpus(tmp_path)
    res = exp_01_effort.run(manifest_path=manifest, predictions_dir=preds_dir)

    justification = res["sample_size_justification"]
    effort = res["inspection_effort"]
    tradeoff = res["error_detection_and_tradeoff"]
    assert justification["corpus"] == "mini"
    assert justification["entries_considered"] == 1
    assert justification["transcribed_scores"] == 1
    assert justification["total_measures"] == effort["total_measures"]
    assert justification["measures_with_errors"] == tradeoff["measures_with_real_errors"]

    text = res["missed_errors_breakdown"]["scientific_interpretation"]
    assert "inmensa mayoría" not in text
    assert f"{effort['baseline_inspections_manual']} manuales" in text
    assert f"{effort['assisted_inspections_validator']} asistidas" in text


def test_exp_01_interpretation_lists_missed_operations_by_count() -> None:
    """El desglose de la interpretación es el de `missed_operations`, ordenado (#139)."""
    text = exp_01_effort._missed_errors_interpretation(
        missed_operations={"SetPitch": 2, "SetAccidental": 6},
        fn_missed=5,
        measures_with_real_errors=10,
        baseline_inspections=40,
        assisted_inspections=12,
    )
    assert "5 de 10" in text
    assert text.index("SetAccidental 6") < text.index("SetPitch 2")
    assert "75.00%" in text and "25.00%" in text
    assert "inspección humana" in text

    clean = exp_01_effort._missed_errors_interpretation(
        missed_operations={},
        fn_missed=0,
        measures_with_real_errors=3,
        baseline_inspections=10,
        assisted_inspections=3,
    )
    assert "todos los compases con error real" in clean

    undefined = exp_01_effort._missed_errors_interpretation(
        missed_operations={},
        fn_missed=0,
        measures_with_real_errors=0,
        baseline_inspections=10,
        assisted_inspections=4,
    )
    assert "no está definida" in undefined
    assert "0 de 0" not in undefined and "todos los compases" not in undefined


@pytest.mark.skipif(not DATA_MANIFEST.is_file(), reason="Requiere data/manifest.json")
def test_exp_01_real_primus_data() -> None:
    # Limitado a 5 incipits para rapidez en suite de pruebas
    res = exp_01_effort.run(manifest_path=DATA_MANIFEST, limit=5, seed=20260920)
    assert res["experiment"] == "exp_01_effort"
    assert res["mode"] == "real_data_primus"
    effort = res["inspection_effort"]
    assert effort["total_measures"] > 0
    assert effort["assisted_inspections_validator"] <= effort["baseline_inspections_manual"]

    tradeoff = res["error_detection_and_tradeoff"]
    # En datos reales de HOMR, el validador no atrapa el 100% de los errores (no es circular)
    assert tradeoff["false_negatives_missed"] >= 0
    assert "by_operation" in res["missed_errors_breakdown"]


def _test_pool(size: int = 60, seed: int = 7) -> tuple[TrainingSample, ...]:
    """Pool determinista solo para probar el cálculo de exp_02, nunca como resultado."""
    rng = random.Random(seed)
    # Las de contenido, en su orden: las de marcas no son muestras (ADR-0039).
    ops = [op for op in EditOp if op in CONTENT_EDIT_OPS]
    return tuple(
        TrainingSample(
            document_id="doc-prueba",
            anchor=Anchor(
                part=0, staff=0, measure=i, voice=0, event_index=0, staff_id="part-0-staff-0"
            ),
            before_pitch="C4",
            after_pitch="D4",
            seq=i,
            op=ops[i % len(ops)],
            correction_magnitude=round(rng.uniform(1.0, 12.0), 2),
            error_density=round(rng.betavariate(2.0, 5.0), 4),
            features=tuple(round(rng.uniform(0.0, 1.0), 4) for _ in range(8)),
        )
        for i in range(1, size + 1)
    )


def test_exp_02_fails_without_corpus(tmp_path: Path) -> None:
    """Sin corpus no hay resultado de reserva (CLAUDE.md §8.1, #134)."""
    with pytest.raises(FileNotFoundError, match="corpus PrIMuS"):
        exp_02_active_learning.run(manifest_path=tmp_path / "manifest.json")


def test_exp_02_fails_when_no_real_samples(tmp_path: Path) -> None:
    """Un manifiesto sin predicciones no se sustituye por datos sintéticos (#134)."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "corpus": "primus",
                "entries": [{"id": "x", "image": "x.png", "ground_truth": "x.mei"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ninguna muestra real"):
        exp_02_active_learning.run(manifest_path=manifest)


def test_exp_02_interpretation_comes_from_measured_values() -> None:
    """La interpretación cita los valores medidos, no cifras escritas a mano (#134)."""
    res = exp_02_active_learning._evaluate_pool(_test_pool(), seed=42, manifest_path=None)
    evals = res["canonical_evaluations"]
    assert set(evals) == {"uncertainty", "diversity", "hybrid", "random"}
    assert res["jaccard_similarity_matrix"]["uncertainty"]["uncertainty"] == 1.0

    text = res["scientific_interpretation"]
    best_error = max(e["mean_error_density"] for e in evals.values())
    best_magnitude = max(e["total_correction_magnitude"] for e in evals.values())
    assert f"{best_error:.3f}" in text
    assert f"{best_magnitude:.3f}" in text
    assert f"{res['jaccard_similarity_matrix']['hybrid']['uncertainty']:.3f}" in text
    assert "46.50" not in text


def test_exp_02_interpretation_reports_ties_when_pool_fits_budget() -> None:
    """Con un pool que no supera el presupuesto todas empatan y se advierte (#134)."""
    pool = _test_pool(size=exp_02_active_learning.CANONICAL_BUDGET)
    res = exp_02_active_learning._evaluate_pool(pool, seed=42, manifest_path=None)
    text = res["scientific_interpretation"]
    assert "no discrimina" in text
    assert "'uncertainty', 'diversity', 'hybrid', 'random'" in text


def test_exp_02_sample_size_comes_from_the_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La justificación muestral de exp_02 cuenta el pool de la ejecución (#139)."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"corpus": "mini", "entries": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}),
        encoding="utf-8",
    )
    pool = _test_pool(size=30)
    monkeypatch.setattr(
        exp_02_active_learning, "build_real_training_pool", lambda *args, **kwargs: pool
    )

    res = exp_02_active_learning.run(manifest_path=manifest, limit=2)
    justification = res["sample_size_justification"]
    assert justification["corpus"] == "mini"
    assert justification["entries_considered"] == 2
    assert justification["scores_with_edits"] == 1
    assert justification["derived_edits_count"] == res["pool_size"] == 30
    assert justification["standard_errors"]["derived_edits"]["n"] == 30
    assert "544" not in json.dumps(justification)


@pytest.mark.skipif(not DATA_MANIFEST.is_file(), reason="Requiere data/manifest.json")
def test_exp_02_real_data_criteria_and_jaccard() -> None:
    # Usar el pool generado sobre datos reales
    res = exp_02_active_learning.run(manifest_path=DATA_MANIFEST, limit=10, seed=20260920)
    assert res["experiment"] == "exp_02_active_learning"
    assert res["mode"] == "real_data_primus"
    assert res["pool_size"] > 0

    evals = res["canonical_evaluations"]
    # 1. Densidad de error: uncertainty debe ser mayor que diversity y random
    assert evals["uncertainty"]["mean_error_density"] >= evals["diversity"]["mean_error_density"]
    assert evals["uncertainty"]["mean_error_density"] >= evals["random"]["mean_error_density"]

    # 2. Diversidad de features: diversity o hybrid debe tener spread significativo
    assert evals["diversity"]["mean_pairwise_spread"] > 0.0

    # 3. Disimilitud de Jaccard: hybrid NO coincide trivialmente con uncertainty en datos reales
    jaccard_hyb_unc = res["jaccard_similarity_matrix"]["hybrid"]["uncertainty"]
    assert jaccard_hyb_unc < 1.0


def test_exp_03_fails_without_manifest_and_keeps_run_info(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin corpus no hay modo de prueba ni se sobrescribe el run_info real (#139)."""
    missing = tmp_path / "manifest.json"
    with pytest.raises(FileNotFoundError, match="corpus"):
        exp_03_omr_quality.run(missing, None, None)

    monkeypatch.setattr(sys, "argv", ["exp_03_omr_quality.py", "--manifest", str(missing)])
    with pytest.raises(FileNotFoundError, match="corpus"):
        exp_03_omr_quality.main()
    assert not (common.RESULTS_DIR / "exp_03_run_info.json").exists()


def test_exp_03_fails_without_any_transcription_evidence(tmp_path: Path) -> None:
    """Sin predicciones ni fallos registrados por exp_04 no se imputa un 100 % de fallos (#139)."""
    manifest, preds_dir = _piano_corpus(tmp_path, with_predictions=False)
    with pytest.raises(ValueError, match="exp_04"):
        exp_03_omr_quality.run(manifest, preds_dir, None, write_results=False)


def test_exp_03_sample_size_comes_from_this_run(tmp_path: Path) -> None:
    """La justificación muestral usa los recuentos de la ejecución (#139)."""
    manifest, preds_dir = _piano_corpus(tmp_path)
    res = exp_03_omr_quality.run(manifest, preds_dir, None, write_results=False)
    justification = res["sample_size_justification"]
    assert justification["corpus"] == "mini"
    assert justification["entries_considered"] == res["total_evaluated"] == 1
    assert justification["successful_transcriptions"] == res["successes_count"] == 1
    assert justification["failed_transcriptions"] == res["failures_count"] == 0
    assert justification["standard_errors"]["failure_rate"]["n"] == 1


def _write_omr_cache(predicted: Path, ground_truth: Path) -> Path:
    """CSV de caché de exp_03 con una fila de éxito de valores imposibles de medir aquí."""
    cache = common.RESULTS_DIR / "omr_baseline.csv"
    cache.parent.mkdir(parents=True, exist_ok=True)
    row = dict.fromkeys(exp_03_omr_quality.CSV_FIELDS, "")
    row.update(
        id="p1",
        status="success",
        predicted=str(predicted),
        ground_truth=str(ground_truth),
        predicted_symbols="10",
        ground_truth_symbols="10",
        edit_distance="9",
        omr_ned="0.9999",
        pred_ser_symbols="10",
        gt_ser_symbols="10",
        ser_edit_distance="9",
        ser="0.9999",
        predicted_sha256=common.sha256_of_file(predicted),
        ground_truth_sha256=common.sha256_of_file(ground_truth),
    )
    lines = [",".join(exp_03_omr_quality.CSV_FIELDS), ",".join(row.values())]
    cache.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return cache


def test_exp_03_reuses_cache_only_for_the_same_prediction_content(tmp_path: Path) -> None:
    """La caché vale si la predicción y la verdad no cambiaron de contenido (#139)."""
    manifest, preds_dir = _piano_corpus(tmp_path)
    prediction = preds_dir / "p1.musicxml"
    ground_truth = tmp_path / "mini" / "gt" / "p1.musicxml"

    _write_omr_cache(prediction, ground_truth)
    cached = exp_03_omr_quality.run(manifest, preds_dir, None, write_results=False)
    assert cached["metrics_on_successes"]["mean_omr_ned"] == 0.9999

    # Otra predicción en la misma ruta y con la misma fecha (p. ej. copiada con `copy2`).
    import os

    original = prediction.read_text(encoding="utf-8")
    stamp = prediction.stat().st_mtime
    prediction.write_text(original.replace("<step>A</step>", "<step>B</step>"), encoding="utf-8")
    os.utime(prediction, (stamp, stamp))
    other = exp_03_omr_quality.run(manifest, preds_dir, None, write_results=False)
    assert other["metrics_on_successes"]["mean_omr_ned"] != 0.9999

    # Otra verdad de referencia con la misma predicción.
    prediction.write_text(original, encoding="utf-8")
    _write_omr_cache(prediction, ground_truth)
    ground_truth.write_text(ground_truth.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    regenerated_gt = exp_03_omr_quality.run(manifest, preds_dir, None, write_results=False)
    assert regenerated_gt["metrics_on_successes"]["mean_omr_ned"] != 0.9999


def test_exp_03_does_not_reuse_a_cache_without_content_hashes(tmp_path: Path) -> None:
    """Un CSV anterior a #139 (sin sha256) no se reutiliza: se mide de nuevo."""
    manifest, preds_dir = _piano_corpus(tmp_path)
    prediction = preds_dir / "p1.musicxml"
    cache = _write_omr_cache(prediction, tmp_path / "mini" / "gt" / "p1.musicxml")
    old_fields = [f for f in exp_03_omr_quality.CSV_FIELDS if not f.endswith("_sha256")]
    header, row = cache.read_text(encoding="utf-8").splitlines()
    values = dict(zip(header.split(","), row.split(","), strict=True))
    cache.write_text(
        ",".join(old_fields) + "\n" + ",".join(values[f] for f in old_fields) + "\n",
        encoding="utf-8",
    )
    res = exp_03_omr_quality.run(manifest, preds_dir, None, write_results=False)
    assert res["metrics_on_successes"]["mean_omr_ned"] != 0.9999


def test_exp_03_fails_when_some_entries_were_never_transcribed(tmp_path: Path) -> None:
    """Una entrada sin predicción ni fallo registrado no se cuenta como fallo de HOMR (#139)."""
    manifest, preds_dir = _piano_corpus(tmp_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["entries"].append({"id": "p2", "ground_truth": "mini/gt/p1.musicxml"})
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match=r"1 de 2 entradas"):
        exp_03_omr_quality.run(manifest, preds_dir, None, write_results=False)

    (preds_dir / "failures.json").write_text(
        json.dumps([{"id": "p2", "error": "Exception: No staffs found"}]), encoding="utf-8"
    )
    res = exp_03_omr_quality.run(manifest, preds_dir, None, write_results=False)
    assert res["failures_count"] == 1
    assert res["failures_detail"] == [{"id": "p2", "error": "Exception: No staffs found"}]
    ned = res["metrics_on_successes"]["mean_omr_ned"]
    penalized = res["metrics_penalized_with_failures"]["mean_omr_ned_penalized"]
    assert penalized == round((ned + 1.0) / 2, 4)


@pytest.mark.skipif(not DATA_MANIFEST.is_file(), reason="Requiere data/manifest.json")
def test_exp_03_real_baseline_reports_failures_and_penalty() -> None:
    res = exp_03_omr_quality.run(DATA_MANIFEST, predictions=None, limit=15, write_results=False)
    assert res["experiment"] == "exp_03_omr_quality"
    assert res["total_evaluated"] == 15
    # La tasa penalizada debe ser mayor o igual a la media sobre éxitos si hubo algún fallo
    succ = res["metrics_on_successes"]["mean_omr_ned"]
    pen = res["metrics_penalized_with_failures"]["mean_omr_ned_penalized"]
    if res["failures_count"] > 0:
        assert pen >= succ
    # Verificación de métricas SER
    assert "mean_ser" in res["metrics_on_successes"]
    assert "mean_ser_penalized" in res["metrics_penalized_with_failures"]
    succ_ser = res["metrics_on_successes"]["mean_ser"]
    pen_ser = res["metrics_penalized_with_failures"]["mean_ser_penalized"]
    if res["failures_count"] > 0 and succ_ser is not None and pen_ser is not None:
        assert pen_ser >= succ_ser


def _exp07_corpus(tmp_path: Path, count: int = 3) -> Path:
    """Corpus mínimo: una imagen ficticia y un *ground truth* MusicXML por partitura."""
    fixture = Path(__file__).parent / "fixtures" / "simple.musicxml"
    entries = []
    for index in range(count):
        score_dir = tmp_path / "mini" / f"s{index}"
        score_dir.mkdir(parents=True)
        (score_dir / f"s{index}.png").write_bytes(b"png")
        (score_dir / f"s{index}.musicxml").write_text(
            fixture.read_text(encoding="utf-8"), encoding="utf-8"
        )
        entries.append(
            {
                "id": f"s{index}",
                "image": f"mini/s{index}/s{index}.png",
                "ground_truth": f"mini/s{index}/s{index}.musicxml",
            }
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"corpus": "mini", "entries": entries}), encoding="utf-8")
    return manifest


def _exp07_baseline(manifest: Path, successes: list[str], failures: list[str]) -> Path:
    fixture = Path(__file__).parent / "fixtures" / "simple.musicxml"
    predictions = manifest.parent / "mini" / "predictions"
    predictions.mkdir(parents=True)
    for entry_id in successes:
        (predictions / f"{entry_id}.musicxml").write_text(
            fixture.read_text(encoding="utf-8"), encoding="utf-8"
        )
    (predictions / "failures.json").write_text(
        json.dumps([{"id": entry_id, "error": "No staffs found"} for entry_id in failures]),
        encoding="utf-8",
    )
    return predictions


class _Exp07Engine:
    """Motor de prueba: devuelve el MusicXML indicado por partitura o falla.

    `fail` imita al adaptador (envuelve la excepción del motor en
    `OMRTranscriptionError`); `env` imita un error del entorno.
    """

    def __init__(self, outcomes: dict[str, str]) -> None:
        self._outcomes = outcomes
        self.calls: list[str] = []
        fixture = Path(__file__).parent / "fixtures" / "simple.musicxml"
        self._exact = fixture.read_text(encoding="utf-8")

    def transcribe_musicxml(self, image_path: Path) -> str:
        entry_id = image_path.stem
        self.calls.append(entry_id)
        outcome = self._outcomes[entry_id]
        if outcome == "fail":
            raise OMRTranscriptionError("No staffs found") from TimeoutError()
        if outcome == "env":
            raise RuntimeError("HOMREngine requiere el extra opcional 'homr'")
        if outcome == "worse":
            return self._exact.replace("<step>C</step>", "<step>E</step>")
        return self._exact


def test_exp_07_measures_recovery_and_regression(tmp_path: Path) -> None:
    from cadenza.omr.preprocessing import PreprocessingConfig

    from ml.experiments import exp_07_preprocessing_impact as exp_07

    manifest = _exp07_corpus(tmp_path)
    _exp07_baseline(manifest, successes=["s0", "s2"], failures=["s1"])
    engine = _Exp07Engine({"s0": "worse", "s1": "exact", "s2": "fail"})

    res = exp_07.run_preprocessing_experiment(
        manifest,
        configs={"probe": PreprocessingConfig(enabled=True, binarize=True)},
        engine_factory=lambda _config, _use_gpu: engine,
        write_results=False,
    )

    assert res["simulated"] is False
    assert res["total_samples"] == 3
    # Línea base: dos aciertos exactos (0) y un fallo (penalizado con 1).
    assert res["baseline"]["failures"] == 1
    assert res["baseline"]["failure_rate"] == 0.3333
    assert res["baseline"]["mean_omr_ned_successes"] == 0.0
    assert res["baseline"]["mean_omr_ned_penalized"] == 0.3333
    assert res["baseline"]["mean_ser_penalized"] == 0.3333

    # Variante: s0 empeora, s1 se recupera (exacta) y s2 falla.
    predictions = exp_07.predictions_dir(manifest, "probe")
    ground_truth = manifest.parent / "mini" / "s0" / "s0.musicxml"
    worse_ned = omr_ned_pair(predictions / "s0.musicxml", ground_truth).omr_ned
    assert worse_ned > 0

    probe = res["configurations"]["probe"]
    assert probe["summary"]["failures"] == 1
    assert probe["summary"]["failure_rate"] == 0.3333
    assert probe["summary"]["mean_omr_ned_successes"] == round(worse_ned / 2, 4)
    assert probe["summary"]["mean_omr_ned_penalized"] == round((worse_ned + 1.0) / 3, 4)
    versus = probe["versus_baseline"]
    assert versus["recovered"] == ["s1"]
    assert versus["regressed"] == ["s2"]
    assert versus["paired_successes"] == 1
    assert versus["paired_mean_omr_ned_delta"] == round(worse_ned, 4)
    assert versus["paired_mean_ser_delta"] > 0
    assert versus["paired_omr_ned_worsened"] == 1
    assert versus["paired_omr_ned_improved"] == 0
    assert versus["paired_omr_ned_equal"] == 0
    assert sorted(engine.calls) == ["s0", "s1", "s2"]


def test_exp_07_requires_baseline_predictions(tmp_path: Path) -> None:
    from ml.experiments import exp_07_preprocessing_impact as exp_07

    manifest = _exp07_corpus(tmp_path)
    with pytest.raises(FileNotFoundError, match="directorio de predicciones"):
        exp_07.run_preprocessing_experiment(
            manifest,
            engine_factory=lambda _config, _use_gpu: _Exp07Engine({}),
            write_results=False,
        )


def test_exp_07_missing_prediction_is_not_counted_as_failure(tmp_path: Path) -> None:
    """Una predicción que nunca se intentó no puede contarse como fallo del motor."""
    from ml.experiments import exp_07_preprocessing_impact as exp_07

    manifest = _exp07_corpus(tmp_path)
    predictions = _exp07_baseline(manifest, successes=["s0"], failures=["s1"])
    with pytest.raises(FileNotFoundError, match="s2"):
        exp_07.measure_predictions(manifest, predictions)


def test_exp_07_transcription_resumes_without_repeating(tmp_path: Path) -> None:
    from cadenza.omr.preprocessing import PreprocessingConfig

    from ml.experiments import exp_07_preprocessing_impact as exp_07

    manifest = _exp07_corpus(tmp_path)
    config = PreprocessingConfig(enabled=True, rescale=True)
    engine = _Exp07Engine({"s0": "exact", "s1": "fail", "s2": "exact"})

    def factory(_config: PreprocessingConfig, _use_gpu: bool) -> _Exp07Engine:
        return engine

    first = exp_07.transcribe_config(manifest, "probe", config, engine_factory=factory)
    assert first == {"written": 2, "reused": 0, "failures": 1}

    second = exp_07.transcribe_config(manifest, "probe", config, engine_factory=factory)
    assert second == {"written": 0, "reused": 3, "failures": 1}
    assert len(engine.calls) == 3

    forced = exp_07.transcribe_config(manifest, "probe", config, engine_factory=factory, force=True)
    assert forced == {"written": 2, "reused": 0, "failures": 1}

    # El registro conserva el tipo de la excepción original del motor.
    recorded = json.loads(
        (exp_07.predictions_dir(manifest, "probe") / "failures.json").read_text(encoding="utf-8")
    )
    assert recorded == [
        {"id": "s1", "error": "OMRTranscriptionError [TimeoutError]: No staffs found"}
    ]

    # Con `limit`, los fallos contados son solo los de las partituras consideradas.
    limited = exp_07.transcribe_config(manifest, "probe", config, engine_factory=factory, limit=1)
    assert limited == {"written": 0, "reused": 1, "failures": 0}


def test_exp_07_retry_failures_repeats_only_recorded_failures(tmp_path: Path) -> None:
    from cadenza.omr.preprocessing import PreprocessingConfig

    from ml.experiments import exp_07_preprocessing_impact as exp_07

    manifest = _exp07_corpus(tmp_path)
    config = PreprocessingConfig(enabled=True, rescale=True)
    failing = _Exp07Engine({"s0": "exact", "s1": "fail", "s2": "exact"})
    exp_07.transcribe_config(manifest, "probe", config, engine_factory=lambda _c, _g: failing)

    recovered = _Exp07Engine({"s0": "exact", "s1": "exact", "s2": "exact"})
    result = exp_07.transcribe_config(
        manifest, "probe", config, engine_factory=lambda _c, _g: recovered, retry_failures=True
    )

    assert recovered.calls == ["s1"]
    assert result == {"written": 1, "reused": 2, "failures": 0}
    assert (exp_07.predictions_dir(manifest, "probe") / "s1.musicxml").is_file()


def test_exp_07_environment_error_is_not_recorded_as_failure(tmp_path: Path) -> None:
    """Sin el motor, el experimento se detiene: no inventa fallos ni borra predicciones."""
    from cadenza.omr.preprocessing import PreprocessingConfig

    from ml.experiments import exp_07_preprocessing_impact as exp_07

    manifest = _exp07_corpus(tmp_path)
    config = PreprocessingConfig(enabled=True, rescale=True)
    working = _Exp07Engine({"s0": "exact", "s1": "exact", "s2": "exact"})
    exp_07.transcribe_config(manifest, "probe", config, engine_factory=lambda _c, _g: working)

    broken = _Exp07Engine({"s0": "env", "s1": "env", "s2": "env"})
    with pytest.raises(RuntimeError, match="homr"):
        exp_07.transcribe_config(
            manifest, "probe", config, engine_factory=lambda _c, _g: broken, force=True
        )

    predictions = exp_07.predictions_dir(manifest, "probe")
    assert sorted(path.name for path in predictions.glob("*.musicxml")) == [
        "s0.musicxml",
        "s1.musicxml",
        "s2.musicxml",
    ]
    assert json.loads((predictions / "failures.json").read_text(encoding="utf-8")) == []


def test_exp_07_refuses_predictions_of_another_configuration(tmp_path: Path) -> None:
    from cadenza.omr.preprocessing import PreprocessingConfig

    from ml.experiments import exp_07_preprocessing_impact as exp_07

    manifest = _exp07_corpus(tmp_path)
    engine = _Exp07Engine({"s0": "exact", "s1": "exact", "s2": "exact"})

    def factory(_config: PreprocessingConfig, _use_gpu: bool) -> _Exp07Engine:
        return engine

    exp_07.transcribe_config(
        manifest, "probe", PreprocessingConfig(enabled=True, rescale=True), engine_factory=factory
    )
    other = PreprocessingConfig(enabled=True, binarize=True)
    with pytest.raises(ValueError, match="otra configuración"):
        exp_07.transcribe_config(manifest, "probe", other, engine_factory=factory)
    assert len(engine.calls) == 3

    forced = exp_07.transcribe_config(manifest, "probe", other, engine_factory=factory, force=True)
    assert forced == {"written": 3, "reused": 0, "failures": 0}


def test_exp_07_measures_existing_predictions_without_transcribing(tmp_path: Path) -> None:
    from cadenza.omr.preprocessing import PreprocessingConfig

    from ml.experiments import exp_07_preprocessing_impact as exp_07

    manifest = _exp07_corpus(tmp_path)
    _exp07_baseline(manifest, successes=["s0", "s1", "s2"], failures=[])
    config = PreprocessingConfig(enabled=True, binarize=True)
    engine = _Exp07Engine({"s0": "exact", "s1": "exact", "s2": "exact"})
    exp_07.transcribe_config(manifest, "probe", config, engine_factory=lambda _c, _g: engine)

    def forbidden(_config: PreprocessingConfig, _use_gpu: bool) -> _Exp07Engine:
        raise AssertionError("no debe crearse el motor")

    res = exp_07.run_preprocessing_experiment(
        manifest,
        configs={"probe": config},
        transcribe=False,
        engine_factory=forbidden,
        write_results=False,
    )

    probe = res["configurations"]["probe"]
    assert probe["transcription"] is None
    assert probe["summary"]["failures"] == 0
    assert probe["versus_baseline"]["paired_successes"] == 3
    assert probe["versus_baseline"]["paired_omr_ned_equal"] == 3
    assert probe["versus_baseline"]["paired_mean_omr_ned_delta"] == 0.0


def test_exp_07_compare_without_common_successes() -> None:
    from ml.experiments import exp_07_preprocessing_impact as exp_07

    success = {"status": "success", "omr_ned": 0.2, "ser": 0.1, "error": ""}
    failure = {"status": "failure", "omr_ned": 1.0, "ser": 1.0, "error": "x"}
    versus = exp_07.compare({"a": success, "b": failure}, {"a": failure, "b": success})

    assert versus["recovered"] == ["b"]
    assert versus["regressed"] == ["a"]
    assert versus["paired_successes"] == 0
    assert versus["paired_mean_omr_ned_delta"] is None
    assert versus["paired_mean_ser_delta"] is None
    assert exp_07.summarize({"a": success, "b": failure}) == {
        "total": 2,
        "successes": 1,
        "failures": 1,
        "failure_rate": 0.5,
        "mean_omr_ned_successes": 0.2,
        "median_omr_ned_successes": 0.2,
        "mean_ser_successes": 0.1,
        "mean_omr_ned_penalized": 0.6,
        "mean_ser_penalized": 0.55,
    }


def test_exp_07_control_configuration_does_not_preprocess() -> None:
    from ml.experiments import exp_07_preprocessing_impact as exp_07

    assert exp_07.CONFIGS[exp_07.CONTROL].enabled is False
    assert all(config.enabled for name, config in exp_07.CONFIGS.items() if name != exp_07.CONTROL)


def test_exp_07_writes_results_only_to_results_dir(tmp_path: Path) -> None:
    from cadenza.omr.preprocessing import PreprocessingConfig

    from ml.experiments import exp_07_preprocessing_impact as exp_07

    manifest = _exp07_corpus(tmp_path, count=1)
    _exp07_baseline(manifest, successes=["s0"], failures=[])

    exp_07.run_preprocessing_experiment(
        manifest,
        configs={"probe": PreprocessingConfig(enabled=True, binarize=True)},
        engine_factory=lambda _config, _use_gpu: _Exp07Engine({"s0": "exact"}),
    )

    # La fixture de `conftest.py` redirige `RESULTS_DIR` de todos los experimentos.
    results_dir = common.RESULTS_DIR
    summary_file = results_dir / "preprocessing_impact_summary.json"
    written = json.loads(summary_file.read_text(encoding="utf-8"))
    assert written["simulated"] is False
    assert (results_dir / "preprocessing_comparison.csv").is_file()
    assert (results_dir / "exp_07_run_info.json").is_file()


def test_corpus_smb_and_muscima_spec() -> None:
    from ml.experiments.corpus import CORPORA

    assert "smb" in CORPORA
    assert "muscima_pp" in CORPORA
    assert CORPORA["smb"].ground_truth_format != ""
    assert "MuNG" in CORPORA["muscima_pp"].ground_truth_format


def test_corpus_build_manifest_smb_and_muscima(tmp_path: Path) -> None:
    from ml.experiments.corpus import build_manifest

    # Subconjunto SMB
    smb_dir = tmp_path / "smb"
    smb_dir.mkdir(parents=True)
    (smb_dir / "score_01.png").write_bytes(b"\x89PNG\r\n\x1a\nfakeimage")
    (smb_dir / "score_01.krn").write_text("**kern\n*k[]\n4c\n*-", encoding="utf-8")

    manifest_smb = build_manifest(tmp_path, "smb")
    assert manifest_smb["corpus"] == "smb"
    assert manifest_smb["count"] == 1
    entries_smb = manifest_smb["entries"]
    assert isinstance(entries_smb, list)
    assert entries_smb[0]["id"] == "score_01"

    # Subconjunto MUSCIMA++
    muscima_dir = tmp_path / "muscima_pp"
    muscima_dir.mkdir(parents=True)
    (muscima_dir / "CVC_01.png").write_bytes(b"\x89PNG\r\n\x1a\nfakeimage")
    (muscima_dir / "CVC_01.xml").write_text("<mung></mung>", encoding="utf-8")

    manifest_muscima = build_manifest(tmp_path, "muscima_pp")
    assert manifest_muscima["corpus"] == "muscima_pp"
    assert manifest_muscima["count"] == 1
    entries_muscima = manifest_muscima["entries"]
    assert isinstance(entries_muscima, list)
    assert entries_muscima[0]["id"] == "CVC_01"


def test_exp_09_is_retired() -> None:
    """`exp_09` no evaluaba ningún corpus real y SMB y MUSCIMA++ son trabajo futuro (#102, #271)."""
    import importlib.util

    assert importlib.util.find_spec("ml.experiments.exp_09_multicorpus_evaluation") is None
    experiments = REPO_ROOT / "ml" / "experiments"
    assert not list(experiments.glob("exp_09*.py"))


def test_exp_01_effort_smb_custom_manifest(tmp_path: Path) -> None:
    # Preparar predicción y GT de SMB usando piano.musicxml
    piano_xml = (
        REPO_ROOT / "packages" / "interchange" / "tests" / "fixtures" / "piano.musicxml"
    ).read_text(encoding="utf-8")

    smb_root = tmp_path / "smb"
    preds_dir = smb_root / "predictions"
    gt_dir = smb_root / "gt"
    preds_dir.mkdir(parents=True)
    gt_dir.mkdir(parents=True)

    (gt_dir / "piano_score.musicxml").write_text(piano_xml, encoding="utf-8")
    (preds_dir / "piano_score.musicxml").write_text(piano_xml, encoding="utf-8")

    manifest_file = tmp_path / "manifest.json"
    manifest_data = {
        "corpus": "smb",
        "entries": [
            {
                "id": "piano_score",
                "ground_truth": "smb/gt/piano_score.musicxml",
            }
        ],
    }
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    res = exp_01_effort.run(manifest_path=manifest_file, predictions_dir=preds_dir)
    assert res["experiment"] == "exp_01_effort"
    assert res["mode"] == "real_data_smb"
    assert res["corpus"] == "smb"
    assert res["inspection_effort"]["total_measures"] == 4  # 2 staves * 2 measures


def test_exp_05_and_exp_06_fail_without_corpus_or_predictions(tmp_path: Path) -> None:
    """Sin manifiesto o sin predicciones no escriben resultados con ceros (#139)."""
    from ml.experiments import exp_05_edit_derivation, exp_06_validation_metrics

    missing = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError, match="manifiesto"):
        exp_05_edit_derivation.run_derivation_experiment(missing)
    with pytest.raises(FileNotFoundError, match="manifiesto"):
        exp_06_validation_metrics.run_validation_experiment(missing)

    manifest, preds_dir = _piano_corpus(tmp_path, with_predictions=False)
    with pytest.raises(ValueError, match="ninguna predicción"):
        exp_05_edit_derivation.run_derivation_experiment(manifest, preds_dir)
    with pytest.raises(ValueError, match="ninguna predicción"):
        exp_06_validation_metrics.run_validation_experiment(manifest, preds_dir)
    assert not (common.RESULTS_DIR / "primus_edit_distribution.json").exists()
    assert not (common.RESULTS_DIR / "validation_metrics_summary.json").exists()


def test_exp_05_reports_failures_and_unverified_ids_of_this_run(tmp_path: Path) -> None:
    """Fallos e incipits sin verificar salen de la ejecución, no de una lista fija (#139)."""
    from ml.experiments import exp_05_edit_derivation

    manifest, preds_dir = _piano_corpus(tmp_path)
    summary = exp_05_edit_derivation.run_derivation_experiment(manifest, preds_dir)
    verification = summary["structurally_verified_materialization"]
    assert verification["total_tested"] == 1
    assert len(verification["unverified_ids"]) == 1 - verification["verified_count"]
    text = json.dumps(summary, ensure_ascii=False)
    assert "000051794" not in text and "9 imágenes" not in text
    assert summary["homr_detection_failures"] == 0


def test_exp_05_counts_only_failures_of_the_entries_considered(tmp_path: Path) -> None:
    """Los fallos de `failures.json` ajenos a las entradas de la ejecución no cuentan (#139)."""
    from ml.experiments import exp_05_edit_derivation

    manifest, preds_dir = _piano_corpus(tmp_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["entries"].append({"id": "p2", "ground_truth": "mini/gt/p1.musicxml"})
    manifest.write_text(json.dumps(data), encoding="utf-8")
    (preds_dir / "failures.json").write_text(
        json.dumps([{"id": "p2", "error": "x"}, {"id": "ajena", "error": "y"}]), encoding="utf-8"
    )
    summary = exp_05_edit_derivation.run_derivation_experiment(manifest, preds_dir)
    assert summary["homr_detection_failures"] == 1
    assert summary["homr_detection_failures_treatment"].startswith("1 entradas no tienen")
    assert "(1 registradas" in summary["homr_detection_failures_treatment"]


def test_exp_06_validation_smb_custom_manifest(tmp_path: Path) -> None:
    from ml.experiments import exp_06_validation_metrics

    piano_xml = (
        REPO_ROOT / "packages" / "interchange" / "tests" / "fixtures" / "piano.musicxml"
    ).read_text(encoding="utf-8")

    smb_root = tmp_path / "smb"
    preds_dir = smb_root / "predictions"
    gt_dir = smb_root / "gt"
    preds_dir.mkdir(parents=True)
    gt_dir.mkdir(parents=True)

    (gt_dir / "piano_score.musicxml").write_text(piano_xml, encoding="utf-8")
    (preds_dir / "piano_score.musicxml").write_text(piano_xml, encoding="utf-8")

    manifest_file = tmp_path / "manifest.json"
    manifest_data = {
        "corpus": "smb",
        "entries": [
            {
                "id": "piano_score",
                "ground_truth": "smb/gt/piano_score.musicxml",
            }
        ],
    }
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    report = exp_06_validation_metrics.run_validation_experiment(
        manifest_path=manifest_file, predictions_dir=preds_dir
    )
    assert report.total_measures == 4
    assert report.global_metrics.accuracy == 1.0


def _exp_06_corpus(tmp_path: Path) -> tuple[Path, Path]:
    piano_xml = (
        REPO_ROOT / "packages" / "interchange" / "tests" / "fixtures" / "piano.musicxml"
    ).read_text(encoding="utf-8")
    root = tmp_path / "corpus"
    preds_dir = root / "primus" / "predictions"
    gt_dir = root / "primus" / "gt"
    preds_dir.mkdir(parents=True)
    gt_dir.mkdir(parents=True)
    (gt_dir / "p1.musicxml").write_text(piano_xml, encoding="utf-8")
    (preds_dir / "p1.musicxml").write_text(piano_xml, encoding="utf-8")
    manifest = root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {"corpus": "primus", "entries": [{"id": "p1", "ground_truth": "primus/gt/p1.musicxml"}]}
        ),
        encoding="utf-8",
    )
    return manifest, preds_dir


def test_exp_06_records_the_rules_version_with_every_figure(tmp_path: Path) -> None:
    """Cada cifra de `exp_06` dice de qué versión de las reglas es (ADR-0040 §15.6)."""
    import csv

    from cadenza.validation import RULES_CATALOG_VERSION, ValidationEngine

    from ml.experiments import exp_06_validation_metrics

    manifest, preds_dir = _exp_06_corpus(tmp_path)
    output = tmp_path / "out"
    exp_06_validation_metrics.run_validation_experiment(manifest, preds_dir, output_dir=output)
    rules_version = ValidationEngine().rules_version
    expected: dict[str, object] = {
        "rules_version": rules_version,
        "rules_catalog_version": RULES_CATALOG_VERSION,
    }
    summary = json.loads((output / "validation_metrics_summary.json").read_text("utf-8"))
    coverage = json.loads((output / "validation_error_coverage.json").read_text("utf-8"))
    for payload in (summary, coverage):
        assert {key: payload[key] for key in expected} == expected
    assert set(summary["metrics_by_rule"]) == set(rules_version.split(","))
    for name in ("validation_metrics_by_rule.csv", "validation_metrics_by_measure.csv"):
        rows = list(csv.DictReader((output / name).open(encoding="utf-8")))
        assert rows
        assert all(row["rules_version"] == rules_version for row in rows)
        assert all(row["rules_catalog_version"] == str(RULES_CATALOG_VERSION) for row in rows)
    # Nada en el `results/` del experimento: la salida va a `--output-dir`.
    assert not exp_06_validation_metrics.RESULTS_DIR.exists() or not any(
        exp_06_validation_metrics.RESULTS_DIR.iterdir()
    )


def test_exp_06_does_not_overwrite_a_measurement_of_another_rules_catalog(
    tmp_path: Path,
) -> None:
    """La medición nueva se documenta junto a la anterior: sin `rules_catalog_version`, el
    resumen es del catálogo 1 y no se sobrescribe (ADR-0040 §15.6)."""
    from ml.experiments import exp_06_validation_metrics

    manifest, preds_dir = _exp_06_corpus(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    previous = output / "validation_metrics_summary.json"
    previous.write_text(json.dumps({"experiment": "exp_06_validation_metrics"}), "utf-8")
    with pytest.raises(ValueError, match="catálogo de reglas 1"):
        exp_06_validation_metrics.run_validation_experiment(manifest, preds_dir, output_dir=output)
    assert json.loads(previous.read_text("utf-8")) == {"experiment": "exp_06_validation_metrics"}
    # Una medición de la misma versión sí se rehace.
    exp_06_validation_metrics.run_validation_experiment(manifest, preds_dir, output_dir=tmp_path)
    exp_06_validation_metrics.run_validation_experiment(manifest, preds_dir, output_dir=tmp_path)


def test_exp_10_effort_study_smoke(tmp_path: Path) -> None:
    from ml.experiments import exp_10_effort_study

    summary = exp_10_effort_study.run_effort_study_export(
        output_dir=tmp_path,
        smoke=True,
        seed=12345,
    )

    assert summary["protocol_version"] == "1.0"
    assert summary["total_sessions"] == 32
    assert summary["total_participants"] == 8
    assert "assisted" in summary["conditions"]
    assert "unassisted" in summary["conditions"]

    # Validar archivos generados
    assert (tmp_path / "effort_study_sessions.csv").is_file()
    assert (tmp_path / "effort_study_by_measure.csv").is_file()
    assert (tmp_path / "effort_study_summary.json").is_file()
    assert summary["simulated"] is True
    assert summary["data_source"] == "synthetic"
    assert "simulation_warning" in summary

    # El run_info de una exportación sintética también lo dice, y solo va a su carpeta.
    run_info = json.loads((tmp_path / "exp_10_run_info.json").read_text(encoding="utf-8"))
    assert run_info["simulated"] is True
    assert run_info["data_source"] == "synthetic"
    assert not (common.RESULTS_DIR / "exp_10_run_info.json").exists()


def test_exp_10_smoke_never_writes_into_results(tmp_path: Path) -> None:
    """Los datos sintéticos no van a `results/`, donde pasarían por el estudio (#271)."""
    from ml.experiments import exp_10_effort_study

    with pytest.raises(ValueError, match="results"):
        exp_10_effort_study.run_effort_study_export(smoke=True)
    with pytest.raises(ValueError, match="results"):
        exp_10_effort_study.run_effort_study_export(smoke=True, output_dir=common.RESULTS_DIR)
    assert not list(common.RESULTS_DIR.glob("effort_study_*"))


def test_exp_10_smoke_refuses_any_path_into_the_repository_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """También `results` relativo y sus subcarpetas: el del repositorio, no solo el en uso."""
    from ml.experiments import exp_10_effort_study

    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(exp_10_effort_study, "REPO_ROOT", repo)
    monkeypatch.chdir(repo)

    for output_dir in ("results", "./results/sub", repo / "results" / "x"):
        with pytest.raises(ValueError, match="results"):
            exp_10_effort_study.run_effort_study_export(smoke=True, output_dir=output_dir)
    assert not (repo / "results").exists()


def test_exp_10_without_database_fails(tmp_path: Path) -> None:
    """Sin `--db-url` ni `--smoke` no hay estudio que exportar ni datos de reserva (#271)."""
    from ml.experiments import exp_10_effort_study

    with pytest.raises(ValueError, match="--db-url"):
        exp_10_effort_study.run_effort_study_export(output_dir=tmp_path / "out")
    assert not (tmp_path / "out" / "effort_study_summary.json").exists()


def test_exp_10_empty_database_fails_instead_of_inventing_sessions(tmp_path: Path) -> None:
    """Una base sin sesiones de estudio no se rellena con datos sintéticos (#96, #271)."""
    from ml.experiments import exp_10_effort_study

    with pytest.raises(ValueError, match="sesiones"):
        exp_10_effort_study.run_effort_study_export(
            db_url=f"sqlite+pysqlite:///{(tmp_path / 'empty.db').as_posix()}",
            output_dir=tmp_path / "out",
        )
    assert not (tmp_path / "out" / "effort_study_summary.json").exists()


def _exp_10_document(session_id: str, score: Any | None = None) -> dict[str, Any]:
    """El documento del doble de OMR (dos compases de un pentagrama), o con otra partitura."""
    from dataclasses import replace

    from cadenza.omr.testing import FakeOMREngine

    document = FakeOMREngine(document_id=f"d-{session_id}").transcribe(Path("x.png"))
    if score is not None:
        document = replace(document, score=score)
    primitive: dict[str, Any] = document.to_primitive()
    return primitive


def _exp_10_session(
    db: Any,
    session_id: str,
    owner: str,
    *,
    status: str = "finalized",
    self_registered: bool = False,
    role: str = "transcriptor",
    test_score_id: str | None = "TS-01",
    condition: str = "assisted",
    score: Any | None = None,
) -> None:
    from cadenza.persistence import Session as SessionRecord
    from cadenza.persistence import UserRecord

    if db.get(UserRecord, owner) is None:
        db.add(
            UserRecord(
                id=owner,
                username=owner,
                password_hash="hash",
                role=role,
                self_registered=self_registered,
            )
        )
    db.add(
        SessionRecord(
            id=session_id,
            owner_id=owner,
            document_id=f"d-{session_id}",
            omr_engine="homr",
            document=_exp_10_document(session_id, score),
            status=status,
            condition=condition,
            test_score_id=test_score_id,
        )
    )


def _exp_10_effort(db: Any, session_id: str, record_id: str, **values: Any) -> None:
    from cadenza.persistence import EffortMetricsRecord

    db.add(
        EffortMetricsRecord(
            id=record_id,
            session_id=session_id,
            duration_ms=values.pop("duration_ms", 1000),
            interventions=values.pop("interventions", {}),
            **values,
        )
    )


def _exp_10_db() -> Any:
    from cadenza.persistence import create_memory_engine, create_schema, create_session_factory

    engine = create_memory_engine()
    create_schema(engine)
    return create_session_factory(engine)()


def test_exp_10_excludes_self_registered_accounts() -> None:
    """Las sesiones de cuentas del registro público no entran en el estudio (ADR-0022, #154)."""
    from ml.experiments import exp_10_effort_study

    with _exp_10_db() as db:
        for user_id, self_registered in (("estudio", False), ("publico", True)):
            _exp_10_session(db, f"s-{user_id}", user_id, self_registered=self_registered)
            _exp_10_effort(db, f"s-{user_id}", f"e-{user_id}")
        db.commit()

        sessions, _measures = exp_10_effort_study.extract_study_data_from_db(db)

    assert [row.session_id for row in sessions] == ["s-estudio"]


def test_exp_10_only_counts_finalized_and_measured_sessions() -> None:
    """Una partitura sin finalizar no entra en el análisis, y una finalizada sin registro de
    esfuerzo no se midió: no entra, pero el resumen la nombra (protocolo §3.4, ADR-0050)."""
    from ml.experiments import exp_10_effort_study

    with _exp_10_db() as db:
        _exp_10_session(db, "s-abierta", "p01", status="correcting")
        _exp_10_effort(db, "s-abierta", "e-abierta")
        _exp_10_session(db, "s-sin-medir", "p01")
        _exp_10_session(db, "s-medida", "p01")
        _exp_10_effort(db, "s-medida", "e-medida")
        db.commit()

        sessions, _measures = exp_10_effort_study.extract_study_data_from_db(db)
        unmeasured = exp_10_effort_study.finalized_sessions_without_effort(db)

    assert [row.session_id for row in sessions] == ["s-medida"]
    assert unmeasured == ["s-sin-medir"]


def test_exp_10_an_accumulated_record_without_segments_is_not_a_measurement() -> None:
    """Un descarte crea el registro acumulado aunque no llegara ningún tramo de tiempo: sin
    tramos no hay medición, y si hay un registro suelto se usa ese (ADR-0050)."""
    from ml.experiments import exp_10_effort_study

    with _exp_10_db() as db:
        _exp_10_session(db, "s-sin-tramos", "p01")
        _exp_10_effort(
            db, "s-sin-tramos", "a1", duration_ms=0, accumulated=True, findings_dismissed=1
        )
        _exp_10_session(db, "s-suelto", "p01")
        _exp_10_effort(db, "s-suelto", "a2", duration_ms=0, accumulated=True)
        _exp_10_effort(db, "s-suelto", "suelto", duration_ms=7_000)
        db.commit()

        sessions, _measures = exp_10_effort_study.extract_study_data_from_db(db)
        unmeasured = exp_10_effort_study.finalized_sessions_without_effort(db)

    assert [(row.session_id, row.duration_ms) for row in sessions] == [("s-suelto", 7_000)]
    assert sessions[0].findings_dismissed is None
    assert unmeasured == ["s-sin-tramos"]


def test_exp_10_reads_the_accumulated_record_of_the_web() -> None:
    """El registro que acumula la web es el de la sesión aunque haya otro suelto más nuevo, y
    trae las intervenciones por clase y lo que se cuenta aparte (#188, ADR-0050)."""
    from datetime import UTC, datetime

    from ml.experiments import exp_10_effort_study

    with _exp_10_db() as db:
        _exp_10_session(db, "s-1", "p01")
        _exp_10_effort(
            db,
            "s-1",
            "acumulado",
            duration_ms=90_000,
            time_to_first_edit_ms=12_000,
            interventions={"1": 3, "2": 1},
            created_at=datetime(2026, 11, 1, tzinfo=UTC),
            accumulated=True,
            segments=[{"id": "tab-a", "active_ms": 90_000, "first_edit_ms": 12_000}],
            interventions_by_class={"content": {"1": 2}, "mark": {"2": 1}, "meter": {"1": 1}},
            findings_dismissed=2,
            findings_restored=1,
            suggestions_applied=1,
            suggestions_rejected=3,
        )
        _exp_10_effort(
            db,
            "s-1",
            "suelto",
            duration_ms=5,
            created_at=datetime(2026, 11, 2, tzinfo=UTC),
        )
        db.commit()

        (row,), measures = exp_10_effort_study.extract_study_data_from_db(db)

    assert (row.duration_ms, row.time_to_first_edit_ms) == (90_000, 12_000)
    assert row.total_interventions == 4
    assert (row.content_interventions, row.mark_interventions, row.meter_interventions) == (
        2,
        1,
        1,
    )
    assert (row.findings_dismissed, row.findings_restored) == (2, 1)
    assert (row.suggestions_applied, row.suggestions_rejected) == (1, 3)
    assert sorted((m.measure_number, m.interventions_count) for m in measures) == [(1, 3), (2, 1)]


_TLX = ("mental", "physical", "temporal", "performance", "effort", "frustration")


def _fake_score() -> Any:
    from cadenza.omr.testing import FakeOMREngine

    return FakeOMREngine().transcribe(Path("x.png")).score


def _with_pitch(score: Any, measure: int, index: int, pitch: str) -> Any:
    """La partitura con otra altura en un evento del primer pentagrama."""
    from dataclasses import replace

    part = score.parts[0]
    staff = part.staves[0]
    measures = list(staff.measures)
    events = list(measures[measure].events)
    events[index] = replace(events[index], pitch=pitch)
    measures[measure] = replace(measures[measure], events=tuple(events))
    staff = replace(staff, measures=tuple(measures))
    return replace(score, parts=(replace(part, staves=(staff,)), *score.parts[1:]))


def test_exp_10_only_exports_the_evaluated_scores_of_study_transcribers() -> None:
    """Ni el calentamiento, ni una sesión sin partitura de prueba, ni las pruebas de una cuenta
    de investigador entran en el estudio (#250, protocolo §2.3)."""
    from ml.experiments import exp_10_effort_study

    with _exp_10_db() as db:
        _exp_10_session(db, "s-ts02", "P01", test_score_id="TS-02", condition="unassisted")
        _exp_10_session(db, "s-calentamiento", "P01", test_score_id="calentamiento")
        _exp_10_session(db, "s-libre", "P01", test_score_id=None)
        _exp_10_session(db, "s-investigador", "inv", role="investigador")
        for session_id in ("s-ts02", "s-calentamiento", "s-libre", "s-investigador"):
            _exp_10_effort(db, session_id, f"e-{session_id}")
        db.commit()

        sessions, _measures = exp_10_effort_study.extract_study_data_from_db(db)
        unmeasured = exp_10_effort_study.finalized_sessions_without_effort(db)

    assert [(row.session_id, row.block) for row in sessions] == [("s-ts02", 2)]
    assert unmeasured == []


def test_exp_10_counts_the_measures_of_the_whole_score() -> None:
    """Los compases son los del pentagrama que más tiene en toda la partitura, no los del
    primero de la primera parte (#250)."""
    from dataclasses import replace

    from ml.experiments import exp_10_effort_study

    score = _fake_score()
    part = score.parts[0]
    staff = part.staves[0]
    longer = replace(part, staves=(replace(staff, measures=staff.measures * 3),))
    with _exp_10_db() as db:
        _exp_10_session(db, "s-1", "P01", score=replace(score, parts=(part, longer)))
        _exp_10_effort(db, "s-1", "e-1", duration_ms=12_000, interventions={"1": 3})
        db.commit()

        (row,), _measures = exp_10_effort_study.extract_study_data_from_db(db)

    assert len(staff.measures) == 2
    assert row.total_measures == 6
    assert (row.time_per_measure_s, row.interventions_per_measure) == (2.0, 0.5)


def _write_tlx(path: Path, rows: list[dict[str, Any]]) -> Path:
    import csv

    columns = ["participant_id", "block", *_TLX, *[f"weight_{scale}" for scale in _TLX]]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def _tlx_row(participant: str, block: int, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"participant_id": participant, "block": block}
    row.update(dict(zip(_TLX, (60, 10, 40, 30, 50, 20), strict=True)))
    row.update(extra)
    return row


def test_exp_10_joins_the_nasa_tlx_by_participant_and_block(tmp_path: Path) -> None:
    """El NASA-TLX se une por participante y por el bloque que da la matriz; sin dato, las
    celdas quedan vacías, nunca a 0 (#250, protocolo §3.3)."""
    from ml.experiments import exp_10_effort_study

    weights = dict(zip([f"weight_{scale}" for scale in _TLX], (5, 0, 3, 2, 4, 1), strict=True))
    csv_path = _write_tlx(tmp_path / "tlx.csv", [_tlx_row("P03", 1, **weights)])
    tlx = exp_10_effort_study.load_nasa_tlx(csv_path)
    with _exp_10_db() as db:
        # P03: bloque 1, TS-02 asistida; bloque 2, TS-01 no asistida (protocolo §2.4).
        _exp_10_session(db, "s-b1", "P03", test_score_id="TS-02")
        _exp_10_session(db, "s-b2", "P03", test_score_id="TS-01", condition="unassisted")
        _exp_10_effort(db, "s-b1", "e-b1")
        _exp_10_effort(db, "s-b2", "e-b2")
        db.commit()

        rows, _measures = exp_10_effort_study.extract_study_data_from_db(db, nasa_tlx=tlx)

    by_block = {row.block: row for row in rows}
    first, second = by_block[1], by_block[2]
    assert (first.nasa_tlx_mental, first.nasa_tlx_frustration) == (60.0, 20.0)
    assert first.nasa_tlx_raw == 35.0
    # (60·5 + 10·0 + 40·3 + 30·2 + 50·4 + 20·1) / 15
    assert first.nasa_tlx_weighted == 46.67
    assert second.nasa_tlx_mental is None
    assert (second.nasa_tlx_raw, second.nasa_tlx_weighted) == (None, None)

    summary = exp_10_effort_study.compute_summary_statistics(rows)
    assert summary["conditions"]["assisted"]["mean_nasa_tlx_raw"] == 35.0
    assert summary["conditions"]["unassisted"]["mean_nasa_tlx_raw"] is None
    assert summary["effort_reduction"]["cognitive_workload_reduction_percent"] is None


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([_tlx_row("P01", 1, mental=120)], "entre 0 y 100"),
        ([_tlx_row("P01", 1, effort="")], "no es un número"),
        ([_tlx_row("P01", 1), _tlx_row("P01", 1)], "repetido"),
        ([_tlx_row("P01", 5)], "bloque"),
        ([_tlx_row("P01", 1, weight_mental=15, weight_effort=0)], "todos o ninguno"),
        (
            [
                _tlx_row(
                    "P01",
                    1,
                    **dict(zip([f"weight_{s}" for s in _TLX], (10, 1, 1, 1, 1, 1), strict=True)),
                )
            ],
            "de 0 a 5",
        ),
        (
            [
                _tlx_row(
                    "P01",
                    1,
                    **dict(zip([f"weight_{s}" for s in _TLX], (5, 0, 3, 2, 4, 0), strict=True)),
                )
            ],
            "suman 14",
        ),
    ],
)
def test_exp_10_rejects_an_invalid_nasa_tlx(
    tmp_path: Path, rows: list[dict[str, Any]], message: str
) -> None:
    from ml.experiments import exp_10_effort_study

    with pytest.raises(ValueError, match=message):
        exp_10_effort_study.load_nasa_tlx(_write_tlx(tmp_path / "tlx.csv", rows))


def test_exp_10_ser_does_not_depend_on_voice_numbers_or_chord_order() -> None:
    """Dos voces numeradas al revés y un acorde escrito en otro orden se ven igual: la SER
    normalizada no los cuenta como errores (protocolo §2.3, riesgos; #250)."""
    from dataclasses import replace
    from fractions import Fraction

    from cadenza.domain import Event, EventKind
    from cadenza.learning import score_ser_pair

    from ml.experiments import exp_10_effort_study

    def note(pitch: str, voice: int, chord: bool = False) -> Event:
        return Event(
            kind=EventKind.NOTE,
            voice=voice,
            pitch=pitch,
            duration_beats=Fraction(2),
            is_chord=chord,
        )

    score = _fake_score()
    part = score.parts[0]
    staff = part.staves[0]

    def with_events(events: tuple[Event, ...]) -> Any:
        measure = replace(staff.measures[0], events=events)
        new_staff = replace(staff, measures=(measure,))
        return replace(score, parts=(replace(part, staves=(new_staff,)),))

    truth = with_events(
        (note("C4", 0), note("E4", 0, True), note("D4", 0), note("G3", 1), note("A3", 1))
    )
    final = with_events(
        (note("G3", 0), note("A3", 0), note("E4", 1), note("C4", 1, True), note("D4", 1))
    )

    assert score_ser_pair(truth, final).ser > 0
    normalized = score_ser_pair(
        exp_10_effort_study.ser_normalized(truth), exp_10_effort_study.ser_normalized(final)
    )
    assert normalized.ser == 0.0


def test_exp_10_measures_the_residual_fidelity_of_the_final_state() -> None:
    """La fidelidad residual compara el estado final (el documento con el log aplicado) con la
    verdad: una corrección que deja la partitura como la verdad da SER y OMR-NED 0 (#250)."""
    from datetime import UTC, datetime

    from cadenza.persistence import EditEventRecord

    from ml.experiments import exp_10_effort_study

    score = _fake_score()
    truth = _with_pitch(score, 1, 0, "F4")
    staff = score.parts[0].staves[0]
    with _exp_10_db() as db:
        _exp_10_session(db, "s-corregida", "P01")
        _exp_10_session(db, "s-sin-corregir", "P02", condition="unassisted")
        db.add(
            EditEventRecord(
                id="ed-1",
                session_id="s-corregida",
                seq=1,
                op="SetPitch",
                author="P01",
                anchor={
                    "part": 0,
                    "staff": 0,
                    "measure": staff.measures[1].number,
                    "voice": 0,
                    "event_index": 0,
                    "staff_id": staff.id,
                },
                before={"pitch": "E4"},
                after={"pitch": "F4"},
                created_at=datetime(2026, 11, 9, tzinfo=UTC),
            )
        )
        _exp_10_effort(db, "s-corregida", "e-1")
        _exp_10_effort(db, "s-sin-corregir", "e-2")
        db.commit()

        rows, _measures = exp_10_effort_study.extract_study_data_from_db(
            db, truths={"TS-01": truth}
        )

    by_session = {row.session_id: row for row in rows}
    fixed, unfixed = by_session["s-corregida"], by_session["s-sin-corregir"]
    assert (fixed.residual_ser, fixed.residual_omr_ned, fixed.residual_omr_ned_error) == (
        0.0,
        0.0,
        "",
    )
    assert unfixed.residual_ser is not None and unfixed.residual_ser > 0
    assert unfixed.residual_omr_ned is not None and unfixed.residual_omr_ned > 0
    assert fixed.edits_count == 1


def _exp_10_db_file(tmp_path: Path) -> str:
    from cadenza.persistence import create_engine_for_url, create_schema, create_session_factory

    url = f"sqlite+pysqlite:///{(tmp_path / 'estudio.db').as_posix()}"
    engine = create_engine_for_url(url)
    create_schema(engine)
    with create_session_factory(engine)() as db:
        # P01: bloque 1, TS-01 asistida (protocolo §2.4).
        _exp_10_session(db, "s-1", "P01")
        _exp_10_effort(db, "s-1", "e-1", duration_ms=8_000)
        db.commit()
    return url


def test_exp_10_export_without_the_study_bank_fails_clearly(tmp_path: Path) -> None:
    """Sin la verdad del banco no hay fidelidad residual: falla y dice cómo regenerarlo
    (`CLAUDE.md` §8.1, #250)."""
    from ml.experiments import exp_10_effort_study

    with pytest.raises(ValueError, match="build_study_bank"):
        exp_10_effort_study.run_effort_study_export(
            db_url=_exp_10_db_file(tmp_path),
            output_dir=tmp_path / "out",
            bank_dir=tmp_path / "sin-banco",
        )
    assert not (tmp_path / "out").exists()


def test_exp_10_export_with_the_bank_and_the_nasa_tlx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """De punta a punta: la verdad del banco (comprobada con su sha256), el NASA-TLX unido y lo
    que no cuadra, nombrado en el resumen (#250)."""
    import copy
    import csv
    import hashlib

    from cadenza.interchange import Music21ScoreExporter

    from ml.experiments import exp_10_effort_study

    manifest = copy.deepcopy(exp_10_effort_study.load_study_manifest())
    bank = tmp_path / "banco"
    bank.mkdir()
    xml = Music21ScoreExporter().to_musicxml(_fake_score()).encode("utf-8")
    for entry in manifest["partituras"]:
        (bank / entry["salida"]["verdad"]).write_bytes(xml)
        entry["sha256"]["verdad"] = hashlib.sha256(xml).hexdigest()
    monkeypatch.setattr(exp_10_effort_study, "load_study_manifest", lambda: manifest)
    tlx = _write_tlx(tmp_path / "tlx.csv", [_tlx_row("P01", 1), _tlx_row("P05", 2)])
    out = tmp_path / "out"

    db_url = _exp_10_db_file(tmp_path)
    from cadenza.persistence import create_engine_for_url, create_session_factory

    with create_session_factory(create_engine_for_url(db_url))() as db:
        # Una cuenta de prueba que no está en la matriz: va en las filas, no en las medias.
        _exp_10_session(db, "s-piloto", "piloto", test_score_id="TS-02")
        _exp_10_effort(db, "s-piloto", "e-piloto", duration_ms=99_000)
        db.commit()

    summary = exp_10_effort_study.run_effort_study_export(
        db_url=db_url, output_dir=out, bank_dir=bank, nasa_tlx_csv=tlx
    )

    with (out / "effort_study_sessions.csv").open(encoding="utf-8") as handle:
        rows = {row["participant_id"]: row for row in csv.DictReader(handle)}
    row = rows["P01"]
    assert (row["block"], row["test_score_id"]) == ("1", "TS-01")
    assert (row["residual_ser"], row["residual_omr_ned"]) == ("0.0", "0.0")
    assert (row["nasa_tlx_raw"], row["nasa_tlx_weighted"]) == ("35.0", "")
    assert rows["piloto"]["block"] == ""
    assert summary["nasa_tlx_rows_without_session"] == ["P05#2"]
    assert summary["sessions_outside_matrix"] == ["s-piloto"]
    assert summary["sessions_with_condition_not_in_matrix"] == []
    assert summary["duplicate_participant_blocks"] == []
    assert summary["total_sessions"] == 1
    assert summary["conditions"]["assisted"]["mean_duration_s"] == 8.0
    assert summary["conditions"]["assisted"]["mean_residual_ser"] == 0.0
    assert summary["conditions"]["unassisted"]["sessions_count"] == 0
    assert summary["conditions"]["unassisted"]["mean_duration_s"] is None
    assert summary["simulated"] is False
    # Fuera del repositorio solo queda el nombre: nada de rutas con el usuario de la máquina.
    assert summary["bank_dir"] == "banco"
    assert summary["nasa_tlx_csv"] == "tlx.csv"


def test_exp_10_ser_counts_a_lost_natural_under_the_key_signature() -> None:
    """Las alturas del `ScoreIR` son las que suenan: en mi bemol mayor, un La becuadro de la
    verdad (`A4`) leído como La bemol (`Ab4`) es un error, aunque la armadura ya lo bemolice
    (como `exp_14`, #250)."""
    from dataclasses import replace

    from cadenza.domain import KeySignature

    from ml.experiments import exp_10_effort_study

    score = _fake_score()
    part = score.parts[0]
    staff = part.staves[0]
    measures = (replace(staff.measures[0], key_signature=KeySignature(fifths=-3)),)
    flat_key = replace(score, parts=(replace(part, staves=(replace(staff, measures=measures),)),))
    truth = _with_pitch(flat_key, 0, 0, "A4")
    final = _with_pitch(flat_key, 0, 0, "Ab4")

    ser, _omr_ned, _error = exp_10_effort_study.residual_fidelity(final, truth)

    assert ser > 0


def test_exp_10_an_unreadable_pair_leaves_the_omr_ned_empty_and_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si musicdiff no lee un par, la celda del OMR-NED queda vacía, con su error, y el resumen
    nombra la sesión; sin musicdiff, la exportación falla con un mensaje claro (#250)."""
    from cadenza.learning import MetricsExtraMissing

    from ml.experiments import exp_10_effort_study

    def unreadable(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("par ilegible")

    monkeypatch.setattr(exp_10_effort_study, "omr_ned_pair", unreadable)
    with _exp_10_db() as db:
        _exp_10_session(db, "s-1", "P01")
        _exp_10_effort(db, "s-1", "e-1")
        db.commit()
        rows, _measures = exp_10_effort_study.extract_study_data_from_db(
            db, truths={"TS-01": _fake_score()}
        )

    assert (rows[0].residual_ser, rows[0].residual_omr_ned) == (0.0, None)
    assert rows[0].residual_omr_ned_error == "RuntimeError: par ilegible"
    checks = exp_10_effort_study._matrix_checks(
        rows, exp_10_effort_study.study_assignments(exp_10_effort_study.load_study_manifest()), None
    )
    assert checks["residual_omr_ned_errors"] == ["s-1"]

    def missing(*_args: Any, **_kwargs: Any) -> Any:
        raise MetricsExtraMissing("falta musicdiff")

    monkeypatch.setattr(exp_10_effort_study, "omr_ned_pair", missing)
    with pytest.raises(ValueError, match="musicdiff"):
        exp_10_effort_study.residual_fidelity(_fake_score(), _fake_score())


def test_exp_10_names_what_does_not_match_the_matrix() -> None:
    """Una condición distinta de la de la matriz y dos sesiones del mismo participante y bloque
    se nombran en el resumen (#250)."""
    from ml.experiments import exp_10_effort_study

    with _exp_10_db() as db:
        # P01 hace TS-02 sin asistencia (bloque 2); P02, TS-01 sin asistencia (bloque 1).
        _exp_10_session(db, "s-otra-condicion", "P01", test_score_id="TS-02")
        _exp_10_session(db, "s-a", "P02", condition="unassisted")
        _exp_10_session(db, "s-b", "P02", condition="unassisted")
        for session_id in ("s-otra-condicion", "s-a", "s-b"):
            _exp_10_effort(db, session_id, f"e-{session_id}")
        db.commit()
        rows, _measures = exp_10_effort_study.extract_study_data_from_db(db)

    checks = exp_10_effort_study._matrix_checks(
        rows, exp_10_effort_study.study_assignments(exp_10_effort_study.load_study_manifest()), None
    )
    assert checks["sessions_with_condition_not_in_matrix"] == ["s-otra-condicion"]
    assert checks["duplicate_participant_blocks"] == ["P02#1"]


def test_ml_cli_export_effort_passes_the_bank_and_the_nasa_tlx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ml import cli
    from ml.experiments import exp_10_effort_study

    received: dict[str, Any] = {}

    def fake_export(**kwargs: Any) -> dict[str, Any]:
        received.update(kwargs)
        return {}

    monkeypatch.setattr(exp_10_effort_study, "run_effort_study_export", fake_export)

    code = cli.main(
        [
            "export-effort",
            "--db-url",
            "sqlite+pysqlite:///estudio.db",
            "--bank-dir",
            "banco_estudio",
            "--nasa-tlx",
            "nasa_tlx.csv",
            "--output-dir",
            "fuera",
        ]
    )

    assert code == 0
    assert (received["bank_dir"], received["nasa_tlx_csv"]) == ("banco_estudio", "nasa_tlx.csv")


def test_ml_cli_export_effort(tmp_path: Path) -> None:
    from ml import cli

    code = cli.main(["export-effort", "--smoke", "--output-dir", str(tmp_path), "--seed", "999"])
    assert code == 0
    assert (tmp_path / "effort_study_sessions.csv").is_file()
    assert (tmp_path / "effort_study_summary.json").is_file()


def test_ml_cli_export_effort_smoke_refuses_results(capsys: pytest.CaptureFixture[str]) -> None:
    """Con la carpeta por defecto (`results`), `--smoke` falla con un mensaje claro (#271)."""
    from ml import cli

    assert cli.main(["export-effort", "--smoke"]) == 1
    assert "results" in capsys.readouterr().err


def test_exp_02_coverage_counts_only_content_ops() -> None:
    """La cobertura de operaciones es sobre las siete de contenido: añadir las de marcas a
    `EditOp` no cambia las cifras de exp_02 (ADR-0039)."""
    pool = _test_pool(size=exp_02_active_learning.CANONICAL_BUDGET * 3)
    res = exp_02_active_learning._evaluate_pool(pool, seed=42, manifest_path=None)
    coverages = [e["op_coverage_ratio"] for e in res["canonical_evaluations"].values()]
    assert max(coverages) == 1.0
    assert all(0.0 < coverage <= 1.0 for coverage in coverages)
