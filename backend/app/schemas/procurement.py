from datetime import date, datetime

from pydantic import BaseModel, Field
from typing import Literal


QuoteStatus = Literal["draft", "submitted", "approved", "purchased", "closed", "expired"]


class OfflineQuoteCreateRequest(BaseModel):
    product_id: int
    supplier_name: str = Field(min_length=2, max_length=255)
    quoted_price: float = Field(gt=0)
    shipping_cost: float = Field(default=0, ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=12)
    seller_location: str | None = Field(default=None, max_length=120)
    pincode: str | None = Field(default=None, max_length=12)
    estimated_delivery_days: int | None = Field(default=None, ge=0, le=365)
    contact_name: str | None = Field(default=None, max_length=120)
    contact_phone: str | None = Field(default=None, max_length=32)
    quote_reference: str | None = Field(default=None, max_length=120)
    status: QuoteStatus = "submitted"
    supplier_score: float | None = Field(default=None, ge=0, le=5)
    notes: str | None = Field(default=None, max_length=500)
    valid_until: date | None = None
    is_active: bool = True


class OfflineQuoteUpdateRequest(BaseModel):
    status: QuoteStatus | None = None
    valid_until: date | None = None
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=500)
    supplier_score: float | None = Field(default=None, ge=0, le=5)
    quote_reference: str | None = Field(default=None, max_length=120)


class OfflineQuoteResponse(BaseModel):
    id: int
    product_id: int
    supplier_name: str
    quoted_price: float
    shipping_cost: float
    total_price: float
    currency: str
    seller_location: str | None = None
    pincode: str | None = None
    estimated_delivery_days: int | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    quote_reference: str | None = None
    status: QuoteStatus
    supplier_score: float | None = None
    notes: str | None = None
    valid_until: date | None = None
    days_until_expiry: int | None = None
    is_expiring_soon: bool = False
    is_active: bool
    submitted_at: datetime | None = None
    approved_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime


class PurchaseRecordCreateRequest(BaseModel):
    product_id: int
    supplier_name: str = Field(min_length=2, max_length=255)
    unit_price: float = Field(gt=0)
    quantity: int = Field(default=1, ge=1)
    shipping_cost: float = Field(default=0, ge=0)
    buyer_location: str | None = Field(default=None, max_length=120)
    pincode: str | None = Field(default=None, max_length=12)
    delivery_days: int | None = Field(default=None, ge=0, le=365)
    reference_number: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=500)
    related_quote_ids: list[int] = Field(default_factory=list)
    purchased_at: datetime | None = None


class PurchaseRecordResponse(BaseModel):
    id: int
    product_id: int
    supplier_name: str
    unit_price: float
    quantity: int
    shipping_cost: float
    total_price: float
    buyer_location: str | None = None
    pincode: str | None = None
    delivery_days: int | None = None
    reference_number: str | None = None
    notes: str | None = None
    related_quote_ids: list[int] = []
    market_best_price: float | None = None
    market_median_price: float | None = None
    delta_from_market_best_percent: float | None = None
    delta_from_market_median_percent: float | None = None
    purchased_at: datetime
    created_at: datetime


class LatestPurchaseSummary(BaseModel):
    supplier_name: str
    unit_price: float
    quantity: int
    shipping_cost: float
    total_price: float
    buyer_location: str | None = None
    delivery_days: int | None = None
    purchased_at: datetime


class ProcurementStatusCount(BaseModel):
    status: QuoteStatus
    count: int


class SupplierCompetitivenessSummary(BaseModel):
    supplier_name: str
    quote_count: int
    purchase_count: int
    best_quote_total_price: float | None = None
    average_quote_total_price: float | None = None
    average_purchase_unit_price: float | None = None
    latest_quote_status: QuoteStatus | None = None
    competitiveness_label: str


class PurchaseBenchmarkSummary(BaseModel):
    supplier_name: str
    purchased_at: datetime
    unit_price: float
    total_price: float
    market_best_price: float | None = None
    market_median_price: float | None = None
    delta_from_market_best_percent: float | None = None
    delta_from_market_median_percent: float | None = None
    benchmark_note: str


class ProcurementSummaryResponse(BaseModel):
    product_id: int
    product_name: str
    active_quote_count: int
    expiring_quote_count: int
    approved_quote_count: int
    quote_status_breakdown: list[ProcurementStatusCount]
    active_quotes: list[OfflineQuoteResponse]
    expiring_quotes: list[OfflineQuoteResponse]
    supplier_competitiveness: list[SupplierCompetitivenessSummary]
    latest_purchase_benchmark: PurchaseBenchmarkSummary | None = None
