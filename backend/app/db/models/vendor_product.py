from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.time_utils import utc_now


class VendorProduct(Base):
    __tablename__ = "vendor_products"
    __table_args__ = (
        UniqueConstraint("vendor_id", "vendor_product_url", name="uq_vendor_product_url"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    vendor_product_name: Mapped[str] = mapped_column(String(255))
    vendor_product_url: Mapped[str] = mapped_column(String(500))
    current_price: Mapped[object] = mapped_column(Numeric(10, 2))
    raw_price: Mapped[str] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(12), default="INR")
    rating: Mapped[float | None] = mapped_column(nullable=True)
    review_count: Mapped[int] = mapped_column(default=0)
    delivery_info: Mapped[str | None] = mapped_column(String(120), nullable=True)
    availability_status: Mapped[str] = mapped_column(String(64), default="in_stock")
    last_seen_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utc_now)

    product = relationship("Product", back_populates="vendor_products")
    vendor = relationship("Vendor", back_populates="vendor_products")
    price_snapshots = relationship(
        "PriceSnapshot",
        back_populates="vendor_product",
        cascade="all, delete-orphan",
        order_by="PriceSnapshot.scraped_at",
    )
    reviews = relationship(
        "Review",
        back_populates="vendor_product",
        cascade="all, delete-orphan",
        order_by="Review.review_date",
    )
    sentiment_summary = relationship(
        "SentimentSummary",
        back_populates="vendor_product",
        uselist=False,
        cascade="all, delete-orphan",
    )
