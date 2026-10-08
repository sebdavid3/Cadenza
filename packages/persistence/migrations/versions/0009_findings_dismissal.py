"""Añadir columnas de descarte/resolución a la tabla findings (#36).

Revision ID: 0009_findings_dismissal
Revises: 0008_edit_events_reverts_edit_id
Create Date: 2026-10-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_findings_dismissal"
down_revision = "0008_edit_events_reverts_edit_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("findings") as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active")
        )
        batch_op.add_column(
            sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("dismissed_by", sa.String(length=128), nullable=True)
        )
        batch_op.add_column(
            sa.Column("dismissal_reason", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("findings") as batch_op:
        batch_op.drop_column("dismissal_reason")
        batch_op.drop_column("dismissed_by")
        batch_op.drop_column("dismissed_at")
        batch_op.drop_column("status")
