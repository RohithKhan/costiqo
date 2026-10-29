from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.time_utils import utc_now


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="user")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utc_now)

    saved_products = relationship("SavedProduct", back_populates="user", cascade="all, delete-orphan")
    saved_searches = relationship("SavedSearch", back_populates="user", cascade="all, delete-orphan")
    alert_rules = relationship("AlertRule", back_populates="user", cascade="all, delete-orphan")
    search_audit_logs = relationship("SearchAuditLog", back_populates="user", passive_deletes=True)
