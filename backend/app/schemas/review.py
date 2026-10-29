from datetime import date

from pydantic import BaseModel


class ReviewItem(BaseModel):
    id: int
    vendor: str
    title: str | None = None
    body: str
    rating: float | None = None
    review_date: date | None = None


class ReviewsResponse(BaseModel):
    product_id: int
    reviews: list[ReviewItem]


class SentimentBreakdown(BaseModel):
    vendor_product_id: int
    vendor: str
    product_url: str
    positive_count: int
    neutral_count: int
    negative_count: int
    sentiment_score: float


class ProductSentimentResponse(BaseModel):
    product_id: int
    sentiment_score: float
    positive_count: int
    neutral_count: int
    negative_count: int
    vendor_breakdown: list[SentimentBreakdown]
