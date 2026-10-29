from datetime import datetime

from pydantic import BaseModel

from app.schemas.comparison import ComparisonResponse, SearchDiagnosticsSummary
from app.schemas.procurement import OfflineQuoteResponse


class VendorListingSummary(BaseModel):
    id: int
    vendor: str
    vendor_product_name: str
    product_url: str
    current_price: float
    raw_price: str
    currency: str
    rating: float | None = None
    review_count: int
    delivery_info: str | None = None
    availability_status: str
    sentiment_score: float | None = None
    last_seen_at: datetime


class ProductSummary(BaseModel):
    id: int
    canonical_name: str
    brand: str | None = None
    category: str | None = None
    model_number: str | None = None
    image_url: str | None = None
    best_price: float | None = None
    best_vendor: str | None = None
    best_product_url: str | None = None
    vendor_count: int


class SuggestionStorePreview(BaseModel):
    vendor: str
    price: float | None = None


class SearchSuggestion(BaseModel):
    id: int
    canonical_name: str
    brand: str | None = None
    category: str | None = None
    image_url: str | None = None
    best_price: float | None = None
    best_vendor: str | None = None
    vendor_count: int
    live_store_count: int
    source_stores: list[SuggestionStorePreview]


class ProductDetail(ProductSummary):
    created_at: datetime
    vendors: list[VendorListingSummary]
    comparison: ComparisonResponse
    offline_quotes: list[OfflineQuoteResponse]


class SearchResponse(BaseModel):
    query: str
    results: list[ProductSummary]
    search_diagnostics: SearchDiagnosticsSummary | None = None


class SuggestionResponse(BaseModel):
    query: str
    sources: list[str]
    results: list[SearchSuggestion]
