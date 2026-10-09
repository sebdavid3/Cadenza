"""Migración del esquema de sessions y findings al modelo objetivo (ADR-0004, #5).

Revision ID: 0004_sessions_findings_schema
Revises: 0003_artifacts_table
Create Date: 2026-10-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_sessions_findings_schema"
down_revision = "0003_artifacts_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Actualizar tabla sessions
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "image_artifact",
                sa.String(length=64),
                sa.ForeignKey(
                    "artifacts.sha256",
                    ondelete="SET NULL",
                    name="fk_sessions_image_artifact",
                ),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("model_version", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=32),
                server_default="transcribed",
                nullable=False,
            )
        )

    # 2. Actualizar tabla findings
    with op.batch_alter_table("findings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "at_seq",
                sa.Integer(),
                server_default="0",
                nullable=False,
            )
        )


def downgrade() -> None:
    # 1. Revertir tabla findings
    with op.batch_alter_table("findings") as batch_op:
        batch_op.drop_column("at_seq")

    # 2. Revertir tabla sessions
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_constraint("fk_sessions_image_artifact", type_="foreignkey")
        batch_op.drop_column("status")
        batch_op.drop_column("model_version")
        batch_op.drop_column("image_artifact")

