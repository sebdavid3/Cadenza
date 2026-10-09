"""Crear tabla effort_metrics para persistencia de métricas de esfuerzo (ADR-0004, #13).

Revision ID: 0007_effort_metrics_table
Revises: 0006_session_validated_at_seq
Create Date: 2026-10-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_effort_metrics_table"
down_revision = "0006_session_validated_at_seq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "effort_metrics",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("time_to_first_edit_ms", sa.Integer(), nullable=True),
        sa.Column(
            "interventions",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("effort_metrics")
