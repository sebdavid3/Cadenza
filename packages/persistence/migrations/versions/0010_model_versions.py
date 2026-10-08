"""Crear tabla model_versions para persistencia del Model Registry (ADR-0008, #21).

Revision ID: 0010_model_versions
Revises: 0009_findings_dismissal
Create Date: 2026-10-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_model_versions"
down_revision = "0009_findings_dismissal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_versions",
        sa.Column("version", sa.String(length=64), primary_key=True),
        sa.Column(
            "artifact_hash",
            sa.String(length=64),
            sa.ForeignKey("artifacts.sha256", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("dataset_hash", sa.String(length=64), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("ser", sa.Float(), nullable=False),
        sa.Column("omr_ned", sa.Float(), nullable=False),
        sa.Column(
            "promoted",
            sa.Boolean(),
            server_default=sa.text("0"),
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
    op.drop_table("model_versions")
