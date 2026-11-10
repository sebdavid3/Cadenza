"""El permiso de uso de los datos solo se guarda (#378, ADR-0064).

El dataset de correcciones (`ml build-dataset`) y la exportación del estudio (`exp_10`) dan lo
mismo con el permiso que sin él: las cuentas del registro público siguen fuera, lo hayan dado o no.
Usar el permiso para incluir datos será otro issue. (El corpus de la capa de sugerencias,
`ml suggestions build-dataset`, se comprueba en `test_suggestions_training.py`.)
"""

from __future__ import annotations

import secrets
from dataclasses import replace
from datetime import UTC, datetime

from cadenza.application import (
    DATA_CONSENT_VERSION,
    InMemoryEditEventRepository,
    InMemorySessionRepository,
    InMemoryUserRepository,
    Role,
    SessionData,
    User,
)
from cadenza.domain import EditEvent, EditOp
from cadenza.learning import RepositoryDatasetReader, TrainingSample
from cadenza.persistence import (
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
    create_memory_engine,
    create_schema,
    create_session_factory,
)

from .support import make_anchor, make_document

CONSENT_AT = datetime(2026, 11, 9, 18, 30, tzinfo=UTC)


def _users(*, consent: bool) -> list[User]:
    users = [
        User(id="ana", username="ana", password_hash=secrets.token_hex(8), role=Role.TRANSCRIPTOR),
        User(
            id="visita",
            username="visita",
            password_hash=secrets.token_hex(8),
            role=Role.TRANSCRIPTOR,
            self_registered=True,
        ),
    ]
    if not consent:
        return users
    return [
        replace(user, data_consent_at=CONSENT_AT, data_consent_version=DATA_CONSENT_VERSION)
        for user in users
    ]


def _session(session_id: str, owner_id: str) -> tuple[SessionData, EditEvent]:
    document = make_document(f"doc-{session_id}")
    session = SessionData(
        id=session_id,
        document_id=document.id,
        omr_engine="fake",
        document=document.to_primitive(),
        image_artifact=f"image-{session_id}",
        status="finalized",
        owner_id=owner_id,
        test_score_id="TS-01",
    )
    edit = EditEvent(
        id=f"edit-{session_id}",
        document_id=document.id,
        seq=1,
        anchor=make_anchor(0),
        op=EditOp.SET_PITCH,
        author=owner_id,
        created_at=datetime(2026, 10, 23, tzinfo=UTC),
        before={"pitch": "C4"},
        after={"pitch": "D4"},
    )
    return session, edit


def test_the_correction_dataset_is_the_same_with_the_permission() -> None:
    sessions = InMemorySessionRepository()
    edits = InMemoryEditEventRepository()
    for session_id, owner in (("estudio", "ana"), ("registro", "visita")):
        session, edit = _session(session_id, owner)
        sessions.add(session, [])
        edits.append(session_id, edit)

    def read(consent: bool) -> tuple[TrainingSample, ...]:
        return RepositoryDatasetReader().read_dataset(
            sessions, edits, user_repository=InMemoryUserRepository(_users(consent=consent))
        )

    with_permission = read(True)
    assert with_permission == read(False)
    assert {sample.document_id for sample in with_permission} == {"doc-estudio"}


def test_the_effort_study_export_takes_the_same_sessions_with_the_permission() -> None:
    from ml.experiments.exp_10_effort_study import _study_sessions

    def chosen(consent: bool) -> list[tuple[str, str]]:
        engine = create_memory_engine()
        create_schema(engine)
        factory = create_session_factory(engine)
        with factory() as db:
            users = SqlAlchemyUserRepository(db)
            for user in _users(consent=consent):
                users.add(user)
            for session_id, owner in (("estudio", "ana"), ("registro", "visita")):
                session, _ = _session(session_id, owner)
                SqlAlchemySessionRepository(db).add(session, [])
            db.commit()
            return [(sess.id, user.id) for sess, user in _study_sessions(db, scores=["TS-01"])]

    assert chosen(consent=True) == chosen(consent=False) == [("estudio", "ana")]
