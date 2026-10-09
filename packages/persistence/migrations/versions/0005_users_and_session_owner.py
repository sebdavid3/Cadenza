"""Creación de la tabla users y columna owner_id en sessions (ADR-0012, #43).

Revision ID: 0005_users_and_session_owner
Revises: 0004_sessions_findings_schema
Create Date: 2026-10-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_users_and_session_owner"
down_revision = "0004_sessions_findings_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Crear tabla users
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    # 2. Insertar usuario inicial semilla para preservar sesiones existentes
    users_table = sa.table(
        "users",
        sa.column("id", sa.String),
        sa.column("username", sa.String),
        sa.column("password_hash", sa.String),
        sa.column("role", sa.String),
        sa.column("active", sa.Boolean),
    )
    op.bulk_insert(
        users_table,
        [
            {
                "id": "default-user",
                "username": "admin",
                "password_hash": "",
                "role": "investigador",
                "active": True,
            }
        ],
    )

    # 3. Añadir owner_id en tabla sessions con FK y server_default
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "owner_id",
                sa.String(length=36),
                sa.ForeignKey(
                    "users.id",
                    ondelete="RESTRICT",
                    name="fk_sessions_owner_id",
                ),
                server_default="default-user",
                nullable=False,
            )
        )


def downgrade() -> None:
    # 1. Revertir columna owner_id en tabla sessions
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_constraint("fk_sessions_owner_id", type_="foreignkey")
        batch_op.drop_column("owner_id")

    # 2. Eliminar tabla users
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
