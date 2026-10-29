from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.utils.time_utils import utc_now


class PurchaseRecordQuote(Base):
    __tablename__ = "purchase_record_quotes"
    __table_args__ = (
        UniqueConstraint(
            "purchase_record_id",
            "offline_quote_id",
            name="uq_purchase_record_quotes_record_quote",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_record_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_records.id", ondelete="CASCADE"),
        index=True,
    )
    offline_quote_id: Mapped[int] = mapped_column(
        ForeignKey("offline_quotes.id", ondelete="CASCADE"),
        index=True,
    )
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utc_now)

    purchase_record = relationship("PurchaseRecord", back_populates="quote_associations")
    offline_quote = relationship("OfflineQuote", back_populates="purchase_associations")
