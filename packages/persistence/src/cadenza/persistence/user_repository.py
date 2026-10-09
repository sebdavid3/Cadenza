"""Adaptador SQLAlchemy para el repositorio de usuarios (ADR-0012, #43, #46)."""

from __future__ import annotations

from cadenza.application import DuplicateUsername, Role, User, UserNotFound, UserRepository
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from .models import UserRecord


class SqlAlchemyUserRepository(UserRepository):
    """Implementación de UserRepository respaldada por SQLAlchemy."""

    def __init__(self, session: DbSession) -> None:
        self._session = session

    def add(self, user: User) -> User:
        record = UserRecord(
            id=user.id,
            username=user.username,
            password_hash=user.password_hash,
            role=user.role.value,
            active=user.active,
        )
        try:
            with self._session.begin_nested():
                self._session.add(record)
                self._session.flush()
        except IntegrityError as err:
            raise DuplicateUsername(user.username) from err
        return self._to_entity(record)

    def get(self, user_id: str) -> User | None:
        record = self._session.get(UserRecord, user_id)
        if record is None:
            return None
        return self._to_entity(record)

    def get_by_username(self, username: str) -> User | None:
        record = self._session.scalars(
            select(UserRecord).where(UserRecord.username == username)
        ).first()
        if record is None:
            return None
        return self._to_entity(record)

    def list(self) -> tuple[User, ...]:
        records = self._session.scalars(
            select(UserRecord).order_by(UserRecord.created_at.asc(), UserRecord.username.asc())
        ).all()
        return tuple(self._to_entity(r) for r in records)

    def update(self, user: User) -> User:
        record = self._session.get(UserRecord, user.id)
        if record is None:
            raise UserNotFound(user.id)
        record.username = user.username
        record.password_hash = user.password_hash
        record.role = user.role.value
        record.active = user.active
        try:
            with self._session.begin_nested():
                self._session.flush()
        except IntegrityError as err:
            raise DuplicateUsername(user.username) from err
        return self._to_entity(record)

    @staticmethod
    def _to_entity(record: UserRecord) -> User:
        return User(
            id=record.id,
            username=record.username,
            password_hash=record.password_hash,
            role=Role(record.role),
            active=record.active,
            created_at=record.created_at,
        )
