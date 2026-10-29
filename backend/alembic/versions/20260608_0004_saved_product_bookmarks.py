"""Store saved product bookmarks as name and URL.

Revision ID: 20260608_0004
Revises: 20260428_0003
Create Date: 2026-06-08 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260608_0004"
down_revision = "20260428_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = _column_names("saved_products")
    if "product_id" not in columns:
        return

    with op.batch_alter_table("saved_products") as batch_op:
        if "product_name" not in columns:
            batch_op.add_column(sa.Column("product_name", sa.String(length=255), nullable=True))
        if "product_url" not in columns:
            batch_op.add_column(sa.Column("product_url", sa.String(length=500), nullable=True))

    op.execute(
        """
        UPDATE saved_products
        SET
          product_name = COALESCE(
            (SELECT products.canonical_name FROM products WHERE products.id = saved_products.product_id),
            'Saved product'
          ),
          product_url = COALESCE(
            (
              SELECT vendor_products.vendor_product_url
              FROM vendor_products
              WHERE vendor_products.product_id = saved_products.product_id
              ORDER BY vendor_products.current_price ASC
              LIMIT 1
            ),
            '#legacy-product-' || saved_products.product_id
          )
        WHERE product_name IS NULL OR product_url IS NULL
        """
    )

    with op.batch_alter_table("saved_products") as batch_op:
        batch_op.alter_column("product_name", existing_type=sa.String(length=255), nullable=False)
        batch_op.alter_column("product_url", existing_type=sa.String(length=500), nullable=False)
        batch_op.drop_constraint("uq_saved_product_user_product", type_="unique")
        batch_op.drop_index("ix_saved_products_product_id")
        batch_op.drop_column("product_id")
        batch_op.create_unique_constraint("uq_saved_product_user_url", ["user_id", "product_url"])


def downgrade() -> None:
    columns = _column_names("saved_products")
    if "product_id" in columns:
        return

    with op.batch_alter_table("saved_products") as batch_op:
        batch_op.add_column(sa.Column("product_id", sa.Integer(), nullable=True))
        if _constraint_exists("saved_products", "uq_saved_product_user_url"):
            batch_op.drop_constraint("uq_saved_product_user_url", type_="unique")
        batch_op.create_index("ix_saved_products_product_id", ["product_id"])
        batch_op.create_unique_constraint("uq_saved_product_user_product", ["user_id", "product_id"])
        if "product_url" in columns:
            batch_op.drop_column("product_url")
        if "product_name" in columns:
            batch_op.drop_column("product_name")


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _constraint_exists(table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    constraints = inspector.get_unique_constraints(table_name)
    return any(constraint["name"] == constraint_name for constraint in constraints)
