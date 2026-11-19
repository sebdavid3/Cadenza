"""Qué sesiones entran en los datos según el permiso de uso de los datos (#422, ADR-0065).

Decisión del responsable del 2026-11-19: por defecto entran las cuentas del registro con el
permiso vigente, y una opción las deja fuera. Las que no lo tienen (nunca lo dieron, lo
retiraron o lo dieron para otro texto) quedan siempre fuera y solo se cuentan. Las cuentas que no
vienen del registro (las del equipo y las del estudio, anteriores a ADR-0070) entran siempre: no
se les pidió este permiso. La regla es la misma en todos los comandos (`cadenza.learning.consent`);
aquí, el filtro y el dataset de `ml build-dataset` (`RepositoryDatasetReader`).
"""

from __future__ import annotations

import secrets
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from cadenza.application import (
    DATA_CONSENT_VERSION,
    InMemoryEditEventRepository,
    InMemorySessionRepository,
    InMemoryUserRepository,
    SessionData,
    User,
)
from cadenza.domain import EditEvent, EditOp
from cadenza.learning import RepositoryDatasetReader
from cadenza.learning.consent import NO_OWNER, ConsentTally, filter_by_consent

from .support import make_anchor, make_document

CONSENT_AT = datetime(2026, 11, 19, 18, 30, tzinfo=UTC)


def _user(user_id: str, *, self_registered: bool = True, consent: str | None = None) -> User:
    user = User(
        id=user_id,
        username=user_id,
        password_hash=secrets.token_hex(8),
        self_registered=self_registered,
    )
    if consent is None:
        return user
    return replace(user, data_consent_at=CONSENT_AT, data_consent_version=consent)


USERS = (
    _user("vigente", consent=DATA_CONSENT_VERSION),
    # Retirarlo borra la fecha y la versión: igual que no haberlo dado nunca (ADR-0065 §5).
    _user("retirado"),
    # El del texto anterior (#427 subió la versión): ya no está vigente.
    _user("otro-texto", consent="2026-11-09"),
    _user("equipo", self_registered=False),
    # Una cuenta del estudio, creada por un investigador antes de ADR-0070, con el permiso dado
    # o sin él: no viene del registro, así que este permiso no decide.
    _user("estudio", self_registered=False, consent=DATA_CONSENT_VERSION),
)

# (sesión, dueño, partitura de prueba)
SESSIONS = (
    ("s-vigente", "vigente", None),
    ("s-retirado", "retirado", None),
    ("s-otro-texto", "otro-texto", None),
    ("s-equipo", "equipo", None),
    ("s-estudio", "estudio", "TS-01"),
    ("s-sin-cuenta", "nadie", None),
)


def _session(session_id: str, owner_id: str, test_score_id: str | None) -> SessionData:
    document = make_document(f"doc-{session_id}")
    return SessionData(
        id=session_id,
        document_id=document.id,
        omr_engine="fake",
        document=document.to_primitive(),
        image_artifact=f"image-{session_id}",
        status="finalized",
        owner_id=owner_id,
        test_score_id=test_score_id,
    )


def _sessions() -> list[SessionData]:
    return [_session(*fields) for fields in SESSIONS]


def test_by_default_registered_accounts_enter_with_the_current_consent() -> None:
    tally = ConsentTally()
    entering, left_out = filter_by_consent(
        _sessions(), InMemoryUserRepository(USERS), exclude_self_registered=False, tally=tally
    )
    assert [s.id for s in entering] == ["s-vigente", "s-equipo", "s-estudio"]
    # Las que deja fuera el permiso solo se cuentan: su identificador no sale.
    assert left_out == {"s-sin-cuenta": NO_OWNER}
    assert (tally.without_current_consent, tally.excluded_by_option) == (2, 0)
    assert tally.to_primitive() == {
        "version": DATA_CONSENT_VERSION,
        "sessions_without_current_consent": 2,
        "sessions_excluded_by_option": 0,
    }


def test_the_option_leaves_out_every_registered_account() -> None:
    tally = ConsentTally()
    entering, left_out = filter_by_consent(
        _sessions(), InMemoryUserRepository(USERS), exclude_self_registered=True, tally=tally
    )
    assert [s.id for s in entering] == ["s-equipo", "s-estudio"]
    assert left_out == {"s-sin-cuenta": NO_OWNER}
    # Las que no tienen el permiso siguen contadas por eso, no por la opción.
    assert (tally.without_current_consent, tally.excluded_by_option) == (2, 1)


def test_the_tally_is_optional_and_adds_up() -> None:
    users = InMemoryUserRepository(USERS)
    entering, _ = filter_by_consent(_sessions(), users, exclude_self_registered=False)
    assert len(entering) == 3
    tally = ConsentTally()
    for _ in range(2):
        filter_by_consent(_sessions(), users, exclude_self_registered=True, tally=tally)
    assert (tally.without_current_consent, tally.excluded_by_option) == (4, 2)


# --- `ml build-dataset`: RepositoryDatasetReader -------------------------------------------------


def _repositories() -> tuple[InMemorySessionRepository, InMemoryEditEventRepository]:
    sessions = InMemorySessionRepository()
    edits = InMemoryEditEventRepository()
    for session in _sessions():
        sessions.add(session, [])
        edits.append(
            session.id,
            EditEvent(
                id=f"edit-{session.id}",
                document_id=session.document_id,
                seq=1,
                anchor=make_anchor(0),
                op=EditOp.SET_PITCH,
                author=session.owner_id,
                created_at=datetime(2026, 11, 19, tzinfo=UTC),
                before={"pitch": "C4"},
                after={"pitch": "D4"},
            ),
        )
    return sessions, edits


@pytest.mark.parametrize(
    ("exclude", "documents", "counts"),
    [
        (False, {"doc-s-vigente", "doc-s-equipo", "doc-s-estudio"}, (2, 0)),
        (True, {"doc-s-equipo", "doc-s-estudio"}, (2, 1)),
    ],
)
def test_the_correction_dataset_follows_the_consent(
    exclude: bool, documents: set[str], counts: tuple[int, int]
) -> None:
    sessions, edits = _repositories()
    tally = ConsentTally()
    samples = RepositoryDatasetReader().read_dataset(
        sessions,
        edits,
        user_repository=InMemoryUserRepository(USERS),
        exclude_self_registered=exclude,
        consent=tally,
    )
    assert {sample.document_id for sample in samples} == documents
    assert (tally.without_current_consent, tally.excluded_by_option) == counts


@pytest.mark.parametrize(
    ("owner_id", "exclude", "message"),
    [
        ("retirado", False, "sin el permiso de uso de los datos vigente"),
        ("otro-texto", False, "sin el permiso de uso de los datos vigente"),
        ("vigente", True, "--exclude-self-registered"),
        ("nadie", False, "no existe"),
    ],
)
def test_asking_for_an_account_that_does_not_enter_is_an_error(
    owner_id: str, exclude: bool, message: str
) -> None:
    # Pedir las sesiones de una cuenta que no entra daría un dataset vacío sin avisar.
    sessions, edits = _repositories()
    with pytest.raises(ValueError, match=message):
        RepositoryDatasetReader().read_dataset(
            sessions,
            edits,
            user_repository=InMemoryUserRepository(USERS),
            owner_id=owner_id,
            exclude_self_registered=exclude,
        )


@pytest.mark.parametrize("owner_id", ["vigente", "equipo", "estudio"])
def test_asking_for_an_account_that_enters(owner_id: str) -> None:
    sessions, edits = _repositories()
    samples = RepositoryDatasetReader().read_dataset(
        sessions, edits, user_repository=InMemoryUserRepository(USERS), owner_id=owner_id
    )
    assert {sample.document_id for sample in samples} == {f"doc-s-{owner_id}"}
