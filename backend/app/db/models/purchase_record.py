from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.time_utils import utc_now


class PurchaseRecord(Base):
    __tablename__ = "purchase_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    supplier_name: Mapped[str] = mapped_column(String(255), index=True)
    unit_price: Mapped[object] = mapped_column(Numeric(10, 2))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    shipping_cost: Mapped[object] = mapped_column(Numeric(10, 2), default=0)
    buyer_location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(12), nullable=True)
    delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    purchased_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utc_now)

    product = relationship("Product", back_populates="purchase_records")
    quote_associations = relationship(
        "PurchaseRecordQuote",
        back_populates="purchase_record",
        cascade="all, delete-orphan",
        order_by="PurchaseRecordQuote.offline_quote_id",
    )
