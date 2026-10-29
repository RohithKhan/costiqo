"""create purchase_record_quotes association table

Revision ID: 20261029_0007
Revises: 20261029_0006
Create Date: 2026-10-29 15:45:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261029_0007"
down_revision = "20261029_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not _table_exists("purchase_record_quotes"):
        op.create_table(
            "purchase_record_quotes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "purchase_record_id",
                sa.Integer(),
                sa.ForeignKey("purchase_records.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "offline_quote_id",
                sa.Integer(),
                sa.ForeignKey("offline_quotes.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "purchase_record_id",
                "offline_quote_id",
                name="uq_purchase_record_quotes_record_quote",
            ),
        )

    if _table_exists("purchase_record_quotes"):
        if not _index_exists("purchase_record_quotes", "ix_purchase_record_quotes_purchase_record_id"):
            op.create_index(
                "ix_purchase_record_quotes_purchase_record_id",
                "purchase_record_quotes",
                ["purchase_record_id"],
            )
        if not _index_exists("purchase_record_quotes", "ix_purchase_record_quotes_offline_quote_id"):
            op.create_index(
                "ix_purchase_record_quotes_offline_quote_id",
                "purchase_record_quotes",
                ["offline_quote_id"],
            )


def downgrade() -> None:
    if _table_exists("purchase_record_quotes"):
        if _index_exists("purchase_record_quotes", "ix_purchase_record_quotes_offline_quote_id"):
            op.drop_index("ix_purchase_record_quotes_offline_quote_id", table_name="purchase_record_quotes")
        if _index_exists("purchase_record_quotes", "ix_purchase_record_quotes_purchase_record_id"):
            op.drop_index("ix_purchase_record_quotes_purchase_record_id", table_name="purchase_record_quotes")
        op.drop_table("purchase_record_quotes")


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in set(inspector.get_table_names())


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    indexes = {idx["name"] for idx in inspector.get_indexes(table_name)}
    return index_name in indexes
