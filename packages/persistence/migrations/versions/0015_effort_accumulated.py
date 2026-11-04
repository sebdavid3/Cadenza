"""Añadir a effort_metrics el registro que acumula la web (#188, ADR-0050).

Un solo registro por sesión (`accumulated`, con un índice único parcial) con los tramos de tiempo
de cada pestaña (`segments`), las intervenciones por clase (`interventions_by_class`), los
contadores de descartes, restauraciones y respuestas a las sugerencias, y `updated_at`. Los
registros anteriores quedan como registros sueltos de `POST /effort`: sin tramos y a cero.

Revision ID: 0015_effort_accumulated
Revises: 0014_session_metadata
Create Date: 2026-11-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_effort_accumulated"
down_revision = "0014_session_metadata"
branch_labels = None
depends_on = None

JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
COUNTERS = (
    "findings_dismissed",
    "findings_restored",
    "suggestions_applied",
    "suggestions_rejected",
)
INDEX = "uq_effort_metrics_accumulated_session"


def upgrade() -> None:
    with op.batch_alter_table("effort_metrics") as batch_op:
        batch_op.add_column(
            sa.Column("accumulated", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(
            sa.Column("segments", JSON_DOCUMENT, server_default=sa.text("'[]'"), nullable=False)
        )
        batch_op.add_column(
            sa.Column(
                "interventions_by_class",
                JSON_DOCUMENT,
                server_default=sa.text("'{}'"),
                nullable=False,
            )
        )
        for name in COUNTERS:
            batch_op.add_column(
                sa.Column(name, sa.Integer(), server_default="0", nullable=False)
            )
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        INDEX,
        "effort_metrics",
        ["session_id"],
        unique=True,
        sqlite_where=sa.text("accumulated = 1"),
        postgresql_where=sa.text("accumulated"),
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name="effort_metrics")
    with op.batch_alter_table("effort_metrics") as batch_op:
        batch_op.drop_column("updated_at")
        for name in reversed(COUNTERS):
            batch_op.drop_column(name)
        batch_op.drop_column("interventions_by_class")
        batch_op.drop_column("segments")
        batch_op.drop_column("accumulated")
