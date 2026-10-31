"""Añadir a sessions el título, el compositor, los instrumentos y el nombre del archivo (#235).

Datos de la sesión que indica la persona, fuera del `ScoreIR` y del log (ADR-0041 §1). Todas
las columnas admiten NULL: las sesiones anteriores se leen sin metadatos, como antes.

Revision ID: 0014_session_metadata
Revises: 0013_suggestions
Create Date: 2026-10-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_session_metadata"
down_revision = "0013_suggestions"
branch_labels = None
depends_on = None

JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(sa.Column("title", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("composer", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("part_instruments", JSON_DOCUMENT, nullable=True))
        batch_op.add_column(sa.Column("source_filename", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_column("source_filename")
        batch_op.drop_column("part_instruments")
        batch_op.drop_column("composer")
        batch_op.drop_column("title")
