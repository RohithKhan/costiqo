from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
except ModuleNotFoundError:
    class SentimentIntensityAnalyzer:  # type: ignore[no-redef]
        POSITIVE_WORDS = {
            "good",
            "great",
            "best",
            "smooth",
            "reliable",
            "dependable",
            "fast",
            "sharp",
            "decent",
            "genuine",
            "stable",
            "acceptable",
            "solid",
            "practical",
        }
        NEGATIVE_WORDS = {
            "bad",
            "poor",
            "slow",
            "broken",
            "damaged",
            "late",
            "worst",
            "fake",
            "unstable",
            "problem",
        }

        def polarity_scores(self, content: str) -> dict[str, float]:
            tokens = {
                token.strip(".,!?;:()[]{}'\"").lower()
                for token in content.split()
                if token.strip()
            }
            positive = len(tokens & self.POSITIVE_WORDS)
            negative = len(tokens & self.NEGATIVE_WORDS)
            if positive == 0 and negative == 0:
                compound = 0.0
            else:
                compound = round((positive - negative) / max(positive + negative, 1), 2)
            return {"compound": compound}

from app.db.models.product import Product
from app.db.models.sentiment_summary import SentimentSummary
from app.db.models.vendor_product import VendorProduct
from app.schemas.review import ProductSentimentResponse, SentimentBreakdown
from app.services.product_service import select_best_listings_by_vendor
from app.utils.time_utils import utc_now
from app.utils.vendor_links import resolve_vendor_url


class SentimentService:
    def __init__(self) -> None:
        self.analyzer = SentimentIntensityAnalyzer()

    def summarize_reviews(self, reviews: list[object]) -> tuple[int, int, int, float]:
        positive = neutral = negative = 0
        scores: list[float] = []

        for review in reviews:
            content = " ".join(filter(None, [getattr(review, "title", None), review.body]))
            score = self.analyzer.polarity_scores(content)["compound"]
            scores.append(score)
            if score > 0.05:
                positive += 1
            elif score < -0.05:
                negative += 1
            else:
                neutral += 1

        average_score = round(sum(scores) / len(scores), 2) if scores else 0.0
        return positive, neutral, negative, average_score

    def upsert_summary(self, db: Session, vendor_product: VendorProduct) -> SentimentSummary:
        positive, neutral, negative, average_score = self.summarize_reviews(vendor_product.reviews)

        summary = vendor_product.sentiment_summary
        if summary is None:
            summary = SentimentSummary(vendor_product_id=vendor_product.id)
            db.add(summary)
            vendor_product.sentiment_summary = summary

        summary.positive_count = positive
        summary.neutral_count = neutral
        summary.negative_count = negative
        summary.sentiment_score = average_score
        summary.updated_at = utc_now()
        return summary

    def get_product_sentiment(self, db: Session, product_id: int) -> ProductSentimentResponse:
        stmt = (
            select(Product)
            .options(
                selectinload(Product.vendor_products).selectinload(VendorProduct.vendor),
                selectinload(Product.vendor_products).selectinload(VendorProduct.sentiment_summary),
            )
            .where(Product.id == product_id)
        )
        product = db.scalar(stmt)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found.",
            )

        vendor_breakdown: list[SentimentBreakdown] = []
        total_positive = total_neutral = total_negative = 0
        score_sum = 0.0
        scored_vendors = 0

        for listing in select_best_listings_by_vendor(product.vendor_products):
            summary = listing.sentiment_summary
            if summary is None:
                continue
            vendor_breakdown.append(
                SentimentBreakdown(
                    vendor_product_id=listing.id,
                    vendor=listing.vendor.name,
                    product_url=resolve_vendor_url(
                        listing.vendor.name,
                        listing.vendor_product_url,
                        listing.vendor_product_name,
                    ),
                    positive_count=summary.positive_count,
                    neutral_count=summary.neutral_count,
                    negative_count=summary.negative_count,
                    sentiment_score=float(summary.sentiment_score),
                )
            )
            total_positive += summary.positive_count
            total_neutral += summary.neutral_count
            total_negative += summary.negative_count
            score_sum += float(summary.sentiment_score)
            scored_vendors += 1

        overall_score = round(score_sum / scored_vendors, 2) if scored_vendors else 0.0
        return ProductSentimentResponse(
            product_id=product.id,
            sentiment_score=overall_score,
            positive_count=total_positive,
            neutral_count=total_neutral,
            negative_count=total_negative,
            vendor_breakdown=sorted(vendor_breakdown, key=lambda item: item.vendor),
        )
