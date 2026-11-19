"""El permiso de uso de los datos solo se guarda (#378, ADR-0065).

El dataset de correcciones (`ml build-dataset`) da lo
mismo con el permiso que sin él: las cuentas del registro público siguen fuera, lo hayan dado o no.
(El corpus de la capa de sugerencias, `ml suggestions build-dataset`, y `ml export-tables`
sí lo leen con `--include-self-registered`, como `ml export-staves`: enmienda de #400 en
ADR-0065, probada en `test_export_tables.py`.)
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
    SessionData,
    User,
)
from cadenza.domain import EditEvent, EditOp
from cadenza.learning import RepositoryDatasetReader, TrainingSample

from .support import make_anchor, make_document

CONSENT_AT = datetime(2026, 11, 9, 18, 30, tzinfo=UTC)


def _users(*, consent: bool) -> list[User]:
    users = [
        User(id="ana", username="ana", password_hash=secrets.token_hex(8)),
        User(
            id="visita",
            username="visita",
            password_hash=secrets.token_hex(8),
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
