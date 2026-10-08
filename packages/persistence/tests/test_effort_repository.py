"""Pruebas del adaptador SqlAlchemyEffortRepository y el modelo EffortMetricsRecord (#13)."""

from datetime import UTC, datetime

from cadenza.application import EffortMetricsData
from cadenza.persistence import (
    SqlAlchemyEffortRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
    session_scope,
)
from cadenza.persistence.models import Session, UserRecord


def test_effort_repository_add_and_query() -> None:
    engine = create_memory_engine()
    create_schema(engine)
    factory = create_session_factory(engine)

    with session_scope(factory) as db:
        user = UserRecord(
            id="u1",
            username="user1",
            password_hash="hash",
            role="transcriptor",
        )
        db.add(user)
        session = Session(
            id="s1",
            owner_id="u1",
            document_id="doc-1",
            omr_engine="fake",
            document={"score": {}},
        )
        db.add(session)
        db.flush()

        repo = SqlAlchemyEffortRepository(db)

        # 1. Agregar primera medición
        m1 = EffortMetricsData(
            id="eff-1",
            session_id="s1",
            duration_ms=45000,
            time_to_first_edit_ms=12000,
            interventions={"1": 3, "2": 1},
            created_at=datetime.now(UTC),
        )
        saved1 = repo.add(m1)
        assert saved1.id == "eff-1"
        assert saved1.duration_ms == 45000
        assert saved1.interventions == {"1": 3, "2": 1}

        # 2. Agregar segunda medición para la misma sesión
        m2 = EffortMetricsData(
            id="eff-2",
            session_id="s1",
            duration_ms=60000,
            time_to_first_edit_ms=12000,
            interventions={"1": 3, "2": 2, "3": 1},
            created_at=datetime.now(UTC),
        )
        saved2 = repo.add(m2)
        assert saved2.id == "eff-2"

        # 3. list_by_session
        all_metrics = repo.list_by_session("s1")
        assert len(all_metrics) == 2
        assert all_metrics[0].id == "eff-1"
        assert all_metrics[1].id == "eff-2"

        # 4. get_latest
        latest = repo.get_latest("s1")
        assert latest is not None
        assert latest.id == "eff-2"
        assert latest.duration_ms == 60000

        # 5. Sesión sin métricas devuelve tupla vacía y None
        assert repo.list_by_session("non-existent") == ()
        assert repo.get_latest("non-existent") is None
