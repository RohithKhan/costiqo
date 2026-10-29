from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.time_utils import utc_now


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), index=True, nullable=True)
    query: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(12), nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(32), default="price_below")
    target_price: Mapped[object | None] = mapped_column(Numeric(10, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utc_now)

    user = relationship("User", back_populates="alert_rules")
    product = relationship("Product", back_populates="alert_rules")
