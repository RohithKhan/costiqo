from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.time_utils import utc_now


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    query: Mapped[str] = mapped_column(String(255), index=True)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(12), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utc_now)

    user = relationship("User", back_populates="saved_searches")
