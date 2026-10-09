"""Refuerza el log de ediciones como append-only (ADR-0007).

Revision ID: 0002_edit_events_append_only
Revises: 0001_initial
Create Date: 2026-09-20
"""

from __future__ import annotations

from alembic import op

revision = "0002_edit_events_append_only"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_edit_events_session_seq", "edit_events", ["session_id", "seq"]
    )
    op.drop_constraint("edit_events_session_id_fkey", "edit_events", type_="foreignkey")
    op.create_foreign_key(
        "fk_edit_events_session_id",
        "edit_events",
        "sessions",
        ["session_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_edit_events_session_id", "edit_events", type_="foreignkey")
    op.create_foreign_key(
        "edit_events_session_id_fkey",
        "edit_events",
        "sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("uq_edit_events_session_seq", "edit_events", type_="unique")
