from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_product_id: Mapped[int] = mapped_column(ForeignKey("vendor_products.id"), index=True)
    price: Mapped[object] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(12), default="INR")
    scraped_at: Mapped[object] = mapped_column(DateTime(timezone=True))

    vendor_product = relationship("VendorProduct", back_populates="price_snapshots")
