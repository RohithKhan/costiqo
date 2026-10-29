"""Add procurement lifecycle fields to offline quotes.

Revision ID: 20260428_0002
Revises: 20260427_0001
Create Date: 2026-04-28 16:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260428_0002"
down_revision = "20260427_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_columns = _column_names("offline_quotes")
    added_status = "status" not in existing_columns
    additions = [
        ("quote_reference", sa.Column("quote_reference", sa.String(length=120), nullable=True)),
        (
            "status",
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="submitted",
            ),
        ),
        ("supplier_score", sa.Column("supplier_score", sa.Float(), nullable=True)),
        ("submitted_at", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True)),
        ("approved_at", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True)),
        ("closed_at", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True)),
    ]

    missing_columns = [column for name, column in additions if name not in existing_columns]
    if missing_columns:
        with op.batch_alter_table("offline_quotes") as batch_op:
            for column in missing_columns:
                batch_op.add_column(column)

    if added_status:
        op.execute(
            """
            UPDATE offline_quotes
            SET status = CASE
                WHEN is_active IS TRUE THEN 'submitted'
                ELSE 'closed'
            END
            """
        )

        with op.batch_alter_table("offline_quotes") as batch_op:
            batch_op.alter_column("status", server_default=None)


def downgrade() -> None:
    existing_columns = _column_names("offline_quotes")
    with op.batch_alter_table("offline_quotes") as batch_op:
        for column_name in (
            "closed_at",
            "approved_at",
            "submitted_at",
            "supplier_score",
            "status",
            "quote_reference",
        ):
            if column_name in existing_columns:
                batch_op.drop_column(column_name)


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}
