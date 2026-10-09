"""Tests de copia de seguridad y restauración (#40, D44)."""

import sqlite3
import tarfile
from pathlib import Path

import pytest

from scripts.backup_restore import _safe_extractall, create_backup, restore_backup, verify_backup


def test_backup_and_restore_sqlite_with_artifacts(tmp_path: Path) -> None:
    # 1. Preparar base de datos SQLite con datos
    db_file = tmp_path / "original.db"
    conn = sqlite3.connect(db_file)
    with conn:
        conn.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, note TEXT);")
        conn.execute("INSERT INTO test_data (note) VALUES ('Allegro con brio');")
    conn.close()

    # 2. Preparar artefactos
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    sample_art = artifacts_dir / "sample.txt"
    sample_art.write_text("dummy artifact content", encoding="utf-8")

    # 3. Crear backup
    archive_path = tmp_path / "backup.tar.gz"
    create_backup(
        archive_path,
        db_url=f"sqlite:///{db_file}",
        artifacts_dir=artifacts_dir,
    )
    assert archive_path.exists()

    # 4. Verificar backup
    verification = verify_backup(archive_path)
    assert verification["status"] == "valid"
    assert verification["db_type"] == "sqlite"
    assert verification["artifacts_verified"] == 1

    # 5. Restaurar en nuevas rutas
    restore_db = tmp_path / "restored.db"
    restore_artifacts = tmp_path / "restored_artifacts"

    restore_backup(
        archive_path,
        db_url=f"sqlite:///{restore_db}",
        artifacts_dir=restore_artifacts,
        force=True,
    )

    # Comprobar base de datos restaurada
    assert restore_db.exists()
    r_conn = sqlite3.connect(restore_db)
    cursor = r_conn.cursor()
    cursor.execute("SELECT note FROM test_data;")
    rows = cursor.fetchall()
    r_conn.close()
    assert rows == [("Allegro con brio",)]

    # Comprobar artefactos restaurados
    restored_file = restore_artifacts / "sample.txt"
    assert restored_file.exists()
    assert restored_file.read_text(encoding="utf-8") == "dummy artifact content"


def test_verify_backup_detects_tampered_archive(tmp_path: Path) -> None:
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(db_file)
    with conn:
        conn.execute("CREATE TABLE t (x INT);")
    conn.close()

    artifacts_dir = tmp_path / "arts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    archive_path = tmp_path / "backup_tampered.tar.gz"
    create_backup(
        archive_path,
        db_url=f"sqlite:///{db_file}",
        artifacts_dir=artifacts_dir,
    )

    # Extraer, modificar la base de datos y reempaquetar sin actualizar el hash
    extract_dir = tmp_path / "extracted"
    with tarfile.open(archive_path, "r:gz") as tar:
        _safe_extractall(tar, extract_dir)

    tampered_db = extract_dir / "database" / "cadenza.sqlite"
    tampered_db.write_bytes(b"tampered content not matching original sha256")

    tampered_archive = tmp_path / "tampered.tar.gz"
    with tarfile.open(tampered_archive, "w:gz") as tar:
        tar.add(extract_dir / "manifest.json", arcname="manifest.json")
        tar.add(extract_dir / "database", arcname="database")
        tar.add(extract_dir / "artifacts", arcname="artifacts")

    with pytest.raises(ValueError, match="Hash mismatch en base de datos"):
        verify_backup(tampered_archive)
