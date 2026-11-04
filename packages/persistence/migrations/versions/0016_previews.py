"""Crear la tabla previews: transcripciones sin cuenta de la portada (#278).

Cada fila es una transcripción hecha sin cuenta: el documento que leyó HOMR, la imagen, los datos
de la partitura, el SHA-256 del token con el que se reclama y su caducidad (ADR-0054). No es una
sesión ni tiene dueño: `sessions.owner_id` no cambia. Al reclamarla, la fila se borra y nace la
sesión; al caducar, se borra con su imagen.

Cuelga de la 0015 de #188 (`0015_effort_accumulated`), que entró en `dev` mientras se hacía esta.

Revision ID: 0016_previews
Revises: 0015_effort_accumulated
Create Date: 2026-11-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016_previews"
down_revision = "0015_effort_accumulated"
branch_labels = None
depends_on = None

JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "previews",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("document", JSON_DOCUMENT, nullable=False),
        sa.Column("image", sa.LargeBinary(), nullable=False),
        sa.Column("image_media_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("composer", sa.String(length=200), nullable=True),
        sa.Column("part_instruments", JSON_DOCUMENT, nullable=True),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_previews_expires_at", "previews", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_previews_expires_at", table_name="previews")
    op.drop_table("previews")
