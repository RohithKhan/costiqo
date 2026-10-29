"""add product search indexes
 
Revision ID: 20261029_0006
Revises: 20260609_0005
Create Date: 2026-10-29 15:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261029_0006"
down_revision = "20260609_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not _table_exists("products"):
        return

    if not _index_exists("products", "ix_products_brand"):
        op.create_index("ix_products_brand", "products", ["brand"])

    if not _index_exists("products", "ix_products_category"):
        op.create_index("ix_products_category", "products", ["category"])

    if not _index_exists("products", "ix_products_category_brand"):
        op.create_index("ix_products_category_brand", "products", ["category", "brand"])


def downgrade() -> None:
    if not _table_exists("products"):
        return

    if _index_exists("products", "ix_products_category_brand"):
        op.drop_index("ix_products_category_brand", table_name="products")

    if _index_exists("products", "ix_products_category"):
        op.drop_index("ix_products_category", table_name="products")

    if _index_exists("products", "ix_products_brand"):
        op.drop_index("ix_products_brand", table_name="products")


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in set(inspector.get_table_names())


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    indexes = {idx["name"] for idx in inspector.get_indexes(table_name)}
    return index_name in indexes
