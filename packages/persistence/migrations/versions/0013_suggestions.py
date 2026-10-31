"""Crear las tablas de la capa de sugerencias: suggestions y suggestion_model_versions (#256).

Una fila por sugerencia, con su hallazgo (que queda en NULL al sustituirse si la sugerencia
ya tenía respuesta), la edición propuesta, la confianza, la explicación, la versión de la
capa y la respuesta de la persona; y el registro de versiones de la capa, separado del del
motor OMR (ADR-0036 §4, §8).

Revision ID: 0013_suggestions
Revises: 0012_users_self_registered
Create Date: 2026-10-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_suggestions"
down_revision = "0012_users_self_registered"
branch_labels = None
depends_on = None

JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "suggestions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE", name="fk_suggestions_session_id"),
            nullable=False,
        ),
        sa.Column(
            "finding_id",
            sa.Integer(),
            sa.ForeignKey("findings.id", ondelete="SET NULL", name="fk_suggestions_finding_id"),
            nullable=True,
        ),
        sa.Column("at_seq", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("op", sa.String(length=32), nullable=False),
        sa.Column("anchor", JSON_DOCUMENT, nullable=False),
        sa.Column("before", JSON_DOCUMENT, nullable=True),
        sa.Column("after", JSON_DOCUMENT, nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("confidence_level", sa.String(length=16), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("response", sa.String(length=16), nullable=True),
        sa.Column("responded_by", sa.String(length=128), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_seq", sa.Integer(), nullable=True),
        sa.Column("inherited_from", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_suggestions_session_id", "suggestions", ["session_id"])
    op.create_index("ix_suggestions_finding_id", "suggestions", ["finding_id"])
    op.create_table(
        "suggestion_model_versions",
        sa.Column("version", sa.String(length=64), primary_key=True),
        sa.Column(
            "artifact_hash",
            sa.String(length=64),
            sa.ForeignKey(
                "artifacts.sha256",
                ondelete="RESTRICT",
                name="fk_suggestion_model_versions_artifact_hash",
            ),
            nullable=False,
        ),
        sa.Column("dataset_hash", sa.String(length=64), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("model_type", sa.String(length=64), nullable=False),
        sa.Column("feature_version", sa.Integer(), nullable=False),
        sa.Column("metrics", JSON_DOCUMENT, nullable=False),
        sa.Column("promoted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("suggestion_model_versions")
    op.drop_index("ix_suggestions_finding_id", table_name="suggestions")
    op.drop_index("ix_suggestions_session_id", table_name="suggestions")
    op.drop_table("suggestions")
