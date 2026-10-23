"""Añadir la columna self_registered a la tabla users (ADR-0022, #154).

Revision ID: 0012_users_self_registered
Revises: 0011_condition_and_test_score
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_users_self_registered"
down_revision = "0011_condition_and_test_score"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Las cuentas existentes las creó un investigador o la CLI: no son autorregistradas.
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "self_registered",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("self_registered")
