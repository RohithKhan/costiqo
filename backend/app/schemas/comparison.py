from typing import Literal
from datetime import datetime

from pydantic import BaseModel

from app.schemas.procurement import LatestPurchaseSummary


ComparisonRankingMode = Literal[
    "recommended",
    "cheapest",
    "fastest_delivery",
    "best_value",
    "best_reviewed",
]


class BestOption(BaseModel):
    vendor: str
    price: float
    product_url: str
    vendor_product_id: int


class DecisionHighlight(BaseModel):
    vendor: str
    vendor_product_id: int
    product_url: str
    source_type: str
    price: float
    landed_price: float
    price_confidence: float
    estimated_delivery_days: int | None = None
    sentiment_score: float | None = None
    detail: str | None = None


class DecisionSummary(BaseModel):
    recommended: DecisionHighlight
    recommendation_reason: str
    cheapest_offer: DecisionHighlight | None = None
    best_landed_price: DecisionHighlight | None = None
    fastest_delivery: DecisionHighlight | None = None
    best_reviewed: DecisionHighlight | None = None
    best_sentiment: DecisionHighlight | None = None
    best_value: DecisionHighlight | None = None
    best_for_location: DecisionHighlight | None = None
    location_context_applied: bool = False
    location_context_label: str | None = None
    warnings: list[str] = []


class ComparisonItem(BaseModel):
    vendor_product_id: int
    vendor: str
    vendor_domain: str | None = None
    vendor_is_trusted: bool = False
    product_name: str
    price: float
    displayed_price: float
    raw_price: str | None = None
    rating: float | None = None
    review_count: int
    delivery_info: str | None = None
    sentiment_score: float | None = None
    availability_status: str
    product_url: str
    shipping_cost: float | None = None
    estimated_delivery_days: int | None = None
    seller_location: str | None = None
    seller_pincode: str | None = None
    landed_price: float
    source_type: str
    price_verification_status: str
    price_confidence: float
    verified_price: float | None = None
    price_verified_at: datetime | None = None
    last_seen_at: datetime | None = None
    reasonability_label: str
    delta_from_median_percent: float | None = None
    delta_from_last_purchase_percent: float | None = None


class RelatedStoreLink(BaseModel):
    vendor: str
    product_url: str
    search_label: str
    note: str | None = None


class ProductGroupSummary(BaseModel):
    label: str
    relation: str
    confidence: float
    result_count: int
    results: list[ComparisonItem]


class BenchmarkSummary(BaseModel):
    min_price: float
    max_price: float
    average_price: float
    median_price: float
    offer_count: int
    last_purchase_unit_price: float | None = None


class SearchFilterSummary(BaseModel):
    key: str
    label: str
    detail: str
    source: str | None = None
    active: bool = True
    removed_count: int = 0


class SearchDiagnosticsSummary(BaseModel):
    query: str
    source_profile: str
    location: str | None = None
    pincode: str | None = None
    intent: str | None = None
    corrected_query: str | None = None
    source_groups_checked: list[str] = []
    coverage_status: str | None = None
    match_confidence: float | None = None
    sources_checked: list[str] = []
    observed_offer_count: int = 0
    matched_offer_count: int = 0
    filters: list[SearchFilterSummary] = []


class ComparisonResponse(BaseModel):
    query: str
    ranking_mode: ComparisonRankingMode = "recommended"
    product_id: int | None = None
    product_name: str | None = None
    product_image_url: str | None = None
    location: str | None = None
    pincode: str | None = None
    latest_purchase: LatestPurchaseSummary | None = None
    benchmark: BenchmarkSummary | None = None
    best_option: BestOption | None = None
    decision_summary: DecisionSummary | None = None
    results: list[ComparisonItem]
    product_groups: list[ProductGroupSummary] = []
    related_store_results: list[ComparisonItem] = []
    related_store_links: list[RelatedStoreLink] = []
    search_diagnostics: SearchDiagnosticsSummary | None = None


class ComparisonProgressResponse(BaseModel):
    progress_id: str
    offer_count: int
    status: str
