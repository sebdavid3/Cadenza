"""Tests de copia de seguridad y restauración (#40, D44)."""

import argparse
import os
import sqlite3
import tarfile
from pathlib import Path

import pytest

from scripts.backup_restore import (
    BackupError,
    _parse_owner,
    _safe_extractall,
    create_backup,
    restore_backup,
    verify_backup,
)


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


def _backup_with_a_stored_artifact(tmp_path: Path) -> Path:
    """Copia de una base SQLite y un artefacto guardado como lo guarda el ArtifactStore."""
    db_file = tmp_path / "origen.db"
    conn = sqlite3.connect(db_file)
    with conn:
        conn.execute("CREATE TABLE t (x INT);")
    conn.close()
    artifacts_dir = tmp_path / "origen_artefactos"
    stored = artifacts_dir / "sha256" / "ab" / "cd" / "abcd1234"
    stored.parent.mkdir(parents=True)
    stored.write_bytes(b"artefacto")
    archive_path = tmp_path / "copia.tar.gz"
    create_backup(archive_path, db_url=f"sqlite:///{db_file}", artifacts_dir=artifacts_dir)
    return archive_path


def _restore_recording_chown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    euid: int,
    owner: tuple[int, int] | None = None,
) -> tuple[Path, list[tuple[Path, int, int]]]:
    archive_path = _backup_with_a_stored_artifact(tmp_path)
    target = tmp_path / "artefactos"
    target.mkdir()
    (target / "otro").write_bytes(b"de antes")
    calls: list[tuple[Path, int, int]] = []

    def chown(path: Path, uid: int, gid: int, *, follow_symlinks: bool = True) -> None:
        # Como root, tarfile también da a cada miembro su dueño al extraer en la carpeta temporal.
        if Path(path).is_relative_to(target):
            assert follow_symlinks is False
            calls.append((Path(path), uid, gid))

    monkeypatch.setattr(os, "geteuid", lambda: euid, raising=False)
    monkeypatch.setattr(os, "chown", chown, raising=False)
    restore_backup(
        archive_path,
        db_url=f"sqlite:///{tmp_path / 'restaurada.db'}",
        artifacts_dir=target,
        force=True,
        owner=owner,
    )
    return target, calls


def _restored_paths(target: Path) -> set[Path]:
    """La carpeta de artefactos, el artefacto restaurado y las carpetas entre ambos."""
    return {
        target,
        target / "sha256",
        target / "sha256" / "ab",
        target / "sha256" / "ab" / "cd",
        target / "sha256" / "ab" / "cd" / "abcd1234",
    }


def test_restore_as_root_gives_the_artifacts_to_the_owner_of_their_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # En el despliegue se restaura como root y la API corre con su propio usuario (D57, #192):
    # las carpetas que crea la restauración han de ser suyas, o la API no podría guardar nada
    # nuevo en ellas. Lo que no viene de la copia («otro») no se toca.
    target, calls = _restore_recording_chown(tmp_path, monkeypatch, euid=0)

    folder = target.stat()
    assert {path for path, _, _ in calls} == _restored_paths(target)
    assert {(uid, gid) for _, uid, gid in calls} == {(folder.st_uid, folder.st_gid)}


def test_restore_as_root_gives_the_artifacts_to_the_given_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Si la restauración crea el volumen, la carpeta es de root: el despliegue nombra al dueño
    # (CADENZA_ARTIFACTS_OWNER) y la carpeta pasa también a ser suya.
    target, calls = _restore_recording_chown(tmp_path, monkeypatch, euid=0, owner=(10001, 10001))

    assert {path for path, _, _ in calls} == _restored_paths(target)
    assert {(uid, gid) for _, uid, gid in calls} == {(10001, 10001)}


def test_restore_without_root_leaves_the_owners_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sin ser root, lo restaurado ya es de quien restaura, y no se puede dar a otro.
    target, calls = _restore_recording_chown(tmp_path, monkeypatch, euid=1000, owner=(10001, 10001))

    assert (target / "sha256" / "ab" / "cd" / "abcd1234").read_bytes() == b"artefacto"
    assert calls == []


def test_restore_refuses_a_destination_that_leaves_the_artifacts_folder(tmp_path: Path) -> None:
    # Con la API sin root, un enlace simbólico plantado en el volumen no debe llevar la
    # restauración, que corre como root, fuera de la carpeta de artefactos.
    archive_path = _backup_with_a_stored_artifact(tmp_path)
    target = tmp_path / "artefactos"
    outside = tmp_path / "fuera"
    (target / "sha256").mkdir(parents=True)
    outside.mkdir()
    try:
        (target / "sha256" / "ab").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Este sistema no permite crear enlaces simbólicos sin privilegios")
    restored_db = tmp_path / "restaurada.db"

    with pytest.raises(BackupError, match="saldría de"):
        restore_backup(
            archive_path, db_url=f"sqlite:///{restored_db}", artifacts_dir=target, force=True
        )

    assert list(outside.iterdir()) == []
    assert not restored_db.exists()


def test_owner_is_read_as_uid_and_gid() -> None:
    assert _parse_owner("10001:10001") == (10001, 10001)
    for wrong in ("10001", "cadenza:cadenza", "10001:", ":10001"):
        with pytest.raises(argparse.ArgumentTypeError, match="UID:GID"):
            _parse_owner(wrong)
