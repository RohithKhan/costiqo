from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.time_utils import utc_now


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_category_brand", "category", "brand"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(255), index=True)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    model_number: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utc_now)

    vendor_products = relationship("VendorProduct", back_populates="product")
    offline_quotes = relationship(
        "OfflineQuote",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="OfflineQuote.created_at.desc()",
    )
    purchase_records = relationship(
        "PurchaseRecord",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="PurchaseRecord.purchased_at.desc()",
    )
    alert_rules = relationship("AlertRule", back_populates="product")
