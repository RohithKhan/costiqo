from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.time_utils import utc_now


class SavedProduct(Base):
    __tablename__ = "saved_products"
    __table_args__ = (
        UniqueConstraint("user_id", "product_url", name="uq_saved_product_user_url"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_name: Mapped[str] = mapped_column(String(255))
    product_url: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utc_now)

    user = relationship("User", back_populates="saved_products")
