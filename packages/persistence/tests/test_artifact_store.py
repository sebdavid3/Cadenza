"""Pruebas del ArtifactStore y su adaptador FilesystemArtifactStore (ADR-0004, #4)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cadenza.application import ArtifactNotFound, InMemoryArtifactStore, compute_sha256
from cadenza.persistence import (
    ArtifactRecord,
    FilesystemArtifactStore,
    create_memory_engine,
    create_schema,
    create_session_factory,
)
from sqlalchemy import inspect, select


def test_in_memory_artifact_store() -> None:
    store = InMemoryArtifactStore()
    content = b"fake-musicxml-content"
    sha = compute_sha256(content)

    assert not store.exists(sha)
    with pytest.raises(ArtifactNotFound) as exc_info:
        store.get(sha)
    assert exc_info.value.sha256 == sha

    # Put y recuperación
    returned_sha = store.put(content, kind="score_xml")
    assert returned_sha == sha
    assert store.exists(sha)
    assert store.get(sha) == content

    # Idempotencia
    assert store.put(content, kind="score_xml") == sha
    assert store.get(sha) == content


def test_filesystem_artifact_store_path_structure(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(root_dir=tmp_path)
    content = b"test binary score image data"
    sha = compute_sha256(content)

    returned_sha = store.put(content, kind="image", media_type="image/png")
    assert returned_sha == sha

    # Estructura requerida: <root_dir>/sha256/ab/cd/<hash>
    expected_rel_path = Path("sha256") / sha[:2] / sha[2:4] / sha
    expected_abs_path = tmp_path / expected_rel_path

    assert expected_abs_path.is_file()
    assert expected_abs_path.read_bytes() == content
    assert store.exists(sha)
    assert store.get(sha) == content


def test_filesystem_artifact_store_idempotency_without_db(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(root_dir=tmp_path)
    content = b"hello duplicate"
    sha = compute_sha256(content)

    # Primera llamada
    store.put(content, kind="image")
    expected_path = tmp_path / "sha256" / sha[:2] / sha[2:4] / sha
    assert expected_path.is_file()

    # Segunda llamada: no falla ni corrompe el archivo existente
    store.put(content, kind="image")
    assert store.get(sha) == content


def test_filesystem_artifact_store_non_existent(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(root_dir=tmp_path)
    fake_sha = "0" * 64

    assert not store.exists(fake_sha)
    with pytest.raises(ArtifactNotFound) as exc_info:
        store.get(fake_sha)
    assert exc_info.value.sha256 == fake_sha


def test_filesystem_artifact_store_with_database_session(tmp_path: Path) -> None:
    engine = create_memory_engine()
    create_schema(engine)
    factory = create_session_factory(engine)

    content = b"test score for db tracking"
    sha = compute_sha256(content)

    with factory() as session:
        store = FilesystemArtifactStore(root_dir=tmp_path, session=session)
        # Primer guardado
        store.put(content, kind="score_xml", media_type="application/vnd.recordare.musicxml+xml")
        session.commit()

    with factory() as session:
        # Verificar fila en BD
        record = session.get(ArtifactRecord, sha)
        assert record is not None
        assert record.sha256 == sha
        assert record.kind == "score_xml"
        assert record.media_type == "application/vnd.recordare.musicxml+xml"
        assert record.size_bytes == len(content)
        assert record.path == f"sha256/{sha[:2]}/{sha[2:4]}/{sha}"
        assert record.created_at is not None

        # Segundo guardado: no duplica fila en BD ni genera error de PK
        store_2 = FilesystemArtifactStore(root_dir=tmp_path, session=session)
        store_2.put(content, kind="score_xml")
        session.commit()

        # Debe seguir existiendo exactamente una sola fila
        all_records = session.scalars(select(ArtifactRecord)).all()
        assert len(all_records) == 1


def test_artifacts_migration_upgrade_and_downgrade() -> None:
    migration_path = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0003_artifacts_table.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0003", migration_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.revision == "0003_artifacts_table"
    assert mod.down_revision == "0002_edit_events_append_only"

    engine = create_memory_engine()
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mod.upgrade()
            inspector = inspect(conn)
            assert "artifacts" in inspector.get_table_names()

            mod.downgrade()
            inspector = inspect(conn)
            assert "artifacts" not in inspector.get_table_names()
