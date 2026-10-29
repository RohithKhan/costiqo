from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.time_utils import utc_now


class SearchAuditLog(Base):
    __tablename__ = "search_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    user_email: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    query: Mapped[str] = mapped_column(String(255), index=True)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(12), nullable=True)
    ranking_mode: Mapped[str] = mapped_column(String(32), default="recommended")
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    client_host: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    user = relationship("User", back_populates="search_audit_logs")
