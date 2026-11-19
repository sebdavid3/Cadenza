"""Crear la tabla public_stats_scores: el detalle de cada partitura de un corpus (#424, ADR-0073).

Una fila por partitura del historial de un corpus público (`primus`, `camera-primus`): sus cifras
y sus ejemplos con el compás dibujado, que sirve `GET /stats/homr-errors/{grupo}/scores/{id}`
al elegirla en la página, y la imagen del corpus si la hay (`.../image`; unos 2 KB en PrIMuS y
23 KB en Camera-PrIMuS). Los grupos de Cadenza no tienen. Sin clave foránea a `public_stats`:
el servicio `stats` reescribe los grupos de los corpus sin recalcular todos, y borra a mano el
detalle de los que ya no están. Son datos derivados: bajar la migración los pierde y el siguiente
cálculo los rehace.

Revision ID: 0020_public_stats_scores
Revises: 0019_public_stats
Create Date: 2026-11-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020_public_stats_scores"
down_revision = "0019_public_stats"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "public_stats_scores",
        sa.Column("group_id", sa.String(length=64), primary_key=True),
        sa.Column("score_id", sa.String(length=200), primary_key=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("format_version", sa.Integer(), nullable=False),
        sa.Column("detail", JSON, nullable=False),
        sa.Column("image_type", sa.String(length=32), nullable=True),
        sa.Column("image", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("public_stats_scores")
