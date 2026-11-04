"""Copias de PostgreSQL con backup_restore.py: volcado real o error claro (#159)."""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Any

import pytest

from scripts.backup_restore import (
    BackupError,
    _libpq_target,
    _libpq_url,
    create_backup,
    restore_backup,
    verify_backup,
)

FAKE_PASSWORD = secrets.token_hex(8)
FAKE_URL = f"postgresql+psycopg2://cadenza:{FAKE_PASSWORD}@postgres:5432/cadenza"


def test_sqlalchemy_url_is_translated_for_libpq() -> None:
    assert _libpq_url(FAKE_URL) == f"postgresql://cadenza:{FAKE_PASSWORD}@postgres:5432/cadenza"
    assert _libpq_url("postgresql://u@h/db") == "postgresql://u@h/db"
    assert _libpq_url("postgres+asyncpg://u@h/db") == "postgres://u@h/db"


def test_backup_without_pg_dump_fails_and_leaves_no_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(*_args: Any, **_kwargs: Any) -> None:
        raise FileNotFoundError("pg_dump")

    monkeypatch.setattr("scripts.backup_restore.subprocess.run", missing)
    archive = tmp_path / "copia.tar.gz"

    with pytest.raises(BackupError, match="No se encontró pg_dump"):
        create_backup(archive, db_url=FAKE_URL, artifacts_dir=tmp_path / "artifacts")

    assert not archive.exists()


def test_pg_dump_failure_is_reported_without_the_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    envs: list[dict[str, str] | None] = []

    def failing(command: list[str], **kwargs: Any) -> None:
        calls.append(command)
        envs.append(kwargs.get("env"))
        stderr = (
            f'pg_dump: error: connection to server at "{_libpq_url(FAKE_URL)}" failed: '
            f"bad password {FAKE_PASSWORD}"
        )
        raise subprocess.CalledProcessError(1, command, stderr=stderr)

    monkeypatch.setattr("scripts.backup_restore.subprocess.run", failing)
    archive = tmp_path / "copia.tar.gz"

    with pytest.raises(BackupError) as excinfo:
        create_backup(archive, db_url=FAKE_URL, artifacts_dir=tmp_path / "artifacts")

    message = str(excinfo.value)
    assert "pg_dump falló (código 1)" in message
    assert "connection to server" in message
    assert FAKE_PASSWORD not in message
    # pg_dump recibe la URL de libpq sin el sufijo del controlador ni la contraseña, que va en
    # PGPASSWORD: en la línea de órdenes se vería en la lista de procesos.
    assert calls[0][0] == "pg_dump"
    assert "postgresql://cadenza@postgres:5432/cadenza" in calls[0]
    assert not any(FAKE_PASSWORD in argument for argument in calls[0])
    assert envs[0] is not None and envs[0]["PGPASSWORD"] == FAKE_PASSWORD
    assert not archive.exists()


def test_libpq_target_separates_the_password() -> None:
    assert _libpq_target(FAKE_URL) == ("postgresql://cadenza@postgres:5432/cadenza", FAKE_PASSWORD)
    assert _libpq_target("postgresql+psycopg2://u:p%40ss@h:5432/db") == (
        "postgresql://u@h:5432/db",
        "p@ss",
    )
    assert _libpq_target("postgresql://u@h/db") == ("postgresql://u@h/db", None)
    # Caracteres sin codificar que cortarían el análisis de una URL: la contraseña no puede
    # quedarse en la URL de la línea de órdenes.
    for raw in ("p#x", "pa?ss", "a/b", "p@ss:w"):
        assert _libpq_target(f"postgresql://u:{raw}@h:5432/db?sslmode=require") == (
            "postgresql://u@h:5432/db?sslmode=require",
            raw,
        )
    assert _libpq_target("postgresql://u:pw@[::1]:5432/db") == (
        "postgresql://u@[::1]:5432/db",
        "pw",
    )


def test_verify_rejects_a_postgresql_backup_that_is_not_a_dump(tmp_path: Path) -> None:
    # Las copias antiguas sin pg_dump guardaban un comentario de texto en lugar del volcado.
    staging = tmp_path / "staging"
    (staging / "database").mkdir(parents=True)
    (staging / "artifacts").mkdir()
    dump = staging / "database" / "cadenza.dump"
    dump.write_text("-- Backup fallback for postgresql://...\n", encoding="utf-8")
    from scripts.backup_restore import compute_sha256

    manifest = (
        '{"version": "1.0.0", "timestamp": "2026-10-23T00:00:00+00:00", "db_type": "postgresql", '
        f'"db_file": "cadenza.dump", "db_sha256": "{compute_sha256(dump)}", "artifacts": {{}}}}'
    )
    (staging / "manifest.json").write_text(manifest, encoding="utf-8")
    archive = tmp_path / "antigua.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name in ("manifest.json", "database", "artifacts"):
            tar.add(staging / name, arcname=name)

    with pytest.raises(ValueError, match="no es un volcado de pg_dump"):
        verify_backup(archive)


def test_restore_failure_is_reported_and_leaves_the_artifacts_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_dump(command: list[str], **_kwargs: Any) -> None:
        Path(command[command.index("-f") + 1]).write_bytes(b"PGDMP" + b"\0" * 16)

    monkeypatch.setattr("scripts.backup_restore.subprocess.run", fake_dump)
    artifacts = tmp_path / "artifacts"
    (artifacts / "sha256").mkdir(parents=True)
    (artifacts / "sha256" / "abc").write_bytes(b"imagen")
    archive = tmp_path / "copia.tar.gz"
    create_backup(archive, db_url=FAKE_URL, artifacts_dir=artifacts)
    commands: list[list[str]] = []

    def failing_restore(command: list[str], **_kwargs: Any) -> None:
        commands.append(command)
        raise subprocess.CalledProcessError(
            1, command, stderr="pg_restore: error: could not connect"
        )

    monkeypatch.setattr("scripts.backup_restore.subprocess.run", failing_restore)
    restored = tmp_path / "restored"
    with pytest.raises(BackupError, match="pg_restore falló"):
        restore_backup(archive, db_url=FAKE_URL, artifacts_dir=restored)

    # Una sola transacción que se detiene en el primer error: la base queda como estaba.
    assert "--single-transaction" in commands[0] and "--exit-on-error" in commands[0]
    # La base se restaura antes que los artefactos: si falla, no se copia ninguno.
    assert not any(path.is_file() for path in restored.rglob("*"))


def test_a_failed_archive_write_leaves_no_partial_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_dump(command: list[str], **_kwargs: Any) -> None:
        Path(command[command.index("-f") + 1]).write_bytes(b"PGDMP" + b"\0" * 16)

    def full_disk(*_args: Any, **_kwargs: Any) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("scripts.backup_restore.subprocess.run", fake_dump)
    archive = tmp_path / "copia.tar.gz"
    archive.write_bytes(b"copia anterior")
    monkeypatch.setattr("scripts.backup_restore.os.replace", full_disk)

    with pytest.raises(OSError, match="No space left"):
        create_backup(archive, db_url=FAKE_URL, artifacts_dir=tmp_path / "artifacts")

    assert archive.read_bytes() == b"copia anterior"
    assert not (tmp_path / "copia.tar.gz.tmp").exists()


def _live_postgres_url() -> str | None:
    return os.getenv("CADENZA_TEST_POSTGRES_URL")


def test_real_backup_and_restore_round_trip(tmp_path: Path) -> None:
    """Ida y vuelta real con el PostgreSQL y el pg_dump de la CI."""
    url = _live_postgres_url()
    tools = shutil.which("pg_dump") and shutil.which("pg_restore")
    if not url or not tools:
        if os.getenv("CADENZA_REQUIRE_POSTGRES") == "1":
            pytest.fail("La CI exige PostgreSQL y pg_dump para la ida y vuelta de las copias")
        pytest.skip("Sin CADENZA_TEST_POSTGRES_URL o sin pg_dump/pg_restore en el PATH")

    from sqlalchemy import create_engine, text

    engine = create_engine(url, future=True)
    table = f"backup_check_{secrets.token_hex(4)}"
    note = f"Allegro {secrets.token_hex(4)}"
    with engine.begin() as conn:
        conn.execute(text(f"CREATE TABLE {table} (id SERIAL PRIMARY KEY, note TEXT)"))
        conn.execute(text(f"INSERT INTO {table} (note) VALUES (:note)"), {"note": note})
    try:
        artifacts = tmp_path / "artifacts"
        (artifacts / "sha256").mkdir(parents=True)
        (artifacts / "sha256" / "abc").write_bytes(b"imagen")
        archive = tmp_path / "copia.tar.gz"

        create_backup(archive, db_url=url, artifacts_dir=artifacts)
        result = verify_backup(archive)
        assert result["db_type"] == "postgresql"

        with engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {table}"))
        restored = tmp_path / "restored"
        restore_backup(archive, db_url=url, artifacts_dir=restored)

        with engine.connect() as conn:
            notes = conn.execute(text(f"SELECT note FROM {table}")).scalars().all()
        assert notes == [note]
        assert (restored / "sha256" / "abc").read_bytes() == b"imagen"
    finally:
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
        engine.dispose()
