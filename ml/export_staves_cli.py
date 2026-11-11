"""`ml export-staves`: cada pentagrama de la foto con lo que leyó HOMR y lo que quedó corregido.

Para las sesiones que guardan la captura de HOMR (#403, ADR-0067: las cajas de los pentagramas,
el recorte del papel y los sistemas), escribe en `--output-dir`:

- `recortes/<sesión>/s<sistema>_<parte>-<pentagrama>.png`: la tira de la foto de cada pentagrama
  (o de un gran pentagrama de piano, `_1-0+1-1`).
- `pentagramas.csv`: una fila por tira, con su caja en la foto, sus compases y la transcripción
  de esos compases en la lectura de HOMR (`lectura`) y en el estado final de la sesión
  (`corregida`), y si difieren (`corregido`). Es el par con el que se entrenaría un lector.
- `musicxml/<sesión>-homr.musicxml` (el MusicXML en bruto de HOMR, de la captura) y
  `musicxml/<sesión>-final.musicxml` (el estado final, del exportador de Cadenza).
- Con `--laminas`, `laminas/<sesión>.png`: la foto con las cajas y, debajo, cada tira con su
  lectura y su corrección, para comprobarlo a ojo.
- `run_info.json`: el commit, la fecha, los filtros, las sesiones que quedan fuera con su motivo,
  los recuentos y el sha256 del CSV (`"simulated": false`).

De la base, por defecto solo las sesiones finalizadas y sin cuentas del registro público. Con
`--include-self-registered` entran las del registro **con el permiso de uso de los datos vigente**
(ADR-0065, decisión del responsable del 2026-11-11). No tiene salida por defecto: la ruta se da
siempre, fuera de `results/`.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from cadenza.application import ArtifactNotFound
from cadenza.domain import ScoreDocument, ScoreIR, materialize
from cadenza.learning.staff_strips import Strip, StripError, plan_strips, strip_sequence
from cadenza.persistence import (
    FilesystemArtifactStore,
    SqlAlchemyEditEventRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
    create_engine_for_url,
    create_session_factory,
    session_scope,
)
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

FORMAT_VERSION = 1

COLUMNS = (
    "session_id",
    "test_score_id",
    "status",
    "source_image_hash",
    "sistema",
    "compases",
    "primer_compas",
    "ultimo_compas",
    "pentagramas",
    "lectura_homr",
    "x0",
    "y0",
    "x1",
    "y1",
    "recorte",
    "lectura",
    "corregida",
    "corregido",
)


def _fail(message: str) -> int:
    print(f"Error: {message}", file=sys.stderr)
    return 1


def _commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _safe_url(url: str) -> str:
    """Solo el dialecto y el nombre de la base: sin usuario, host ni contraseña."""
    try:
        parsed = make_url(url)
    except ArgumentError:
        return "(no se pudo leer la URL)"
    return f"{parsed.get_backend_name()}:{Path(parsed.database or '').name}"


def _staves_name(strip: Strip, joiner: str = "+") -> str:
    return joiner.join(f"{part}-{staff}" for part, staff in strip.staves)


def _font(size: int) -> Any:
    for name in ("DejaVuSans.ttf", "segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _sheet(photo: Image.Image, rows: list[tuple[Strip, str, str]]) -> Image.Image:
    """La foto con las cajas y, debajo, cada tira con su lectura y su corrección."""

    width = photo.width
    size = max(14, width // 90)
    font, bold = _font(size), _font(size + 2)
    page = photo.convert("RGB")
    draw = ImageDraw.Draw(page)
    for strip, _, _ in rows:
        draw.rectangle(strip.box, outline="#00798c", width=max(2, width // 600))
        draw.text(
            (strip.box[0] + 6, strip.box[1] + 2),
            f"S{strip.system}·{_staves_name(strip)}",
            fill="#00798c",
            font=bold,
        )
    blocks = []
    line = int(size * 1.5)
    for strip, read, final in rows:
        crop = photo.crop(strip.box).convert("RGB")
        changed = read != final
        lines = [
            ("HOMR:  " + read, "#222222"),
            ("Final: " + final, "#c0392b" if changed else "#222222"),
        ]
        block = Image.new("RGB", (width, crop.height + line * (len(lines) + 2)), "white")
        bd = ImageDraw.Draw(block)
        title = f"Sistema {strip.system} · pentagramas {_staves_name(strip)} · compases "
        title += f"{strip.measures[0]} a {strip.measures[-1]}" + (" · corregido" if changed else "")
        bd.text((8, 4), title, fill="#00798c", font=bold)
        block.paste(crop, (strip.box[0], line))
        for index, (text, color) in enumerate(lines):
            bd.text((8, line + crop.height + 4 + index * line), text[:220], fill=color, font=font)
        blocks.append(block)
    sheet = Image.new("RGB", (width, page.height + sum(b.height for b in blocks)), "white")
    sheet.paste(page, (0, 0))
    y = page.height
    for block in blocks:
        sheet.paste(block, (0, y))
        y += block.height
    return sheet


def _final_score(raw: ScoreIR, edits: Any) -> ScoreIR:
    return materialize(raw, edits) if edits else raw


def export_staves_command(args: argparse.Namespace) -> int:
    db_url = args.db_url or os.environ.get("CADENZA_DATABASE_URL")
    if not db_url:
        return _fail("falta la base: da --db-url o CADENZA_DATABASE_URL")
    artifacts = args.artifacts_dir or os.environ.get("CADENZA_ARTIFACTS_DIR")
    if not artifacts:
        return _fail("faltan las imágenes: da --artifacts-dir o CADENZA_ARTIFACTS_DIR")
    output = Path(args.output_dir)
    from cadenza.interchange import score_ir_to_musicxml
    from cadenza.omr.adapters.homr_capture import raw_musicxml

    rows: list[dict[str, Any]] = []
    left_out: dict[str, str] = {}
    exported: list[str] = []
    factory = create_session_factory(create_engine_for_url(db_url))
    with session_scope(factory) as db:
        sessions = SqlAlchemySessionRepository(db)
        edits_repo = SqlAlchemyEditEventRepository(db)
        users = SqlAlchemyUserRepository(db)
        store = FilesystemArtifactStore(artifacts, db)
        for session in sessions.list(status=None if args.include_unfinished else "finalized"):
            owner = users.get(session.owner_id)
            if owner is not None and owner.self_registered:
                if not args.include_self_registered:
                    left_out[session.id] = "cuenta del registro público"
                    continue
                if owner.data_consent_at is None:
                    left_out[session.id] = "cuenta del registro sin permiso de uso de los datos"
                    continue
            document = ScoreDocument.from_primitive(session.document)
            capture = document.omr_capture
            if capture is None:
                left_out[session.id] = "sin la captura de HOMR (transcrita antes de #403)"
                continue
            try:
                photo = Image.open(io.BytesIO(store.get(session.image_artifact or "")))
                photo.load()
            except (ArtifactNotFound, OSError, ValueError) as exc:
                left_out[session.id] = f"sin la imagen ({type(exc).__name__})"
                continue
            raw = document.score
            try:
                strips = plan_strips(capture, raw, photo.size)
            except StripError as exc:
                left_out[session.id] = str(exc)
                continue
            final = _final_score(raw, edits_repo.list_events(session.id))
            folder = output / "recortes" / session.id
            folder.mkdir(parents=True, exist_ok=True)
            sheet_rows = []
            for strip in strips:
                name = f"s{strip.system}_{_staves_name(strip)}.png"
                photo.crop(strip.box).save(folder / name)
                read, corrected = strip_sequence(raw, strip), strip_sequence(final, strip)
                sheet_rows.append((strip, read, corrected))
                rows.append(
                    {
                        "session_id": session.id,
                        "test_score_id": session.test_score_id,
                        "status": session.status,
                        "source_image_hash": session.image_artifact,
                        "sistema": strip.system,
                        "compases": len(strip.measures),
                        "primer_compas": strip.measures[0],
                        "ultimo_compas": strip.measures[-1],
                        "pentagramas": _staves_name(strip),
                        "lectura_homr": strip.reading,
                        "x0": strip.box[0],
                        "y0": strip.box[1],
                        "x1": strip.box[2],
                        "y1": strip.box[3],
                        "recorte": f"recortes/{session.id}/{name}",
                        "lectura": read,
                        "corregida": corrected,
                        "corregido": read != corrected,
                    }
                )
            xml_folder = output / "musicxml"
            xml_folder.mkdir(parents=True, exist_ok=True)
            (xml_folder / f"{session.id}-homr.musicxml").write_text(
                raw_musicxml(dict(capture)), encoding="utf-8"
            )
            (xml_folder / f"{session.id}-final.musicxml").write_text(
                score_ir_to_musicxml(final), encoding="utf-8"
            )
            if args.laminas:
                sheets = output / "laminas"
                sheets.mkdir(parents=True, exist_ok=True)
                _sheet(photo, sheet_rows).save(sheets / f"{session.id}.png")
            exported.append(session.id)

    output.mkdir(parents=True, exist_ok=True)
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
    content = buffer.getvalue().encode("utf-8")
    (output / "pentagramas.csv").write_bytes(content)
    info = {
        "format_version": FORMAT_VERSION,
        "simulated": False,
        "commit": _commit(),
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "origin": {"database": _safe_url(db_url), "artifacts_dir": Path(artifacts).name},
        "filters": {
            "include_self_registered": args.include_self_registered,
            "include_unfinished": args.include_unfinished,
        },
        "sessions": sorted(exported),
        "left_out": dict(sorted(left_out.items())),
        "strips": len(rows),
        "strips_corrected": sum(1 for row in rows if row["corregido"]),
        "csv_sha256": hashlib.sha256(content).hexdigest(),
    }
    (output / "run_info.json").write_text(
        json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("[export-staves] Recortes escritos.")
    print(f"  sesiones   : {len(exported)}")
    print(f"  tiras      : {len(rows)} ({info['strips_corrected']} con correcciones)")
    print(f"  fuera      : {len(left_out)}")
    for session_id, reason in sorted(left_out.items()):
        print(f"    {session_id}: {reason}")
    print(f"  salida     : {output}")
    return 0


def add_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "export-staves",
        help="Recorta cada pentagrama de las fotos y lo empareja con sus compases (#403).",
    )
    parser.add_argument("--output-dir", required=True, help="Directorio de los recortes y el CSV.")
    parser.add_argument("--db-url", default=None, help="URL de la base (o CADENZA_DATABASE_URL).")
    parser.add_argument(
        "--artifacts-dir",
        default=None,
        help="Directorio de los artefactos, con las fotos (o CADENZA_ARTIFACTS_DIR).",
    )
    parser.add_argument(
        "--include-self-registered",
        action="store_true",
        help="Incluir las cuentas del registro público con el permiso de uso de los datos.",
    )
    parser.add_argument(
        "--include-unfinished",
        action="store_true",
        help="Incluir las sesiones sin finalizar (fuera por defecto).",
    )
    parser.add_argument(
        "--laminas",
        action="store_true",
        help="Escribir además una lámina por sesión: la foto con las cajas y cada tira.",
    )
