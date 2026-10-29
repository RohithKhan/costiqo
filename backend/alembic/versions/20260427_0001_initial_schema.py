"""Initial Costiqo rewrite schema.

Revision ID: 20260427_0001
Revises:
Create Date: 2026-04-27 17:30:00
"""

from __future__ import annotations

from alembic import op

from app.db.base import Base
from app.db.models import (  # noqa: F401
    alert_rule,
    offline_quote,
    price_snapshot,
    product,
    purchase_record,
    review,
    saved_product,
    saved_search,
    scrape_job,
    sentiment_summary,
    user,
    vendor,
    vendor_product,
)


revision = "20260427_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
