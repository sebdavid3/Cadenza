"""Añadir el permiso de uso de los datos a la tabla users (#378, ADR-0065).

Dos columnas: cuándo se dio el permiso (`data_consent_at`) y qué versión del texto se leyó
(`data_consent_version`). Las dos nulas, sin permiso: así quedan las cuentas que ya existen. El
permiso solo se guarda; usarlo para incluir datos será otro issue.

Revision ID: 0017_users_data_consent
Revises: 0016_previews
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_users_data_consent"
down_revision = "0016_previews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("data_consent_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("data_consent_version", sa.String(32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("data_consent_version")
        batch_op.drop_column("data_consent_at")
