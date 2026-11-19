"""Quitar el rol de la tabla users (#419, ADR-0070).

Ya no hay investigadores: todas las cuentas son iguales y cada una ve solo sus sesiones. Bajar
devuelve la columna con `transcriptor` en todas las cuentas: quién era investigador no se
recupera.

Revision ID: 0018_users_drop_role
Revises: 0017_users_data_consent
Create Date: 2026-11-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_users_drop_role"
down_revision = "0017_users_data_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("role")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("role", sa.String(32), nullable=False, server_default="transcriptor")
        )
