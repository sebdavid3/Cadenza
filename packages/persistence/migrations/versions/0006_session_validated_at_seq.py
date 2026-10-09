"""Añadir columna validated_at_seq a la tabla sessions (ADR-0013, #11).

Revision ID: 0006_session_validated_at_seq
Revises: 0005_users_and_session_owner
Create Date: 2026-10-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_session_validated_at_seq"
down_revision = "0005_users_and_session_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "validated_at_seq",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_column("validated_at_seq")
