"""add search audit logs

Revision ID: 20260609_0005
Revises: 20260608_0004
Create Date: 2026-06-09 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260609_0005"
down_revision = "20260608_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if _table_exists("search_audit_logs"):
        return

    op.create_table(
        "search_audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("user_email", sa.String(length=255), nullable=True),
        sa.Column("query", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=120), nullable=True),
        sa.Column("pincode", sa.String(length=12), nullable=True),
        sa.Column("ranking_mode", sa.String(length=32), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("client_host", sa.String(length=80), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_search_audit_logs_created_at", "search_audit_logs", ["created_at"])
    op.create_index("ix_search_audit_logs_query", "search_audit_logs", ["query"])
    op.create_index("ix_search_audit_logs_user_email", "search_audit_logs", ["user_email"])
    op.create_index("ix_search_audit_logs_user_id", "search_audit_logs", ["user_id"])


def downgrade() -> None:
    if not _table_exists("search_audit_logs"):
        return

    op.drop_index("ix_search_audit_logs_user_id", table_name="search_audit_logs")
    op.drop_index("ix_search_audit_logs_user_email", table_name="search_audit_logs")
    op.drop_index("ix_search_audit_logs_query", table_name="search_audit_logs")
    op.drop_index("ix_search_audit_logs_created_at", table_name="search_audit_logs")
    op.drop_table("search_audit_logs")


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in set(inspector.get_table_names())
