"""`ml export-pairs`: los pares imagen-partitura para entrenar un lector OMR (#420, ADR-0071).

Por cada tira de pentagrama de las sesiones que se pueden usar (la misma de `ml export-staves`,
ADR-0067), escribe en `--output-dir`:

- `<split>/<sesión>/s<sistema>_<parte>-<pentagrama>.png`: la tira de la foto (o del gran
  pentagrama del piano, `_1-0+1-1`);
- `….homr.musicxml`: lo que leyó HOMR en esos compases (el estado 0 de la sesión);
- `….musicxml`: lo corregido (el estado final), la etiqueta del par;
- `pares.csv`: una fila por par, con su partición, su obra, sus compases y el sha256 de sus tres
  archivos (columnas en `docs/experimentos/pares_imagen_partitura.md`);
- `README.md`: la ficha del dataset, con las cifras de esta exportación;
- `run_info.json`: el commit, la fecha, los filtros, las sesiones que quedan fuera con su
  motivo, los recuentos y el sha256 de `pares.csv` y de la ficha (`"simulated": false`).

Entran solo las sesiones finalizadas cuya corrección se verifica (`correction_verified`). De las
cuentas del registro público, por defecto las que tienen el permiso de uso de los datos vigente
(ADR-0065; decisión del responsable del 2026-11-19, la de #422), y ninguna con
`--exclude-self-registered`; sin el permiso vigente, nunca. La partición es la fija por obra de #255: `split_seed` es
obligatoria. No reentrena nada (#103). No tiene salida por defecto: la ruta se da siempre, ha de
estar vacía y no puede caer en `results/` ni en `data/` del repositorio.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import io
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from cadenza.application import DATA_CONSENT_VERSION, ArtifactNotFound, has_current_data_consent
from cadenza.domain import ScoreDocument, materialize
from cadenza.learning import assign_split
from cadenza.learning.staff_strips import StripError, plan_strips, strip_score
from cadenza.learning.suggestions import correction_verified, shared_works
from cadenza.persistence import (
    FilesystemArtifactStore,
    SqlAlchemyEditEventRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
    create_engine_for_url,
    create_session_factory,
    session_scope,
)
from sqlalchemy.exc import SQLAlchemyError

from ml.export_staves_cli import _commit, _safe_url, _staves_name, open_photo, unsafe_output

FORMAT_VERSION = 1
SPLITS = ("train", "test")

COLUMNS = (
    "par",
    "split",
    "work_id",
    "session_id",
    "test_score_id",
    "source_image_hash",
    "sistema",
    "pentagramas",
    "compases",
    "primer_compas",
    "ultimo_compas",
    "lectura_homr",
    "homr_version",
    "imagen",
    "ancho",
    "alto",
    "imagen_sha256",
    "homr",
    "homr_sha256",
    "corregida",
    "corregida_sha256",
    "corregido",
)

DICTIONARY = "docs/experimentos/pares_imagen_partitura.md"


def _fail(message: str) -> int:
    print(f"Error: {message}", file=sys.stderr)
    return 1


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def export_session_pairs(
    session: Any, edits_repo: Any, store: Any, split: str, work: str
) -> tuple[list[dict[str, Any]], dict[str, bytes]] | str:
    """Los pares de una sesión: sus filas de `pares.csv` y sus archivos (ruta relativa a la
    salida y contenido), o el motivo por el que queda fuera. No escribe nada: una sesión que
    falla no deja archivos a medias."""

    # Aquí y no arriba: construir la CLI no debe cargar music21 (`ml/cli.py`).
    from cadenza.interchange import score_ir_to_musicxml
    from cadenza.omr.adapters.homr_capture import CAPTURE_FORMAT_VERSION

    document = ScoreDocument.from_primitive(session.document)
    capture = document.omr_capture
    if capture is None:
        return "sin la captura de HOMR (transcrita antes de #403)"
    if capture.get("format_version") != CAPTURE_FORMAT_VERSION:
        return f"captura de otro formato ({capture.get('format_version')!r})"
    raw = document.score
    edits = edits_repo.list_events(session.id)
    final = materialize(raw, edits) if edits else raw
    if not correction_verified(raw, final, document_id=session.document_id):
        return "la corrección no se verifica: sus ediciones derivadas no dan el estado final"
    try:
        photo = open_photo(store.get(session.image_artifact or ""))
    except (ArtifactNotFound, OSError, ValueError) as exc:
        return f"sin la imagen ({type(exc).__name__})"
    try:
        strips = plan_strips(capture, raw, photo.size)
        scores = [(strip, strip_score(raw, strip), strip_score(final, strip)) for strip in strips]
    except StripError as exc:
        return str(exc)

    rows: list[dict[str, Any]] = []
    files: dict[str, bytes] = {}
    for strip, read, corrected in scores:
        stem = f"{split}/{session.id}/s{strip.system}_{_staves_name(strip)}"
        buffer = io.BytesIO()
        crop = photo.crop(strip.box)
        crop.save(buffer, format="PNG")
        image = buffer.getvalue()
        homr = score_ir_to_musicxml(read, stable=True).encode("utf-8")
        label = score_ir_to_musicxml(corrected, stable=True).encode("utf-8")
        files[f"{stem}.png"] = image
        files[f"{stem}.homr.musicxml"] = homr
        files[f"{stem}.musicxml"] = label
        rows.append(
            {
                "par": f"{session.id}/s{strip.system}_{_staves_name(strip)}",
                "split": split,
                "work_id": work,
                "session_id": session.id,
                "test_score_id": session.test_score_id,
                "source_image_hash": session.image_artifact,
                "sistema": strip.system,
                "pentagramas": _staves_name(strip),
                "compases": len(strip.measures),
                "primer_compas": strip.measures[0],
                "ultimo_compas": strip.measures[-1],
                "lectura_homr": strip.reading,
                "homr_version": capture.get("homr_version"),
                "imagen": f"{stem}.png",
                "ancho": crop.width,
                "alto": crop.height,
                "imagen_sha256": _sha256(image),
                "homr": f"{stem}.homr.musicxml",
                "homr_sha256": _sha256(homr),
                "corregida": f"{stem}.musicxml",
                "corregida_sha256": _sha256(label),
                # Cualquier cambio de la tira: notas, clave, armadura, compás o marcas.
                "corregido": homr != label,
            }
        )
    return rows, files


def pairs_csv(rows: list[dict[str, Any]]) -> bytes:
    """`pares.csv`: una fila por par, en el orden de `COLUMNS`."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow(
            [
                (
                    ("true" if row[c] else "false")
                    if isinstance(row[c], bool)
                    else ("" if row[c] is None else row[c])
                )
                for c in COLUMNS
            ]
        )
    return buffer.getvalue().encode("utf-8")


def _counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def summary(selected: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "pairs": len(selected),
            "pairs_corrected": sum(1 for row in selected if row["corregido"]),
            "sessions": len({row["session_id"] for row in selected}),
            "works": len({row["work_id"] for row in selected}),
        }

    return {
        **summary(rows),
        "by_split": {split: summary([r for r in rows if r["split"] == split]) for split in SPLITS},
    }


def dataset_card(info: dict[str, Any]) -> str:
    """La ficha del dataset (`README.md`), con las cifras y los filtros de `info`."""

    counts, filters, consent = info["counts"], info["filters"], info["consent"]
    train, test = counts["by_split"]["train"], counts["by_split"]["test"]
    versions = ", ".join(f"{v} en {n} sesiones" for v, n in info["homr_versions"].items())
    text = f"el del texto `{consent['version']}`"
    registered = (
        "no entran en esta exportación (`--exclude-self-registered`), tampoco las que tienen el"
        f" permiso vigente, {text}."
        if filters["exclude_self_registered"]
        else f"entran por defecto las que tienen el permiso vigente, {text} (decisión del"
        " responsable del 2026-11-19, #422)."
    )
    refused = consent["sessions_without_current_consent"]
    table = "\n".join(
        f"| `{split}` | {part['pairs']} | {part['pairs_corrected']} | {part['sessions']} |"
        f" {part['works']} |"
        for split, part in counts["by_split"].items()
    )
    return f"""# Pares imagen-partitura de Cadenza

Exportado el {info["generated_at"][:10]} con `ml export-pairs` (commit `{info["commit"]}`), \
desde `{info["origin"]["database"]}`. Formato {info["format_version"]} de la exportación \
(ADR-0071, #420). **No es un resultado:** son los datos para entrenar un lector en el futuro \
(#103).

Pares: {counts["pairs"]}, de {counts["sessions"]} sesiones y {counts["works"]} obras \
({train["pairs"]} en `train` y {test["pairs"]} en `test`). Con alguna corrección: \
{counts["pairs_corrected"]}. Sesiones finalizadas que quedaron fuera por otros motivos que \
el permiso: {len(info["left_out"])}, con su motivo en `run_info.json`.

## Qué es cada par

- `<split>/<sesión>/s<sistema>_<parte>-<pentagrama>.png`: la tira de la foto de un pentagrama \
de un sistema, o del gran pentagrama del piano (`_1-0+1-1`), recortada con las cajas de los \
pentagramas de HOMR (ADR-0067).
- `….homr.musicxml`: lo que leyó HOMR en esos compases (el estado 0 de la sesión).
- `….musicxml`: lo corregido a mano (el estado final de la sesión). Es la etiqueta.
- `pares.csv`: una fila por par, con su partición, su obra y el sha256 de sus tres archivos \
(columnas en `{DICTIONARY}`).

Cada MusicXML tiene la parte de la tira con solo sus pentagramas y sus compases, con sus \
números de la página. Los dos salen del mismo exportador de Cadenza: sus diferencias son solo \
las correcciones. Para entrenar HOMR, su conversor \
(`training/omr_datasets/music_xml_parser.py`) los pasa a sus `.tokens`.

## Origen

- Fotos de partituras subidas a Cadenza por sus usuarios, leídas con HOMR ({versions}) y \
corregidas a mano en la vista de corrección.
- Solo sesiones **finalizadas** (su corrección es una que alguien dio por buena) y \
**verificadas** (las ediciones derivadas de la lectura al estado final lo reproducen, la \
comprobación de #255).
- Quedan fuera, con su motivo, las sesiones sin la captura de HOMR (transcritas antes de #403), \
sin imagen, con la imagen preprocesada o cuyas cajas no casan con la partitura.

## Licencias

- Las fotos y las partituras no son de Cadenza: los derechos de cada obra, arreglo o edición \
siguen siendo de quien los tenga, y subirlas no los cede. **No hay licencia para redistribuir \
este dataset.**
- El permiso de uso de los datos (ADR-0065) autoriza a usarlos solo dentro del proyecto, para \
investigar y para entrenar sus modelos. Cadenza no publica ni comparte las imágenes: lo que se \
publique serán cifras de conjunto.
- La licencia del código de Cadenza está pendiente (#259). HOMR es AGPL-3.0; su \
`LICENSE_FAQ.md` dice con qué datos y licencias se entrenaron sus pesos.

## Permiso

- Cuentas del registro público: {registered} Las que no lo tienen (nunca lo dieron, lo \
retiraron o lo dieron para otro texto) quedan siempre fuera: {refused} sesiones en esta \
exportación.
- Cuentas que no vienen del registro público (las del equipo, anteriores a ADR-0070, que dejó \
el registro como única forma de crear una cuenta): no se les pide este permiso y entran.
- Los pares no llevan el nombre de usuario: la sesión va por su identificador y la obra por la \
partitura de prueba o el sha256 de la foto.
- Quien retira su permiso deja de entrar desde ese momento: una exportación es una foto fija, \
así que tras una retirada se borra y se vuelve a exportar. Lo que ya se entrenó no se puede \
deshacer.
- La carpeta tiene fotos de personas: no se publica ni se comparte fuera del proyecto.

## Partición

- Fija por obra, la de #255 (ADR-0036 §10): `assign_split(obra, seed={filters["split_seed"]}, \
test_fraction={filters["test_fraction"]})`. Depende solo de la obra, de la semilla y de la \
fracción de prueba.
- La obra es la partitura de prueba (`test_score:<id>`) o el sha256 de la foto \
(`image:<sha256>`), y las sesiones que comparten una u otra son la misma obra, también \
encadenadas: una página del banco subida sin partitura de prueba va con ella, porque su foto es \
la misma. Todas las tiras de una obra van a la misma carpeta.
- Si la muestra crece, una obra solo cambia de lado si una sesión nueva la une a otra (una foto \
que se sube después con su partitura de prueba).
- No hay partición de validación: se saca de `train` agrupando por `work_id`.

| Partición | Pares | Con correcciones | Sesiones | Obras |
|---|---|---|---|---|
{table}

## Limitaciones

- **Sin cajas por nota:** cada par es una tira por sistema. HOMR no da la posición de cada \
símbolo (INV-0001): sirve para un lector de secuencias como el de HOMR, no para uno de \
detección.
- **El primer compás de un sistema puede salir corrido** si HOMR no detectó la barra que cierra \
un pentagrama (ADR-0067): esa tira y la siguiente comparten un compás de más o de menos.
- **Dos fotos distintas de la misma página**, sin partitura de prueba que las una, tienen \
distinto sha256: son dos obras y pueden caer en particiones distintas.
- **El primer compás de cada tira lleva la clave, la armadura y el compás que rigen allí;** el \
compás se escribe aunque la tira no lo dibuje.
- **Lo que la importación de Cadenza descarta** (trinos, grupetos, repeticiones) no está en los \
MusicXML; el de HOMR de la página entera sigue en la captura (`ml export-staves`).
- **PrIMuS no entra y no es comparable:** sus imágenes son dibujos generados con Verovio, no \
fotos. Estos pares sí son fotos, con su luz, su perspectiva y su papel; mezclarlos con PrIMuS es \
mezclar dominios.
"""


def export_pairs_command(args: argparse.Namespace) -> int:
    db_url = args.db_url or os.environ.get("CADENZA_DATABASE_URL")
    if not db_url:
        return _fail("falta la base: da --db-url o CADENZA_DATABASE_URL")
    artifacts = args.artifacts_dir or os.environ.get("CADENZA_ARTIFACTS_DIR")
    if not artifacts:
        return _fail("faltan las imágenes: da --artifacts-dir o CADENZA_ARTIFACTS_DIR")
    if not Path(str(artifacts)).is_dir():
        return _fail(f"no existe la carpeta de las fotos: {artifacts}")
    if args.split_seed is None:
        return _fail("falta --split-seed (la semilla de correction_corpus_split.json de #255)")
    if not 0.0 < args.test_fraction < 1.0:
        return _fail(f"--test-fraction ha de estar entre 0 y 1, no {args.test_fraction}")
    output = Path(args.output_dir).resolve()
    problem = unsafe_output(output)
    if problem is not None:
        return _fail(problem)

    rows: list[dict[str, Any]] = []
    left_out: dict[str, str] = {}
    exported: list[str] = []
    versions: Counter[str] = Counter()
    without_consent = excluded = 0
    factory = create_session_factory(create_engine_for_url(db_url))
    with session_scope(factory) as db:
        sessions = SqlAlchemySessionRepository(db)
        edits_repo = SqlAlchemyEditEventRepository(db)
        users = SqlAlchemyUserRepository(db)
        store = FilesystemArtifactStore(artifacts, db)
        eligible = []
        for session in sessions.list(status="finalized"):
            owner = users.get(session.owner_id)
            if owner is None:
                left_out[session.id] = "sin la cuenta de su dueño"
                continue
            if owner.self_registered:
                # Sin el permiso vigente (nunca dado, retirado o de otro texto), nunca entra. De
                # estas y de las que deja fuera la opción solo se cuentan: ni su identificador.
                if not has_current_data_consent(owner):
                    without_consent += 1
                    continue
                if args.exclude_self_registered:
                    excluded += 1
                    continue
            eligible.append(session)
        works = shared_works(eligible)
        for session in eligible:
            work = works.get(session.id)
            if work is None:
                left_out[session.id] = "sin página de origen (test_score_id ni imagen)"
                continue
            split = assign_split(work, seed=args.split_seed, test_fraction=args.test_fraction)
            try:
                result = export_session_pairs(session, edits_repo, store, split, work)
            except SQLAlchemyError:
                # Con PostgreSQL, la transacción quedaría abortada para las que siguen.
                raise
            except Exception as exc:  # una sesión rara no para la exportación
                result = f"no se pudo exportar ({type(exc).__name__}: {exc})"
            if isinstance(result, str):
                left_out[session.id] = result
                continue
            own_rows, files = result
            for relative, content in files.items():
                path = output / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            rows.extend(own_rows)
            exported.append(session.id)
            versions[str(own_rows[0]["homr_version"] or "?") if own_rows else "?"] += 1

    # Por partición y sesión; dentro de una sesión, sus tiras en el orden de la página.
    rows.sort(key=lambda row: (row["split"], row["session_id"]))
    output.mkdir(parents=True, exist_ok=True)
    content = pairs_csv(rows)
    (output / "pares.csv").write_bytes(content)
    info: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "simulated": False,
        "commit": _commit(),
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "origin": {"database": _safe_url(db_url), "artifacts_dir": Path(artifacts).name},
        "format": {
            "image": "png",
            "score": "musicxml",
            "writer": "cadenza.interchange.score_ir_to_musicxml(stable=True)",
            "adr": "docs/adr/ADR-0071-pares-imagen-partitura-para-entrenar-un-lector.md",
        },
        "filters": {
            "status": "finalized",
            "verified_only": True,
            "exclude_self_registered": args.exclude_self_registered,
            "split_seed": args.split_seed,
            "test_fraction": args.test_fraction,
        },
        "consent": {
            "version": DATA_CONSENT_VERSION,
            "sessions_without_current_consent": without_consent,
            "sessions_excluded_by_option": excluded,
        },
        "sessions": sorted(exported),
        "left_out": dict(sorted(left_out.items())),
        "counts": _counts(rows),
        "homr_versions": dict(sorted(versions.items())),
        "dictionary": DICTIONARY,
    }
    card = dataset_card(info).encode("utf-8")
    (output / "README.md").write_bytes(card)
    info["sha256"] = {"pares.csv": _sha256(content), "README.md": _sha256(card)}
    (output / "run_info.json").write_text(
        json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    counts = info["counts"]
    print("[export-pairs] Pares escritos.")
    print(f"  sesiones   : {counts['sessions']} ({counts['works']} obras)")
    for split in SPLITS:
        part = counts["by_split"][split]
        print(f"  {split:<10} : {part['pairs']} pares de {part['works']} obras")
    print(f"  corregidos : {counts['pairs_corrected']}")
    print(f"  fuera      : {len(left_out)}, más {without_consent} sin el permiso vigente")
    for session_id, reason in sorted(left_out.items()):
        print(f"    {session_id}: {reason}")
    print(f"  salida     : {output}")
    return 0


def add_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "export-pairs",
        help=(
            "Exporta pares imagen-partitura (tira PNG y MusicXML leído y corregido) para"
            " entrenar un lector OMR (#420)."
        ),
    )
    parser.add_argument("--output-dir", required=True, help="Directorio de los pares.")
    parser.add_argument("--db-url", default=None, help="URL de la base (o CADENZA_DATABASE_URL).")
    parser.add_argument(
        "--artifacts-dir",
        default=None,
        help="Directorio de los artefactos, con las fotos (o CADENZA_ARTIFACTS_DIR).",
    )
    parser.add_argument(
        "--split-seed",
        type=int,
        default=None,
        help="Semilla de la partición por obra de #255 (obligatoria).",
    )
    parser.add_argument("--test-fraction", type=float, default=0.2)
    parser.add_argument(
        "--exclude-self-registered",
        action="store_true",
        help=(
            "Dejar fuera las cuentas del registro público, también las que tienen el permiso"
            " vigente (por defecto entran; las que no lo tienen quedan siempre fuera)."
        ),
    )
