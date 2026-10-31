"""`ml suggestions`: entrenar, evaluar, promover y construir el corpus de la capa (ADR-0036).

- `train`: cuenta las frecuencias del corpus y elige los umbrales por validación cruzada;
  escribe el artefacto JSON (determinista: mismo corpus y configuración, mismos bytes).
- `evaluate`: mide el artefacto sobre la partición de prueba fija de #255 frente a la línea
  base de no tener capa. Las métricas son siempre medidas (CLAUDE.md §8).
- `promote`: registra la versión y la promueve solo si mejora a la activa (o, la primera, a
  no tener capa). Promover es explícito, nunca efecto de entrenar.
- `build-dataset`: une el corpus de `exp_12` (sin modificarlo) con las sesiones finalizadas
  de Cadenza y las respuestas a sus sugerencias.

Ningún comando tiene salida por defecto bajo `results/`: las rutas se dan siempre.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from cadenza.application import SuggestionModelVersionData
from cadenza.learning.suggestions import (
    SuggestionTrainingError,
    artifact_bytes,
    check_partition,
    evaluate,
    file_sha256,
    load_suggestions_config,
    promotion_decision,
    read_corpus,
    session_records,
    train,
)
from cadenza.persistence import (
    FilesystemArtifactStore,
    SqlAlchemyEditEventRepository,
    SqlAlchemySessionRepository,
    SqlAlchemySuggestionModelRegistry,
    SqlAlchemyUserRepository,
    create_engine_for_url,
    create_session_factory,
    session_scope,
)
from cadenza.validation.learned import (
    FEATURE_VERSION,
    MODEL_TYPE,
    FrequencyBackoffModel,
    InvalidSuggestionArtifact,
)

DEFAULT_CONFIG = "configs/learning/suggestions.json"


def _fail(message: str) -> int:
    print(f"Error: {message}", file=sys.stderr)
    return 1


def train_command(args: argparse.Namespace) -> int:
    corpus = Path(args.corpus)
    try:
        config = load_suggestions_config(Path(args.config))
        records = read_corpus(corpus)
        artifact = train(records, config, dataset_hash=file_sha256(corpus))
    except (SuggestionTrainingError, OSError, KeyError, ValueError) as exc:
        return _fail(str(exc))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    content = artifact_bytes(artifact)
    output.write_bytes(content)
    training = artifact["training"]
    print("[suggestions train] Artefacto escrito.")
    print(f"  dataset_hash : {training['dataset_hash']}")
    print(f"  config_hash  : {training['config_hash']}")
    print(f"  seed         : {training['seed']}")
    print(f"  sha256       : {_sha256(content)}")
    for family, data in artifact["families"].items():
        print(f"  {family:<10}: umbral={data['threshold']} activa={data['active']}")
    print(f"  salida       : {output}")
    return 0


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _load_model(path: Path, version: str) -> tuple[FrequencyBackoffModel, bytes]:
    content = path.read_bytes()
    return FrequencyBackoffModel.from_bytes(content, version=version), content


def evaluate_command(args: argparse.Namespace) -> int:
    corpus = Path(args.corpus)
    try:
        model, content = _load_model(Path(args.model), version="evaluation")
        records = read_corpus(corpus)
        check_partition(json.loads(content.decode("utf-8")), records)
    except (SuggestionTrainingError, InvalidSuggestionArtifact, OSError) as exc:
        return _fail(str(exc))
    report = evaluate(model, records, split=args.split)
    if report["incipits"] == 0:
        return _fail(f"el corpus no tiene incipits verificados de la partición {args.split!r}")
    training = json.loads(content.decode("utf-8")).get("training") or {}
    report = {
        "model_sha256": _sha256(content),
        "model_type": MODEL_TYPE,
        "feature_version": FEATURE_VERSION,
        "training_dataset_hash": training.get("dataset_hash"),
        "config_hash": training.get("config_hash"),
        "seed": training.get("seed"),
        "evaluation_dataset_hash": file_sha256(corpus),
        "measured_at": datetime.datetime.now(datetime.UTC).isoformat(),
        **report,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    learned = report["learned"]
    ranking = report["rule_findings"]
    print("[suggestions evaluate] Medición sobre la partición de prueba.")
    print(f"  incipits             : {report['incipits']}")
    print(
        f"  F1 propios (activos) : {learned['f1']}  (sin capa: {report['baseline']['learned_f1']})"
    )
    print(
        f"  primera sugerencia   : {ranking['top1_accuracy']}  "
        f"(primer candidato de la regla: {ranking['baseline_top1_accuracy']})"
    )
    print(f"  salida               : {output}")
    return 0


def promote_command(args: argparse.Namespace) -> int:
    model_path = Path(args.model)
    report_path = Path(args.report)
    try:
        content = model_path.read_bytes()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        version = args.version or (
            f"sug-{datetime.datetime.now(datetime.UTC).strftime('%Y%m%d-%H%M%S')}"
        )
        FrequencyBackoffModel.from_bytes(content, version=version)
    except (OSError, json.JSONDecodeError, InvalidSuggestionArtifact) as exc:
        return _fail(str(exc))
    sha = _sha256(content)
    if report.get("model_sha256") != sha:
        return _fail("el informe no es de este artefacto (model_sha256 distinto)")
    training = json.loads(content.decode("utf-8")).get("training") or {}

    factory = create_session_factory(create_engine_for_url(args.db_url or _default_db_url()))
    with session_scope(factory) as db:
        registry = SqlAlchemySuggestionModelRegistry(db)
        active = registry.active()
        ok, reason = promotion_decision(report, None if active is None else active.metrics)
        if not ok:
            print(f"[suggestions promote] Rechazada: {reason}", file=sys.stderr)
            return 1
        if any(v.version == version for v in registry.versions()):
            print(f"[suggestions promote] La versión {version} ya existe.", file=sys.stderr)
            return 1
        store = FilesystemArtifactStore(Path(args.artifacts_dir), session=db)
        digest = store.put(content, kind="suggestion_model", media_type="application/json")
        registry.register(
            SuggestionModelVersionData(
                version=version,
                artifact_hash=digest,
                dataset_hash=str(training.get("dataset_hash")),
                config_hash=str(training.get("config_hash")),
                seed=int(training.get("seed", 0)),
                model_type=MODEL_TYPE,
                feature_version=FEATURE_VERSION,
                metrics=report,
            )
        )
        registry.promote(version)
    print(f"[suggestions promote] Promovida {version}: {reason}.")
    print(f"  sha256 : {digest}")
    print("  Entra en vigor al reiniciar la API con CADENZA_SUGGESTIONS_ENABLED=true.")
    return 0


def build_dataset_command(args: argparse.Namespace) -> int:
    corpus = Path(args.corpus)
    if not corpus.is_file():
        return _fail(f"no existe el corpus de exp_12: {corpus}")
    factory = create_session_factory(create_engine_for_url(args.db_url or _default_db_url()))
    with session_scope(factory) as db:
        records, left_out = session_records(
            session_repository=SqlAlchemySessionRepository(db),
            edit_repository=SqlAlchemyEditEventRepository(db),
            user_repository=SqlAlchemyUserRepository(db),
            split_seed=args.split_seed,
            test_fraction=args.test_fraction,
            include_self_registered=args.include_self_registered,
        )
    output = Path(args.output)
    if output.resolve() == corpus.resolve():
        return _fail("la salida no puede ser el corpus de exp_12: es la evidencia de #255")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        handle.write(corpus.read_bytes().rstrip(b"\n") + b"\n")
        for record in records:
            handle.write(
                (json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
            )
    sessions = {r["session_id"] for r in records}
    print("[suggestions build-dataset] Corpus escrito.")
    print(f"  sesiones finalizadas : {len(sessions)}")
    print(f"  registros añadidos   : {len(records)}")
    print(f"  fuera                : {len(left_out)}")
    for session_id, reason in sorted(left_out.items()):
        print(f"    {session_id}: {reason}")
    print(f"  dataset_hash         : {file_sha256(output)}")
    print(f"  salida               : {output}")
    return 0


def _default_db_url() -> str:
    return os.environ.get("CADENZA_DATABASE_URL", "sqlite:///cadenza.db")


def add_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "suggestions", help="Capa de sugerencias que aprende de las correcciones (ADR-0036)."
    )
    commands = parser.add_subparsers(dest="suggestions_command", required=True)

    p_train = commands.add_parser("train", help="Entrena la capa con un corpus de correcciones.")
    p_train.add_argument("--corpus", required=True, help="Corpus JSONL (exp_12 o build-dataset).")
    p_train.add_argument("--config", default=DEFAULT_CONFIG, help="Configuración JSON.")
    p_train.add_argument("--output", required=True, help="Artefacto JSON de salida.")

    p_eval = commands.add_parser("evaluate", help="Mide la capa en la partición de prueba.")
    p_eval.add_argument("--model", required=True, help="Artefacto JSON de la capa.")
    p_eval.add_argument("--corpus", required=True, help="Corpus con la partición de prueba fija.")
    p_eval.add_argument("--split", default="test", help="Partición que se mide (test).")
    p_eval.add_argument("--output", required=True, help="Informe JSON de salida.")

    p_promote = commands.add_parser("promote", help="Registra y promueve si mejora.")
    p_promote.add_argument("--model", required=True, help="Artefacto JSON de la capa.")
    p_promote.add_argument("--report", required=True, help="Informe de `evaluate`.")
    p_promote.add_argument("--version", default=None, help="Nombre de la versión.")
    p_promote.add_argument("--db-url", default=None, help="URL de la base de datos.")
    p_promote.add_argument(
        "--artifacts-dir", required=True, help="Directorio del ArtifactStore de la API."
    )

    p_build = commands.add_parser(
        "build-dataset", help="Une el corpus de exp_12 con las sesiones finalizadas."
    )
    p_build.add_argument("--corpus", required=True, help="Corpus de exp_12 (no se modifica).")
    p_build.add_argument("--output", required=True, help="Corpus JSONL de salida.")
    p_build.add_argument("--db-url", default=None, help="URL de la base de datos.")
    p_build.add_argument(
        "--split-seed",
        type=int,
        required=True,
        help="Semilla de la partición de #255 (la de correction_corpus_split.json).",
    )
    p_build.add_argument("--test-fraction", type=float, default=0.2)
    p_build.add_argument(
        "--include-self-registered",
        action="store_true",
        help="Incluir las sesiones de cuentas del registro público (fuera por defecto).",
    )


def run(args: argparse.Namespace) -> int:
    command = args.suggestions_command
    if command == "train":
        return train_command(args)
    if command == "evaluate":
        return evaluate_command(args)
    if command == "promote":
        return promote_command(args)
    if command == "build-dataset":
        return build_dataset_command(args)
    return _fail(f"comando desconocido: {command}")
