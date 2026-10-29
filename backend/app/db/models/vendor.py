from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.time_utils import utc_now


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    base_url: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    scrape_strategy: Mapped[str] = mapped_column(String(120))
    last_scraped_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utc_now)

    vendor_products = relationship("VendorProduct", back_populates="vendor")
