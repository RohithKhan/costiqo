from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.time_utils import utc_now


class OfflineQuote(Base):
    __tablename__ = "offline_quotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    supplier_name: Mapped[str] = mapped_column(String(255), index=True)
    quoted_price: Mapped[object] = mapped_column(Numeric(10, 2))
    shipping_cost: Mapped[object] = mapped_column(Numeric(10, 2), default=0)
    currency: Mapped[str] = mapped_column(String(12), default="INR")
    seller_location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(12), nullable=True)
    estimated_delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quote_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="submitted")
    supplier_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    valid_until: Mapped[object | None] = mapped_column(Date(), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    submitted_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utc_now)

    product = relationship("Product", back_populates="offline_quotes")
    purchase_associations = relationship(
        "PurchaseRecordQuote",
        back_populates="offline_quote",
        cascade="all, delete-orphan",
    )
