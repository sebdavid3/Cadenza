"""Añadir columna reverts_edit_id a la tabla edit_events (#35, ADR-0007).

Revision ID: 0008_edit_events_reverts_edit_id
Revises: 0007_effort_metrics_table
Create Date: 2026-10-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_edit_events_reverts_edit_id"
down_revision = "0007_effort_metrics_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("edit_events") as batch_op:
        batch_op.add_column(
            sa.Column(
                "reverts_edit_id",
                sa.String(length=36),
                sa.ForeignKey(
                    "edit_events.id",
                    ondelete="RESTRICT",
                    name="fk_edit_events_reverts_edit_id",
                ),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("edit_events") as batch_op:
        batch_op.drop_constraint("fk_edit_events_reverts_edit_id", type_="foreignkey")
        batch_op.drop_column("reverts_edit_id")
