"""Pruebas del RepositoryDatasetReader con repositorios en memoria y base de datos de prueba."""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction

from cadenza.application.ports import (
    InMemoryEditEventRepository,
    InMemorySessionRepository,
    SessionData,
)
from cadenza.domain import (
    EditEvent,
    EditOp,
    Finding,
    Severity,
)
from cadenza.learning import (
    DatasetBuilder,
    RepositoryDatasetReader,
    dataset_hash,
)
from cadenza.persistence import (
    ArtifactRecord,
    SqlAlchemyEditEventRepository,
    SqlAlchemySessionRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)

from .support import make_anchor, make_document


def test_read_dataset_with_in_memory_repositories() -> None:
    session_repo = InMemorySessionRepository()
    edit_repo = InMemoryEditEventRepository()

    doc1 = make_document("doc-1")
    doc2 = make_document("doc-2")
    doc3 = make_document("doc-3")

    anchor0 = make_anchor(0)
    anchor1 = make_anchor(1)

    # Sesión 1: finalizada, con image_artifact y 2 ediciones
    s1 = SessionData(
        id="sess-1",
        document_id="doc-1",
        omr_engine="fake",
        document=doc1.to_primitive(),
        image_artifact="image_sha_1111",
        status="finalized",
        owner_id="user-a",
    )
    findings_s1 = [
        Finding(anchor=anchor0, rule_id="measure.balance", severity=Severity.ERROR, message="err"),
    ]
    session_repo.add(s1, findings_s1)

    edit_s1_1 = EditEvent(
        id="e1",
        document_id="doc-1",
        seq=1,
        anchor=anchor0,
        op=EditOp.SET_PITCH,
        author="user-a",
        created_at=datetime(2026, 10, 8, tzinfo=UTC),
        before={"pitch": "C4"},
        after={"pitch": "E4"},
    )
    edit_s1_2 = EditEvent(
        id="e2",
        document_id="doc-1",
        seq=2,
        anchor=anchor1,
        op=EditOp.SET_DURATION,
        author="user-a",
        created_at=datetime(2026, 10, 8, tzinfo=UTC),
        before={"duration_beats": Fraction(1, 4)},
        after={"duration_beats": Fraction(1, 2)},
    )
    edit_repo.append("sess-1", edit_s1_1)
    edit_repo.append("sess-1", edit_s1_2)

    # Sesión 2: en estado "correcting" -> debe ser excluida
    s2 = SessionData(
        id="sess-2",
        document_id="doc-2",
        omr_engine="fake",
        document=doc2.to_primitive(),
        image_artifact="image_sha_2222",
        status="correcting",
        owner_id="user-a",
    )
    session_repo.add(s2, ())
    edit_repo.append(
        "sess-2",
        EditEvent(
            id="e3",
            document_id="doc-2",
            seq=1,
            anchor=anchor0,
            op=EditOp.SET_PITCH,
            author="user-a",
            created_at=datetime(2026, 10, 8, tzinfo=UTC),
            before={"pitch": "C4"},
            after={"pitch": "D4"},
        ),
    )

    # Sesión 3: finalizada, de otro usuario (user-b)
    s3 = SessionData(
        id="sess-3",
        document_id="doc-3",
        omr_engine="fake",
        document=doc3.to_primitive(),
        image_artifact="image_sha_3333",
        status="finalized",
        owner_id="user-b",
    )
    session_repo.add(s3, ())
    edit_repo.append(
        "sess-3",
        EditEvent(
            id="e4",
            document_id="doc-3",
            seq=1,
            anchor=anchor0,
            op=EditOp.SET_ACCIDENTAL,
            author="user-b",
            created_at=datetime(2026, 10, 8, tzinfo=UTC),
            before={"accidental": ""},
            after={"accidental": "#"},
        ),
    )

    reader = RepositoryDatasetReader()

    # 1. Lectura de todas las sesiones finalizadas
    samples = reader.read_dataset(session_repo, edit_repo, status="finalized")
    assert len(samples) == 3
    assert [s.document_id for s in samples] == ["doc-1", "doc-1", "doc-3"]
    assert samples[0].image_sha256 == "image_sha_1111"
    assert samples[1].image_sha256 == "image_sha_1111"
    assert samples[2].image_sha256 == "image_sha_3333"
    assert samples[0].correction_magnitude == 4.0  # C4 a E4 = 4 semitonos
    assert samples[1].correction_magnitude == 0.25  # 1/4 a 1/2 = 0.25
    assert samples[2].correction_magnitude == 1.0  # natural a # = 1.0

    # 2. Lectura filtrando por propietario user-a
    samples_user_a = reader.read_dataset(
        session_repo, edit_repo, status="finalized", owner_id="user-a"
    )
    assert len(samples_user_a) == 2
    assert all(s.document_id == "doc-1" for s in samples_user_a)

    # 3. Determinismo del hash del dataset
    h1 = dataset_hash(samples)
    h2 = dataset_hash(samples)
    assert h1 == h2
    assert len(h1) == 64


def test_read_dataset_with_real_database() -> None:
    engine = create_memory_engine()
    create_schema(engine)
    factory = create_session_factory(engine)

    doc = make_document("doc-db-1")
    anchor0 = make_anchor(0)
    anchor1 = make_anchor(1)

    with factory() as db:
        # Registrar imagen en la tabla de artefactos
        artifact = ArtifactRecord(
            sha256="db_image_hash_999",
            kind="image",
            media_type="image/png",
            size_bytes=2048,
            path="sha256/db/im/db_image_hash_999",
        )
        db.add(artifact)
        db.flush()

        session_repo = SqlAlchemySessionRepository(db)
        edit_repo = SqlAlchemyEditEventRepository(db)

        # 1. Sesión finalizada
        s_data = SessionData(
            id="sess-db-1",
            document_id="doc-db-1",
            omr_engine="fake",
            document=doc.to_primitive(),
            image_artifact="db_image_hash_999",
            status="finalized",
            owner_id="investigator",
        )
        session_repo.add(
            s_data,
            [
                Finding(
                    anchor=anchor0,
                    rule_id="measure.balance",
                    severity=Severity.WARNING,
                    message="warn",
                )
            ],
        )

        # 2. Edición 1 y su reversión compensatoria (Edit 2 revierte Edit 1)
        edit_repo.append(
            "sess-db-1",
            EditEvent(
                id="edit-db-1",
                document_id="doc-db-1",
                seq=1,
                anchor=anchor0,
                op=EditOp.SET_PITCH,
                author="investigator",
                created_at=datetime(2026, 10, 8, tzinfo=UTC),
                before={"pitch": "C4"},
                after={"pitch": "D4"},
            ),
        )
        edit_repo.append(
            "sess-db-1",
            EditEvent(
                id="edit-db-2",
                document_id="doc-db-1",
                seq=2,
                anchor=anchor0,
                op=EditOp.SET_PITCH,
                author="investigator",
                created_at=datetime(2026, 10, 8, tzinfo=UTC),
                before={"pitch": "D4"},
                after={"pitch": "C4"},
                reverts_edit_id="edit-db-1",
            ),
        )

        # 3. Edición 3 activa que persiste
        edit_repo.append(
            "sess-db-1",
            EditEvent(
                id="edit-db-3",
                document_id="doc-db-1",
                seq=3,
                anchor=anchor1,
                op=EditOp.SET_KEY,
                author="investigator",
                created_at=datetime(2026, 10, 8, tzinfo=UTC),
                before={"fifths": 0},
                after={"fifths": 3},
            ),
        )
        db.commit()

    # Ahora leemos con una nueva sesión de base de datos
    with factory() as db:
        session_repo = SqlAlchemySessionRepository(db)
        edit_repo = SqlAlchemyEditEventRepository(db)

        reader = RepositoryDatasetReader()
        samples = reader.read_dataset(session_repo, edit_repo, status="finalized")

        # Edit 1 y Edit 2 se anulan mutuamente (#35), solo queda Edit 3
        assert len(samples) == 1
        sample = samples[0]
        assert sample.document_id == "doc-db-1"
        assert sample.op == EditOp.SET_KEY
        assert sample.correction_magnitude == 3.0  # 0 a 3 quintas
        assert sample.image_sha256 == "db_image_hash_999"
        assert sample.seq == 3

        # Verificamos hash determinista
        hash_result = dataset_hash(samples)
        assert len(hash_result) == 64
        assert hash_result == dataset_hash(samples)

        # El método de conveniencia en DatasetBuilder produce exactamente lo mismo
        builder_samples = DatasetBuilder().read_from_repositories(
            session_repo, edit_repo, status="finalized"
        )
        assert builder_samples == samples
