"""Fábricas de engine y sesión, y bootstrap de esquema.

En producción la URL apunta a PostgreSQL (JSONB); en tests se usa SQLite en
memoria con `StaticPool` para compartir la misma conexión entre hilos.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base

SessionFactory = sessionmaker[DbSession]


def create_engine_for_url(url: str) -> Engine:
    """Crea un engine; habilita `check_same_thread` y `StaticPool` para SQLite en memoria."""

    is_sqlite = url.startswith("sqlite")
    connect_args: dict[str, Any] = {"check_same_thread": False} if is_sqlite else {}
    kwargs: dict[str, Any] = {"connect_args": connect_args, "future": True}
    if is_sqlite and ":memory:" in url:
        kwargs["poolclass"] = StaticPool
    return create_engine(url, **kwargs)


def create_memory_engine() -> Engine:
    """Engine SQLite en memoria compartido (tests)."""

    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


def create_session_factory(engine: Engine) -> SessionFactory:
    return sessionmaker(bind=engine, expire_on_commit=False, class_=DbSession)


def create_schema(engine: Engine) -> None:
    """Crea el esquema a partir de los modelos (desarrollo/tests)."""

    Base.metadata.create_all(engine)


@contextmanager
def session_scope(factory: SessionFactory) -> Iterator[DbSession]:
    """Transacción de conveniencia: commit al salir, rollback ante error."""

    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
