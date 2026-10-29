"""Add account persistence tables.

Revision ID: 20260428_0003
Revises: 20260428_0002
Create Date: 2026-04-28 19:55:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260428_0003"
down_revision = "20260428_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_tables = _table_names()
    if "saved_products" not in existing_tables:
        op.create_table(
            "saved_products",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "product_id", name="uq_saved_product_user_product"),
        )
        op.create_index("ix_saved_products_user_id", "saved_products", ["user_id"])
        op.create_index("ix_saved_products_product_id", "saved_products", ["product_id"])

    if "saved_searches" not in existing_tables:
        op.create_table(
            "saved_searches",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("query", sa.String(length=255), nullable=False),
            sa.Column("location", sa.String(length=120), nullable=True),
            sa.Column("pincode", sa.String(length=12), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_saved_searches_user_id", "saved_searches", ["user_id"])
        op.create_index("ix_saved_searches_query", "saved_searches", ["query"])

    if "alert_rules" not in existing_tables:
        op.create_table(
            "alert_rules",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
            sa.Column("query", sa.String(length=255), nullable=True),
            sa.Column("location", sa.String(length=120), nullable=True),
            sa.Column("pincode", sa.String(length=12), nullable=True),
            sa.Column("trigger_type", sa.String(length=32), nullable=False),
            sa.Column("target_price", sa.Numeric(10, 2), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_alert_rules_user_id", "alert_rules", ["user_id"])
        op.create_index("ix_alert_rules_product_id", "alert_rules", ["product_id"])


def downgrade() -> None:
    existing_tables = _table_names()
    if "alert_rules" in existing_tables:
        op.drop_index("ix_alert_rules_product_id", table_name="alert_rules")
        op.drop_index("ix_alert_rules_user_id", table_name="alert_rules")
        op.drop_table("alert_rules")

    if "saved_searches" in existing_tables:
        op.drop_index("ix_saved_searches_query", table_name="saved_searches")
        op.drop_index("ix_saved_searches_user_id", table_name="saved_searches")
        op.drop_table("saved_searches")

    if "saved_products" in existing_tables:
        op.drop_index("ix_saved_products_product_id", table_name="saved_products")
        op.drop_index("ix_saved_products_user_id", table_name="saved_products")
        op.drop_table("saved_products")


def _table_names() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())
