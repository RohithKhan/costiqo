from sqlalchemy import DateTime, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.time_utils import utc_now


class SentimentSummary(Base):
    __tablename__ = "sentiment_summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_product_id: Mapped[int] = mapped_column(
        ForeignKey("vendor_products.id"),
        unique=True,
        index=True,
    )
    positive_count: Mapped[int] = mapped_column(default=0)
    neutral_count: Mapped[int] = mapped_column(default=0)
    negative_count: Mapped[int] = mapped_column(default=0)
    sentiment_score: Mapped[object] = mapped_column(Numeric(4, 2), default=0)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utc_now)

    vendor_product = relationship("VendorProduct", back_populates="sentiment_summary")
