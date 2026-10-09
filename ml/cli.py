"""CLI de orquestación de jobs offline de aprendizaje activo (ADR-0008, §3.2, §6.5, #22).

Comandos implementados:
  - build-dataset : extrae muestras de la base de datos y calcula el dataset_hash canónico.
  - select        : aplica una AcquisitionStrategy (hybrid, uncertainty, diversity, etc.).
  - train         : ajusta el modelo (FakeTrainer/Trainer) y guarda los pesos en ArtifactStore.
  - evaluate      : evalúa las métricas simbólicas (SER, OMR-NED) contra el umbral de promoción.
  - promote       : registra y activa la versión en el ModelRegistry persistente.
  - run           : ejecuta el pipeline completo de punta a punta de forma encadenada.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cadenza.application import (
    EvaluationMetrics,
    ModelVersionData,
    PromotionRejected,
    PromotionThreshold,
)
from cadenza.learning import (
    AcquisitionStrategy,
    DiversityAcquisition,
    ErrorDensityAcquisition,
    HybridAcquisition,
    JobConfig,
    RandomAcquisition,
    RepositoryDatasetReader,
    TrainingSample,
    create_trainer,
    dataset_hash,
    deserialize_dataset,
    load_job_config,
    serialize_dataset,
)
from cadenza.persistence import (
    ArtifactRecord,
    FilesystemArtifactStore,
    SqlAlchemyEditEventRepository,
    SqlAlchemyModelRegistry,
    SqlAlchemySessionRepository,
    create_engine_for_url,
    create_schema,
    create_session_factory,
    session_scope,
)


def _default_db_url() -> str:
    return os.environ.get("CADENZA_DATABASE_URL", "sqlite:///cadenza.db")


def _resolve_strategy(name: str, seed: int = 42) -> AcquisitionStrategy:
    canonical = name.strip().lower()
    if canonical == "hybrid":
        return HybridAcquisition()
    if canonical in ("uncertainty", "error_density"):
        return ErrorDensityAcquisition()
    if canonical == "diversity":
        return DiversityAcquisition()
    if canonical == "random":
        return RandomAcquisition(seed=seed)
    msg = (
        f"Estrategia desconocida: '{name}'. "
        "Opciones: hybrid, uncertainty, diversity, error_density, random"
    )
    raise ValueError(msg)


# =============================================================================
# COMANDO 1: build-dataset
# =============================================================================


def build_dataset_command(args: argparse.Namespace) -> int:
    config_path = Path(args.config) if args.config else Path("configs/learning/default.json")
    config: JobConfig | None = None
    cfg_hash: str = "none"
    seed: int = 42

    if config_path.is_file():
        config = load_job_config(config_path)
        cfg_hash = config.config_hash
        seed = config.seed

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    db_url = args.db_url or _default_db_url()
    engine = create_engine_for_url(db_url)
    create_schema(engine)
    factory = create_session_factory(engine)

    with session_scope(factory) as db:
        session_repo = SqlAlchemySessionRepository(db)
        edit_repo = SqlAlchemyEditEventRepository(db)
        reader = RepositoryDatasetReader()

        samples = reader.read_dataset(
            session_repository=session_repo,
            edit_event_repository=edit_repo,
            status=args.status,
            owner_id=args.owner_id,
        )

    serialized = serialize_dataset(samples)
    serialized["config_hash"] = cfg_hash
    serialized["seed"] = seed
    serialized["status_filter"] = args.status
    serialized["created_at"] = datetime.datetime.now(datetime.UTC).isoformat()

    output_path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
    d_hash = str(serialized["dataset_hash"])
    count = int(serialized["count"])

    print("[build-dataset] Extracción completada exitosamente.")
    print(f"  Muestras extraídas : {count}")
    print(f"  dataset_hash       : {d_hash}")
    print(f"  config_hash        : {cfg_hash}")
    print(f"  Archivo de salida  : {output_path}")
    return 0


# =============================================================================
# COMANDO 2: select
# =============================================================================


def select_command(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"Error: No se encontró el dataset en '{input_path}'", file=sys.stderr)
        return 1

    config_path = Path(args.config) if args.config else Path("configs/learning/default.json")
    config: JobConfig | None = None
    if config_path.is_file():
        config = load_job_config(config_path)

    raw_input = json.loads(input_path.read_text(encoding="utf-8"))
    samples = deserialize_dataset(raw_input)
    source_d_hash = str(raw_input.get("dataset_hash", dataset_hash(samples)))

    strategy_name = args.strategy or (config.strategy if config else "hybrid")
    budget = int(args.budget if args.budget is not None else (config.budget if config else 10))
    seed = int(args.seed if args.seed is not None else (config.seed if config else 42))

    if strategy_name.lower() == "random":
        strategy: AcquisitionStrategy = RandomAcquisition(seed=seed)
    else:
        strategy = _resolve_strategy(strategy_name, seed=seed)

    selected_samples = strategy.select(samples, budget=budget)
    selected_hash = dataset_hash(selected_samples)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result_payload: dict[str, Any] = {
        "dataset_hash": selected_hash,
        "source_dataset_hash": source_d_hash,
        "strategy": strategy.strategy_id,
        "budget": budget,
        "seed": seed,
        "config_hash": config.config_hash if config else raw_input.get("config_hash", "none"),
        "count": len(selected_samples),
        "selected_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "samples": [s.to_primitive() for s in sorted(selected_samples, key=TrainingSample.key)],
    }

    output_path.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")

    print(f"[select] Selección de muestras completada ({strategy.strategy_id}).")
    print(f"  Muestras totales   : {len(samples)}")
    print(f"  Muestras elegidas  : {len(selected_samples)} (presupuesto: {budget})")
    print(f"  dataset_hash lote  : {selected_hash}")
    print(f"  Archivo de salida  : {output_path}")
    return 0


# =============================================================================
# COMANDO 3: train
# =============================================================================


def train_command(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"Error: No se encontró el archivo de muestras en '{input_path}'", file=sys.stderr)
        return 1

    config_path = Path(args.config) if args.config else Path("configs/learning/default.json")
    if not config_path.is_file():
        print(f"Error: No se encontró la configuración en '{config_path}'", file=sys.stderr)
        return 1

    config = load_job_config(config_path)
    raw_input = json.loads(input_path.read_text(encoding="utf-8"))
    samples = deserialize_dataset(raw_input)
    d_hash = str(raw_input.get("dataset_hash", dataset_hash(samples)))

    # Métricas simuladas si se configuran o default
    ser_override = float(args.ser) if args.ser is not None else None
    omr_ned_override = float(args.omr_ned) if args.omr_ned is not None else None

    trainer_metrics = None
    if ser_override is not None and omr_ned_override is not None:
        trainer_metrics = EvaluationMetrics(ser=ser_override, omr_ned=omr_ned_override)

    trainer_backend = getattr(args, "trainer", "auto")
    trainer = create_trainer(backend=trainer_backend, metrics=trainer_metrics)
    trained_artifact = trainer.train(samples, config.to_training_config())

    # Persistir los pesos binarios en el ArtifactStore
    artifacts_dir = Path(args.artifacts_dir)
    db_url = args.db_url or _default_db_url()
    engine = create_engine_for_url(db_url)
    create_schema(engine)
    factory = create_session_factory(engine)

    with session_scope(factory) as db:
        store = FilesystemArtifactStore(artifacts_dir, session=db)
        if trained_artifact.weights_binary is not None:
            weight_payload = trained_artifact.weights_binary
        else:
            weight_payload = (
                b"ONNX_WEIGHTS_VERSION_1\n"
                + f"artifact_hash={trained_artifact.artifact_hash}\n".encode()
                + f"dataset_hash={d_hash}\n".encode()
                + f"config_hash={config.config_hash}\n".encode()
                + f"seed={config.seed}\n".encode()
            )
        stored_artifact_hash = store.put(
            weight_payload, kind="model", media_type="application/octet-stream"
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result_data = {
        "artifact_hash": stored_artifact_hash,
        "dataset_hash": d_hash,
        "config_hash": config.config_hash,
        "seed": config.seed,
        "epochs": config.epochs,
        "learning_rate": config.learning_rate,
        "trainer": trainer.__class__.__name__,
        "metrics": {
            "ser": trained_artifact.metrics.ser,
            "omr_ned": trained_artifact.metrics.omr_ned,
        },
        "samples_count": len(samples),
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
    }

    output_path.write_text(json.dumps(result_data, indent=2), encoding="utf-8")

    print(f"[train] Entrenamiento finalizado exitosamente ({trainer.__class__.__name__}).")
    print(f"  artifact_hash (pesos): {stored_artifact_hash}")
    print(f"  dataset_hash         : {d_hash}")
    print(f"  config_hash          : {config.config_hash}")
    print(f"  SER                  : {trained_artifact.metrics.ser:.4f}")
    print(f"  OMR-NED              : {trained_artifact.metrics.omr_ned:.4f}")
    print(f"  Metadatos guardados  : {output_path}")
    return 0


# =============================================================================
# COMANDO 4: evaluate
# =============================================================================


def evaluate_command(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"Error: No se encontró el artefacto en '{input_path}'", file=sys.stderr)
        return 1

    config_path = Path(args.config) if args.config else Path("configs/learning/default.json")
    if not config_path.is_file():
        print(f"Error: No se encontró la configuración en '{config_path}'", file=sys.stderr)
        return 1

    config = load_job_config(config_path)
    artifact_data = json.loads(input_path.read_text(encoding="utf-8"))

    raw_metrics = artifact_data.get("metrics", {})
    ser = float(args.ser if args.ser is not None else raw_metrics.get("ser", 0.1))
    omr_ned = float(args.omr_ned if args.omr_ned is not None else raw_metrics.get("omr_ned", 0.08))

    # Si se especifica un manifest de evaluación, computar métricas empíricas reales
    if getattr(args, "manifest", None) and Path(args.manifest).is_file():
        from ml.experiments.exp_03_omr_quality import run as run_exp_03

        manifest_path = Path(args.manifest)
        preds_dir = Path(args.predictions_dir) if getattr(args, "predictions_dir", None) else None
        exp_summary = run_exp_03(
            manifest_path,
            predictions=preds_dir,
            limit=None,
            write_results=False,
        )
        if getattr(args, "penalized", False):
            m_block = exp_summary.get("metrics_penalized_with_failures", {})
            m_ser = m_block.get("mean_ser_penalized")
            m_ned = m_block.get("mean_omr_ned_penalized")
        else:
            m_block = exp_summary.get("metrics_on_successes", {})
            m_ser = m_block.get("mean_ser")
            m_ned = m_block.get("mean_omr_ned")

        if m_ser is not None and args.ser is None:
            ser = float(m_ser)
        if m_ned is not None and args.omr_ned is None:
            omr_ned = float(m_ned)

    threshold = config.promotion_threshold
    meets_threshold = bool(ser <= threshold.max_ser and omr_ned <= threshold.max_omr_ned)

    report = {
        "artifact_hash": artifact_data.get("artifact_hash"),
        "dataset_hash": artifact_data.get("dataset_hash"),
        "config_hash": config.config_hash,
        "seed": config.seed,
        "metrics": {
            "ser": ser,
            "omr_ned": omr_ned,
        },
        "threshold": {
            "max_ser": threshold.max_ser,
            "max_omr_ned": threshold.max_omr_ned,
        },
        "meets_threshold": meets_threshold,
        "evaluated_at": datetime.datetime.now(datetime.UTC).isoformat(),
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    status_str = "CUMPLE UMBRAL" if meets_threshold else "NO CUMPLE UMBRAL"
    print(f"[evaluate] Evaluación completada: {status_str}.")
    print(f"  SER     : {ser:.4f} (máximo admitido: {threshold.max_ser:.4f})")
    print(f"  OMR-NED : {omr_ned:.4f} (máximo admitido: {threshold.max_omr_ned:.4f})")
    print(f"  Reporte : {output_path}")
    return 0


# =============================================================================
# COMANDO 5: promote
# =============================================================================


def promote_command(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.is_file():
        print(
            f"Error: No se encontró el archivo de artefacto/reporte en '{input_path}'",
            file=sys.stderr,
        )
        return 1

    config_path = Path(args.config) if args.config else Path("configs/learning/default.json")
    config: JobConfig | None = None
    if config_path.is_file():
        config = load_job_config(config_path)

    data = json.loads(input_path.read_text(encoding="utf-8"))
    raw_metrics = data.get("metrics", {})
    ser = float(raw_metrics.get("ser", 0.0))
    omr_ned = float(raw_metrics.get("omr_ned", 0.0))

    artifact_hash = str(data.get("artifact_hash", ""))
    dataset_h = str(data.get("dataset_hash", ""))
    config_h = str(data.get("config_hash", config.config_hash if config else "none"))

    version = args.version
    if not version:
        version = f"v-{datetime.datetime.now(datetime.UTC).strftime('%Y%m%d-%H%M%S')}"

    # Umbral de promoción
    max_ser = float(
        args.max_ser
        if args.max_ser is not None
        else (config.promotion_threshold.max_ser if config else 0.2)
    )
    max_omr_ned = float(
        args.max_omr_ned
        if args.max_omr_ned is not None
        else (config.promotion_threshold.max_omr_ned if config else 0.15)
    )
    threshold = PromotionThreshold(max_ser=max_ser, max_omr_ned=max_omr_ned)

    db_url = args.db_url or _default_db_url()
    engine = create_engine_for_url(db_url)
    create_schema(engine)
    factory = create_session_factory(engine)

    with session_scope(factory) as db:
        # Asegurar que el artefacto exista en la tabla artifacts para la FK
        existing_artifact = db.get(ArtifactRecord, artifact_hash)
        if existing_artifact is None:
            artifact_record = ArtifactRecord(
                sha256=artifact_hash,
                kind="model",
                media_type="application/octet-stream",
                size_bytes=1024,
                path=f"sha256/{artifact_hash[:2]}/{artifact_hash[2:4]}/{artifact_hash}",
            )
            db.add(artifact_record)
            db.flush()

        registry = SqlAlchemyModelRegistry(db, threshold=threshold)

        version_data = ModelVersionData(
            version=version,
            artifact_hash=artifact_hash,
            dataset_hash=dataset_h,
            config_hash=config_h,
            metrics=EvaluationMetrics(ser=ser, omr_ned=omr_ned),
        )

        try:
            registry.register(version_data)
        except ValueError as err:
            print(f"Advertencia: versión ya registrada ({err}). Continuando con promoción...")

        try:
            registry.promote(version)
            promoted_ok = True
            rejection_reason = None
        except PromotionRejected as exc:
            promoted_ok = False
            rejection_reason = str(exc)

        active_ver = registry.active()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    seed = int(config.seed if config is not None else data.get("seed", 42))

    result = {
        "version": version,
        "artifact_hash": artifact_hash,
        "dataset_hash": dataset_h,
        "config_hash": config_h,
        "seed": seed,
        "promoted": promoted_ok,
        "rejection_reason": rejection_reason,
        "metrics": {"ser": ser, "omr_ned": omr_ned},
        "threshold": {"max_ser": max_ser, "max_omr_ned": max_omr_ned},
        "active_model_version": active_ver.version if active_ver else None,
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    if not promoted_ok:
        print(f"[promote] Promoción rechazada: {rejection_reason}", file=sys.stderr)
        if not args.allow_rejected:
            return 1
        return 0

    print(f"[promote] Versión promovida exitosamente: {version}")
    print(f"  artifact_hash : {artifact_hash}")
    print(f"  Modelo activo : {active_ver.version if active_ver else None}")
    print(f"  Resultado     : {output_path}")
    return 0


# =============================================================================
# COMANDO 6: run (pipeline encadenado)
# =============================================================================


def run_command(args: argparse.Namespace) -> int:
    print("=" * 60)
    print("Cadenza Offline Learning Pipeline — Ejecución de Punta a Punta")
    print("=" * 60)

    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = work_dir / "dataset.json"
    selected_path = work_dir / "selected.json"
    trained_path = work_dir / "trained_artifact.json"
    eval_path = work_dir / "evaluation_report.json"
    promotion_path = work_dir / "promotion_result.json"

    # 1. build-dataset
    print("\n--- PASO 1: build-dataset ---")
    b_args = argparse.Namespace(
        config=args.config,
        output=str(dataset_path),
        db_url=args.db_url,
        status=args.status,
        owner_id=args.owner_id,
    )
    rc = build_dataset_command(b_args)
    if rc != 0:
        return rc

    # 2. select
    print("\n--- PASO 2: select ---")
    s_args = argparse.Namespace(
        input=str(dataset_path),
        config=args.config,
        output=str(selected_path),
        strategy=args.strategy,
        budget=args.budget,
        seed=args.seed,
    )
    rc = select_command(s_args)
    if rc != 0:
        return rc

    # 3. train
    print("\n--- PASO 3: train ---")
    t_args = argparse.Namespace(
        input=str(selected_path),
        config=args.config,
        output=str(trained_path),
        artifacts_dir=args.artifacts_dir,
        db_url=args.db_url,
        ser=args.ser,
        omr_ned=args.omr_ned,
        trainer=getattr(args, "trainer", "auto"),
    )
    rc = train_command(t_args)
    if rc != 0:
        return rc

    # 4. evaluate
    print("\n--- PASO 4: evaluate ---")
    e_args = argparse.Namespace(
        input=str(trained_path),
        config=args.config,
        output=str(eval_path),
        ser=args.ser,
        omr_ned=args.omr_ned,
    )
    rc = evaluate_command(e_args)
    if rc != 0:
        return rc

    # 5. promote
    print("\n--- PASO 5: promote ---")
    p_args = argparse.Namespace(
        input=str(trained_path),
        version=args.version,
        config=args.config,
        db_url=args.db_url,
        output=str(promotion_path),
        max_ser=args.max_ser,
        max_omr_ned=args.max_omr_ned,
        allow_rejected=args.allow_rejected,
    )
    rc = promote_command(p_args)
    if rc != 0:
        return rc

    print("\n" + "=" * 60)
    print("Pipeline de aprendizaje completado exitosamente.")
    print("=" * 60)
    return 0


# =============================================================================
# CLI PARSER Y ENTRYPOINT
# =============================================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cadenza-ml",
        description=(
            "CLI de orquestación de jobs offline de aprendizaje activo en Cadenza (ADR-0008, #22)."
        ),
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # 1. build-dataset
    p_build = subparsers.add_parser(
        "build-dataset", help="Construye un dataset a partir de sesiones y ediciones en BD."
    )
    p_build.add_argument(
        "--config", default="configs/learning/default.json", help="Configuración versionada JSON."
    )
    p_build.add_argument(
        "--output", default="data/datasets/dataset.json", help="Ruta del archivo JSON de salida."
    )
    p_build.add_argument("--db-url", default=None, help="URL de la base de datos relacional.")
    p_build.add_argument(
        "--status", default="finalized", help="Filtrar por estado de sesión (default: finalized)."
    )
    p_build.add_argument("--owner-id", default=None, help="Filtrar por propietario (opcional).")

    # 2. select
    p_select = subparsers.add_parser(
        "select", help="Aplica una estrategia de adquisición sobre el dataset."
    )
    p_select.add_argument(
        "--input",
        "--dataset",
        dest="input",
        default="data/datasets/dataset.json",
        help="Dataset de entrada.",
    )
    p_select.add_argument(
        "--config", default="configs/learning/default.json", help="Configuración versionada JSON."
    )
    p_select.add_argument(
        "--output", default="data/datasets/selected.json", help="Ruta del archivo JSON de salida."
    )
    p_select.add_argument(
        "--strategy",
        default=None,
        help="Estrategia: hybrid, uncertainty, diversity, error_density, random.",
    )
    p_select.add_argument(
        "--budget", type=int, default=None, help="Presupuesto de muestras a seleccionar."
    )
    p_select.add_argument("--seed", type=int, default=None, help="Semilla determinista.")

    # 3. train
    p_train = subparsers.add_parser(
        "train", help="Entrena un modelo (FakeTrainer) y persiste los pesos."
    )
    p_train.add_argument(
        "--input",
        "--samples",
        dest="input",
        default="data/datasets/selected.json",
        help="Muestras de entrenamiento.",
    )
    p_train.add_argument(
        "--config", default="configs/learning/default.json", help="Configuración versionada JSON."
    )
    p_train.add_argument(
        "--output",
        default="results/trained_artifact.json",
        help="Metadatos del artefacto entrenado.",
    )
    p_train.add_argument(
        "--artifacts-dir", default="data/artifacts", help="Directorio raíz del ArtifactStore."
    )
    p_train.add_argument("--db-url", default=None, help="URL de la base de datos relacional.")
    p_train.add_argument(
        "--ser", type=float, default=None, help="SER para el entrenador simulado (opcional)."
    )
    p_train.add_argument(
        "--omr-ned",
        type=float,
        default=None,
        help="OMR-NED para el entrenador simulado (opcional).",
    )
    p_train.add_argument(
        "--trainer",
        choices=["auto", "fake", "torch"],
        default="auto",
        help="Backend del entrenador (auto, fake o torch). Por defecto auto.",
    )

    # 4. evaluate
    p_eval = subparsers.add_parser(
        "evaluate", help="Evalúa el artefacto entrenado frente al umbral de promoción."
    )
    p_eval.add_argument(
        "--input",
        "--artifact",
        dest="input",
        default="results/trained_artifact.json",
        help="Artefacto entrenado.",
    )
    p_eval.add_argument(
        "--config", default="configs/learning/default.json", help="Configuración versionada JSON."
    )
    p_eval.add_argument(
        "--output", default="results/evaluation_report.json", help="Ruta del informe de evaluación."
    )
    p_eval.add_argument("--ser", type=float, default=None, help="Sobreescribir SER evaluada.")
    p_eval.add_argument(
        "--omr-ned", type=float, default=None, help="Sobreescribir OMR-NED evaluada."
    )
    p_eval.add_argument(
        "--manifest",
        default=None,
        help="Manifest de evaluación para calcular métricas empíricas reales.",
    )
    p_eval.add_argument(
        "--predictions-dir",
        default=None,
        help="Directorio con transcripciones MusicXML del motor evaluado.",
    )
    p_eval.add_argument(
        "--penalized",
        action="store_true",
        help="Usar métricas penalizadas imputando fallos de segmentación a 1.0.",
    )

    # 5. promote
    p_promote = subparsers.add_parser(
        "promote", help="Registra y activa la versión en el ModelRegistry."
    )
    p_promote.add_argument(
        "--input",
        "--artifact",
        dest="input",
        default="results/trained_artifact.json",
        help="Artefacto o reporte.",
    )
    p_promote.add_argument("--version", default=None, help="Identificador de versión (ej. v1.1.0).")
    p_promote.add_argument(
        "--config", default="configs/learning/default.json", help="Configuración versionada JSON."
    )
    p_promote.add_argument("--db-url", default=None, help="URL de la base de datos relacional.")
    p_promote.add_argument(
        "--output", default="results/promotion_result.json", help="Resultado de la promoción."
    )
    p_promote.add_argument(
        "--max-ser", type=float, default=None, help="Sobreescribir umbral máx SER."
    )
    p_promote.add_argument(
        "--max-omr-ned", type=float, default=None, help="Sobreescribir umbral máx OMR-NED."
    )
    p_promote.add_argument(
        "--allow-rejected",
        action="store_true",
        help="No fallar con código 1 si el umbral no se cumple.",
    )

    # 6. run
    p_run = subparsers.add_parser("run", help="Ejecuta el pipeline completo de punta a punta.")
    p_run.add_argument(
        "--config", default="configs/learning/default.json", help="Configuración versionada JSON."
    )
    p_run.add_argument(
        "--work-dir",
        default="results/pipeline_run",
        help="Directorio de trabajo para artefactos intermedios.",
    )
    p_run.add_argument("--db-url", default=None, help="URL de la base de datos relacional.")
    p_run.add_argument(
        "--artifacts-dir", default="data/artifacts", help="Directorio raíz del ArtifactStore."
    )
    p_run.add_argument("--status", default="finalized", help="Filtrar sesiones por estado.")
    p_run.add_argument("--owner-id", default=None, help="Filtrar sesiones por propietario.")
    p_run.add_argument("--strategy", default=None, help="Estrategia de adquisición.")
    p_run.add_argument("--budget", type=int, default=None, help="Presupuesto de adquisición.")
    p_run.add_argument("--seed", type=int, default=None, help="Semilla.")
    p_run.add_argument("--version", default=None, help="Identificador de versión para registrar.")
    p_run.add_argument("--ser", type=float, default=None, help="SER para el modelo entrenado.")
    p_run.add_argument(
        "--omr-ned", type=float, default=None, help="OMR-NED para el modelo entrenado."
    )
    p_run.add_argument("--max-ser", type=float, default=None, help="Sobreescribir umbral máx SER.")
    p_run.add_argument(
        "--max-omr-ned", type=float, default=None, help="Sobreescribir umbral máx OMR-NED."
    )
    p_run.add_argument(
        "--allow-rejected", action="store_true", help="No fallar si la promoción es rechazada."
    )
    p_run.add_argument(
        "--trainer",
        choices=["auto", "fake", "torch"],
        default="auto",
        help="Backend del entrenador (auto, fake o torch). Por defecto auto.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.subcommand == "build-dataset":
        return build_dataset_command(args)
    if args.subcommand == "select":
        return select_command(args)
    if args.subcommand == "train":
        return train_command(args)
    if args.subcommand == "evaluate":
        return evaluate_command(args)
    if args.subcommand == "promote":
        return promote_command(args)
    if args.subcommand == "run":
        return run_command(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
