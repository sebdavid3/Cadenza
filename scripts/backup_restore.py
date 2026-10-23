"""Herramienta de copia de seguridad y restauración del backend de Cadenza (#40, D44).

Permite crear snapshots atómicos y comprimidos (.tar.gz) de la base de datos
(SQLite o PostgreSQL) y del repositorio de artefactos (`ArtifactStore`), verificar
la integridad de las copias mediante hashes SHA-256 en un manifiesto y restaurar
el estado del sistema de forma reproducible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote


def compute_sha256(file_path: Path) -> str:
    """Calcula el digest SHA-256 hexadecimal de un archivo."""
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _parse_sqlite_path(db_url: str) -> Path | None:
    """Extrae la ruta al archivo SQLite a partir de la URL SQLAlchemy."""
    if "sqlite" not in db_url:
        return None
    # Eliminar prefijos comunes sqlite:/// o sqlite+pysqlite:///
    clean = db_url.split(":///")[-1]
    return Path(clean)


class BackupError(RuntimeError):
    """La copia o la restauración no se pudo completar."""


_PG_DUMP_MAGIC = b"PGDMP"


def _libpq_url(db_url: str) -> str:
    """Traduce una URL de SQLAlchemy (`postgresql+psycopg2://...`) a la que entiende libpq.

    `pg_dump` y `pg_restore` no reconocen el sufijo del controlador (#159).
    """
    scheme, sep, rest = db_url.partition("://")
    if not sep:
        return db_url
    return f"{scheme.split('+', 1)[0]}://{rest}"


def _libpq_target(db_url: str) -> tuple[str, str | None]:
    """URL de libpq sin la contraseña, y la contraseña aparte (para `PGPASSWORD`).

    En la línea de órdenes, la contraseña quedaría a la vista en la lista de procesos.
    """
    url = _libpq_url(db_url)
    scheme, sep, rest = url.partition("://")
    # La última «@» separa las credenciales del servidor: el servidor y la ruta no llevan «@», y
    # la contraseña sí puede llevar «@», «#», «/» o «?» aunque no estén codificados.
    userinfo, at, location = rest.rpartition("@")
    if not sep or not at or ":" not in userinfo:
        return url, None
    user, _, password = userinfo.partition(":")
    target = f"{scheme}://{user}@{location}" if user else f"{scheme}://{location}"
    return target, unquote(password)


def _redact(text: str, db_url: str) -> str:
    """Quita la URL y la contraseña de un mensaje de pg_dump o pg_restore."""
    for url in {db_url, _libpq_url(db_url)}:
        text = text.replace(url, "<CADENZA_DATABASE_URL>")
    _, password = _libpq_target(db_url)
    # Una contraseña muy corta aparecería por casualidad en cualquier texto.
    if password and len(password) >= 4:
        for form in {password, quote(password, safe="")}:
            text = text.replace(form, "***")
    return text


def _run_pg_tool(command: list[str], db_url: str) -> None:
    """Ejecuta pg_dump o pg_restore y convierte cualquier fallo en `BackupError`.

    `command` lleva la URL sin contraseña (`_libpq_target`); la contraseña va en `PGPASSWORD`.
    """
    _, password = _libpq_target(db_url)
    env = {**os.environ, "PGPASSWORD": password} if password else None
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, env=env)
    except FileNotFoundError as err:
        raise BackupError(
            f"No se encontró {command[0]}: instálalo con la misma versión que el servidor "
            "PostgreSQL o usa el servicio backup de docker-compose.prod.yml."
        ) from err
    except subprocess.CalledProcessError as err:
        detail = _redact((err.stderr or "").strip(), db_url)
        raise BackupError(f"{command[0]} falló (código {err.returncode}): {detail}") from err


def _safe_extractall(tar: tarfile.TarFile, target_path: Path) -> None:
    """Extrae de forma segura el archivo tar usando el filtro de datos de Python 3.12+."""
    tar.extractall(target_path, filter="data")


def create_backup(
    output_path: Path,
    *,
    db_url: str = "sqlite+pysqlite:///./cadenza.db",
    artifacts_dir: Path = Path("./data/artifacts"),
) -> Path:
    """Genera un archivo comprimido .tar.gz con la base de datos, artefactos y manifiesto."""
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="cadenza-backup-") as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        db_dir = tmpdir / "database"
        db_dir.mkdir(parents=True, exist_ok=True)
        art_dir = tmpdir / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)

        manifest: dict[str, Any] = {
            "version": "1.0.0",
            "timestamp": datetime.now(UTC).isoformat(),
            "db_type": "unknown",
            "db_file": "",
            "db_sha256": "",
            "artifacts": {},
        }

        # 1. Copia de base de datos
        sqlite_file = _parse_sqlite_path(db_url)
        if sqlite_file is not None:
            manifest["db_type"] = "sqlite"
            manifest["db_file"] = "cadenza.sqlite"
            target_sqlite = db_dir / "cadenza.sqlite"

            if sqlite_file.exists():
                # Realizar backup consistente con la API de sqlite3
                src_conn = sqlite3.connect(sqlite_file)
                dst_conn = sqlite3.connect(target_sqlite)
                with dst_conn:
                    src_conn.backup(dst_conn)
                src_conn.close()
                dst_conn.close()
            else:
                # Si no existe archivo físico todavía, crear base vacía
                empty_conn = sqlite3.connect(target_sqlite)
                empty_conn.close()

            manifest["db_sha256"] = compute_sha256(target_sqlite)
        else:
            manifest["db_type"] = "postgresql"
            manifest["db_file"] = "cadenza.dump"
            target_dump = db_dir / "cadenza.dump"
            # Sin pg_dump no hay copia: antes se escribía un archivo de texto en su lugar y la
            # copia parecía válida sin contener datos (#159).
            _run_pg_tool(
                ["pg_dump", "-Fc", "-d", _libpq_target(db_url)[0], "-f", str(target_dump)], db_url
            )
            manifest["db_sha256"] = compute_sha256(target_dump)

        # 2. Copia de artefactos
        artifacts_manifest: dict[str, str] = {}
        if artifacts_dir.exists():
            for root, _, files in os.walk(artifacts_dir):
                for fname in files:
                    full_p = Path(root) / fname
                    rel_p = full_p.relative_to(artifacts_dir)
                    dst_p = art_dir / rel_p
                    dst_p.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(full_p, dst_p)
                    rel_key = str(rel_p).replace("\\", "/")
                    artifacts_manifest[rel_key] = compute_sha256(full_p)

        manifest["artifacts"] = artifacts_manifest
        manifest["artifacts_count"] = len(artifacts_manifest)

        # 3. Guardar manifiesto
        manifest_file = tmpdir / "manifest.json"
        with manifest_file.open("w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)

        # 4. Empaquetar en tar.gz: primero en un archivo temporal junto al destino y después se
        # renombra, para que un fallo a medias (disco lleno) no deje una copia rota con el nombre
        # final ni pise una anterior.
        partial = output_path.with_name(output_path.name + ".tmp")
        try:
            with tarfile.open(partial, "w:gz") as tar:
                tar.add(manifest_file, arcname="manifest.json")
                tar.add(db_dir, arcname="database")
                tar.add(art_dir, arcname="artifacts")
            os.replace(partial, output_path)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise

    return output_path


def verify_backup(archive_path: Path) -> dict[str, Any]:
    """Verifica la integridad de una copia comprobando el manifiesto y hashes SHA-256."""
    archive_path = archive_path.resolve()
    if not archive_path.exists():
        raise FileNotFoundError(f"Archivo de copia no encontrado: {archive_path}")

    with tempfile.TemporaryDirectory(prefix="cadenza-verify-") as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        with tarfile.open(archive_path, "r:gz") as tar:
            _safe_extractall(tar, tmpdir)

        manifest_path = tmpdir / "manifest.json"
        if not manifest_path.exists():
            raise ValueError("Copia corrupta o inválida: falta manifest.json")

        with manifest_path.open("r", encoding="utf-8") as f:
            manifest = json.load(f)

        db_file = tmpdir / "database" / manifest.get("db_file", "")
        if not db_file.exists():
            raise ValueError(f"Archivo de base de datos ausente: {manifest.get('db_file')}")

        calculated_db_hash = compute_sha256(db_file)
        if calculated_db_hash != manifest.get("db_sha256"):
            raise ValueError(
                f"Hash mismatch en base de datos: esperado {manifest.get('db_sha256')}, "
                f"obtenido {calculated_db_hash}"
            )
        # Un volcado de pg_dump en formato custom empieza por «PGDMP». Las copias hechas sin
        # pg_dump guardaban un comentario de texto con su hash, que pasaba la comprobación (#159).
        if manifest.get("db_type") == "postgresql":
            with db_file.open("rb") as f:
                if f.read(5) != _PG_DUMP_MAGIC:
                    raise ValueError(
                        f"{manifest.get('db_file')} no es un volcado de pg_dump: la copia no "
                        "contiene los datos de PostgreSQL."
                    )

        artifacts = manifest.get("artifacts", {})
        for rel_str, expected_hash in artifacts.items():
            art_file = tmpdir / "artifacts" / rel_str
            if not art_file.exists():
                raise ValueError(f"Artefacto ausente: {rel_str}")
            calculated_art_hash = compute_sha256(art_file)
            if calculated_art_hash != expected_hash:
                raise ValueError(
                    f"Hash mismatch en artefacto {rel_str}: esperado {expected_hash}, "
                    f"obtenido {calculated_art_hash}"
                )

    return {
        "status": "valid",
        "timestamp": manifest.get("timestamp"),
        "db_type": manifest.get("db_type"),
        "artifacts_verified": len(manifest.get("artifacts", {})),
    }


def restore_backup(
    archive_path: Path,
    *,
    db_url: str = "sqlite+pysqlite:///./cadenza.db",
    artifacts_dir: Path = Path("./data/artifacts"),
    force: bool = False,
) -> None:
    """Restaura la base de datos y los artefactos tras verificar su integridad."""
    verify_backup(archive_path)

    archive_path = archive_path.resolve()
    artifacts_dir = artifacts_dir.resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="cadenza-restore-") as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        with tarfile.open(archive_path, "r:gz") as tar:
            _safe_extractall(tar, tmpdir)

        with (tmpdir / "manifest.json").open("r", encoding="utf-8") as f:
            manifest = json.load(f)

        # 1. Restaurar la base de datos primero: si falla, los artefactos quedan como estaban.
        db_file = tmpdir / "database" / manifest.get("db_file", "")
        sqlite_file = _parse_sqlite_path(db_url)
        if sqlite_file is not None:
            sqlite_file = sqlite_file.resolve()
            if sqlite_file.exists() and not force:
                raise FileExistsError(
                    f"El archivo destino SQLite ya existe ({sqlite_file}). "
                    "Use --force para sobrescribirlo."
                )
            sqlite_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db_file, sqlite_file)
        else:
            # PostgreSQL: se borran los objetos existentes y se recrean desde el volcado, en una
            # sola transacción que se detiene en el primer error: si falla, la base queda como
            # estaba.
            _run_pg_tool(
                [
                    "pg_restore",
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    "--single-transaction",
                    "--exit-on-error",
                    "-d",
                    _libpq_target(db_url)[0],
                    str(db_file),
                ],
                db_url,
            )

        # 2. Restaurar los artefactos, direccionados por contenido: copiarlos sobre los existentes
        # no cambia ninguno que ya estuviera.
        src_art = tmpdir / "artifacts"
        if src_art.exists():
            for root, _, files in os.walk(src_art):
                for fname in files:
                    full_p = Path(root) / fname
                    rel_p = full_p.relative_to(src_art)
                    dst_p = artifacts_dir / rel_p
                    dst_p.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(full_p, dst_p)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Utilidad de copia de seguridad y restauración de Cadenza."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Backup
    backup_p = subparsers.add_parser("backup", help="Crear una copia de seguridad.")
    backup_p.add_argument(
        "--output",
        "-o",
        type=Path,
        required=True,
        help="Ruta del archivo de salida .tar.gz",
    )
    backup_p.add_argument(
        "--db-url",
        default=os.getenv("CADENZA_DATABASE_URL", "sqlite+pysqlite:///./cadenza.db"),
        help="URL de conexión a la base de datos.",
    )
    backup_p.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path(os.getenv("CADENZA_ARTIFACTS_DIR", "./data/artifacts")),
        help="Directorio raíz del ArtifactStore.",
    )

    # Verify
    verify_p = subparsers.add_parser("verify", help="Verificar la integridad de una copia.")
    verify_p.add_argument(
        "--archive",
        "-a",
        type=Path,
        required=True,
        help="Ruta de la copia .tar.gz a verificar.",
    )

    # Restore
    restore_p = subparsers.add_parser("restore", help="Restaurar el sistema a partir de una copia.")
    restore_p.add_argument(
        "--archive",
        "-a",
        type=Path,
        required=True,
        help="Ruta de la copia .tar.gz a restaurar.",
    )
    restore_p.add_argument(
        "--db-url",
        default=os.getenv("CADENZA_DATABASE_URL", "sqlite+pysqlite:///./cadenza.db"),
        help="URL de conexión destino.",
    )
    restore_p.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path(os.getenv("CADENZA_ARTIFACTS_DIR", "./data/artifacts")),
        help="Directorio raíz del ArtifactStore destino.",
    )
    restore_p.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Sobrescribir base de datos existente si es SQLite.",
    )

    args = parser.parse_args()

    try:
        _run_command(args)
    except (BackupError, ValueError, OSError, tarfile.TarError) as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


def _run_command(args: argparse.Namespace) -> None:
    if args.command == "backup":
        out = create_backup(
            args.output,
            db_url=args.db_url,
            artifacts_dir=args.artifacts_dir,
        )
        print(f"Copia creada exitosamente en: {out}")
    elif args.command == "verify":
        res = verify_backup(args.archive)
        print(f"Copia válida: {json.dumps(res, indent=2)}")
    elif args.command == "restore":
        restore_backup(
            args.archive,
            db_url=args.db_url,
            artifacts_dir=args.artifacts_dir,
            force=args.force,
        )
        print("Restauración completada exitosamente.")


if __name__ == "__main__":
    main()
