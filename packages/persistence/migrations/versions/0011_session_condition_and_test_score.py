"""Añadir columnas condition y test_score_id a la tabla sessions (#33, D38).

Revision ID: 0011_session_condition_and_test_score
Revises: 0010_model_versions
Create Date: 2026-10-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_session_condition_and_test_score"
down_revision = "0010_model_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "condition",
                sa.String(length=32),
                nullable=False,
                server_default="assisted",
            )
        )
        batch_op.add_column(
            sa.Column(
                "test_score_id",
                sa.String(length=128),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_column("test_score_id")
        batch_op.drop_column("condition")
