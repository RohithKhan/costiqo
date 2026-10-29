from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.time_utils import utc_now


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_product_id: Mapped[int] = mapped_column(ForeignKey("vendor_products.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text())
    rating: Mapped[float | None] = mapped_column(nullable=True)
    review_date: Mapped[object | None] = mapped_column(Date(), nullable=True)
    scraped_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utc_now)

    vendor_product = relationship("VendorProduct", back_populates="reviews")
