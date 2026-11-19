"""Crear la tabla public_stats: las cifras de los errores de HOMR, en vivo (#423, ADR-0073).

Una fila por grupo (`cadenza`, `pruebas` o un corpus como `primus`) con las cifras de conjunto
que calcula el servicio `stats` y sirve `GET /stats/homr-errors`. `stats` es NULL si el grupo
no llega al mínimo de sesiones. Son datos derivados: bajar la migración los pierde y el
siguiente cálculo los rehace.

Revision ID: 0019_public_stats
Revises: 0018_users_drop_role
Create Date: 2026-11-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019_public_stats"
down_revision = "0018_users_drop_role"
branch_labels = None
depends_on = None

NULLABLE_JSON = sa.JSON(none_as_null=True).with_variant(
    postgresql.JSONB(none_as_null=True), "postgresql"
)


def upgrade() -> None:
    op.create_table(
        "public_stats",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("format_version", sa.Integer(), nullable=False),
        sa.Column("min_sessions", sa.Integer(), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("stats", NULLABLE_JSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("public_stats")
