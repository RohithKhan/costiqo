from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.services.search_diagnostics import SearchDiagnostics


@dataclass(slots=True)
class ScrapedReview:
    title: str
    body: str
    rating: float
    review_date: date


@dataclass(slots=True)
class PriceHistoryEntry:
    scraped_at: datetime
    price: Decimal


@dataclass(slots=True, frozen=True)
class SearchContext:
    location: str | None = None
    pincode: str | None = None
    resolved_location: str | None = None

    @property
    def effective_location(self) -> str | None:
        return self.resolved_location or self.location

    def cache_key(self) -> str:
        return "|".join(
            (
                (self.location or "").strip().lower(),
                (self.pincode or "").strip(),
                (self.resolved_location or "").strip().lower(),
            )
        )


@dataclass(slots=True)
class ScrapedListing:
    vendor: str
    base_url: str
    scrape_strategy: str
    canonical_name: str
    brand: str
    category: str
    model_number: str
    image_url: str
    vendor_product_name: str
    product_url: str
    price: Decimal
    raw_price: str
    currency: str = "INR"
    rating: float | None = None
    review_count: int = 0
    delivery_info: str | None = None
    availability_status: str = "in_stock"
    reviews: list[ScrapedReview] = field(default_factory=list)
    price_history: list[PriceHistoryEntry] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)


class BaseScraper(ABC):
    vendor_name: str
    base_url: str
    scrape_strategy: str = "live-playwright"
    last_search_diagnostics: SearchDiagnostics | None = None

    @abstractmethod
    async def search(
        self,
        query: str,
        context: SearchContext | None = None,
    ) -> list[ScrapedListing]:
        raise NotImplementedError

    @abstractmethod
    async def fetch_reviews(self, product_url: str) -> list[ScrapedReview]:
        raise NotImplementedError
