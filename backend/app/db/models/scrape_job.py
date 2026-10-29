import uuid

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.time_utils import utc_now


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    query: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(64), default="queued")
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
