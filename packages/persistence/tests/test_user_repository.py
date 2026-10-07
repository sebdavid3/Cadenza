"""Pruebas para UserRepository y filtrado de sesiones por propietario (ADR-0012, #43)."""

from __future__ import annotations

import pytest
from cadenza.application import (
    DuplicateUsername,
    InMemoryUserRepository,
    Role,
    SessionData,
    User,
)
from cadenza.persistence import (
    Base,
    SessionFactory,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_session_factory,
)


@pytest.fixture
def db_session_factory() -> SessionFactory:
    engine = create_memory_engine()
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


def test_in_memory_user_repository() -> None:
    repo = InMemoryUserRepository()
    user = User(
        id="usr-1",
        username="alice",
        password_hash="hash_alice",
        role=Role.TRANSCRIPTOR,
    )
    repo.add(user)

    assert repo.get("usr-1") == user
    assert repo.get_by_username("alice") == user
    assert repo.get("non-existent") is None
    assert repo.get_by_username("bob") is None

    with pytest.raises(DuplicateUsername):
        repo.add(
            User(
                id="usr-2",
                username="alice",
                password_hash="another_hash",
                role=Role.INVESTIGADOR,
            )
        )


def test_sqlalchemy_user_repository(db_session_factory: SessionFactory) -> None:
    with db_session_factory() as db:
        repo = SqlAlchemyUserRepository(db)
        user = User(
            id="usr-sql-1",
            username="carol",
            password_hash="hash_carol",
            role=Role.INVESTIGADOR,
        )
        saved = repo.add(user)
        db.commit()

        assert saved.id == "usr-sql-1"
        assert saved.username == "carol"
        assert saved.role == Role.INVESTIGADOR
        assert saved.active is True
        assert saved.created_at is not None

    with db_session_factory() as db:
        repo = SqlAlchemyUserRepository(db)
        found_id = repo.get("usr-sql-1")
        assert found_id is not None
        assert found_id.username == "carol"
        assert found_id.role == Role.INVESTIGADOR

        found_username = repo.get_by_username("carol")
        assert found_username is not None
        assert found_username.id == "usr-sql-1"

        assert repo.get("missing") is None
        assert repo.get_by_username("missing") is None

        with pytest.raises(DuplicateUsername):
            repo.add(
                User(
                    id="usr-sql-2",
                    username="carol",
                    password_hash="hash_other",
                    role=Role.TRANSCRIPTOR,
                )
            )


def test_session_repository_list_and_owner_filtering(db_session_factory: SessionFactory) -> None:
    with db_session_factory() as db:
        user_repo = SqlAlchemyUserRepository(db)
        session_repo = SqlAlchemySessionRepository(db)

        # Crear dos usuarios
        u1 = user_repo.add(
            User(id="u1", username="transcriptor1", password_hash="h1", role=Role.TRANSCRIPTOR)
        )
        u2 = user_repo.add(
            User(id="u2", username="investigador1", password_hash="h2", role=Role.INVESTIGADOR)
        )

        # Crear 2 sesiones para u1 y 1 sesión para u2
        s1 = SessionData(
            id="s1",
            document_id="doc1",
            omr_engine="fake",
            document={"k": 1},
            owner_id=u1.id,
        )
        s2 = SessionData(
            id="s2",
            document_id="doc2",
            omr_engine="fake",
            document={"k": 2},
            owner_id=u1.id,
        )
        s3 = SessionData(
            id="s3",
            document_id="doc3",
            omr_engine="fake",
            document={"k": 3},
            owner_id=u2.id,
        )

        session_repo.add(s1, findings=[])
        session_repo.add(s2, findings=[])
        session_repo.add(s3, findings=[])
        db.commit()

    with db_session_factory() as db:
        session_repo = SqlAlchemySessionRepository(db)

        # Listar todas
        all_sessions = session_repo.list()
        assert len(all_sessions) == 3
        ids = [s.id for s in all_sessions]
        assert "s1" in ids and "s2" in ids and "s3" in ids

        # Filtrar por u1
        u1_sessions = session_repo.list(owner_id="u1")
        assert len(u1_sessions) == 2
        assert {s.id for s in u1_sessions} == {"s1", "s2"}
        for s in u1_sessions:
            assert s.owner_id == "u1"

        # Filtrar por u2
        u2_sessions = session_repo.list(owner_id="u2")
        assert len(u2_sessions) == 1
        assert u2_sessions[0].id == "s3"
        assert u2_sessions[0].owner_id == "u2"

        # Filtrar por un usuario sin sesiones
        empty = session_repo.list(owner_id="unknown")
        assert len(empty) == 0
