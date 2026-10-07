"""Línea de comandos para operaciones de administración de Cadenza (ADR-0012, #46)."""

from __future__ import annotations

import argparse
import sys
import uuid

from cadenza.application import DuplicateUsername, Role, User
from cadenza.persistence import (
    SqlAlchemyUserRepository,
    create_engine_for_url,
    create_schema,
    create_session_factory,
)

from .security import Argon2PasswordHasher
from .settings import Settings


def create_initial_investigator(
    username: str,
    password: str,
    settings: Settings | None = None,
) -> User:
    """Crea una cuenta con rol investigador directamente en la base de datos."""

    if len(password) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres")

    app_settings = settings or Settings()
    engine = create_engine_for_url(app_settings.database_url)
    create_schema(engine)
    session_factory = create_session_factory(engine)
    hasher = Argon2PasswordHasher()

    with session_factory() as db:
        repo = SqlAlchemyUserRepository(db)
        user = User(
            id=str(uuid.uuid4()),
            username=username,
            password_hash=hasher.hash(password),
            role=Role.INVESTIGADOR,
            active=True,
        )
        try:
            created = repo.add(user)
            db.commit()
            return created
        except DuplicateUsername as err:
            raise ValueError(f"El usuario '{username}' ya existe") from err


def main() -> None:
    parser = argparse.ArgumentParser(description="Herramientas administrativas de Cadenza")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser(
        "create-investigator", help="Crea el primer usuario investigador"
    )
    create_parser.add_argument("--username", required=True, help="Nombre de usuario")
    create_parser.add_argument(
        "--password", required=True, help="Contraseña inicial (mínimo 8 caracteres)"
    )

    args = parser.parse_args()
    if args.command == "create-investigator":
        try:
            user = create_initial_investigator(args.username, args.password)
            print(f"Investigador '{user.username}' creado exitosamente (ID: {user.id}).")
        except Exception as err:
            print(f"Error: {err}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
