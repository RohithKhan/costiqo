from __future__ import annotations

import logging
from math import log1p

from app.schemas.comparison import ComparisonItem, ComparisonRankingMode, DecisionHighlight, DecisionSummary


logger = logging.getLogger(__name__)


class DecisionService:
    RECOMMENDATION_WEIGHTS = {
        "price": 0.22,
        "delivery": 0.12,
        "sentiment": 0.08,
        "confidence": 0.28,
        "market": 0.12,
        "purchase": 0.06,
        "location": 0.12,
    }
    VALUE_WEIGHTS = {
        "price": 0.3,
        "delivery": 0.1,
        "sentiment": 0.08,
        "confidence": 0.22,
        "market": 0.2,
        "purchase": 0.1,
    }
    LOW_CONFIDENCE_THRESHOLD = 0.5

    def sort_items(
        self,
        items: list[ComparisonItem],
        mode: ComparisonRankingMode,
        *,
        location: str | None = None,
        pincode: str | None = None,
    ) -> list[ComparisonItem]:
        if mode == "recommended":
            return sorted(
                items,
                key=lambda item: (
                    -self._recommendation_score(
                        item,
                        location=location,
                        pincode=pincode,
                    ),
                    item.landed_price,
                    -item.price_confidence,
                    item.vendor,
                ),
            )
        if mode == "cheapest":
            return sorted(
                items,
                key=lambda item: (
                    item.landed_price,
                    item.price,
                    -item.price_confidence,
                    item.vendor,
                ),
            )
        if mode == "fastest_delivery":
            return sorted(
                items,
                key=lambda item: (
                    item.estimated_delivery_days
                    if item.estimated_delivery_days is not None
                    else 999,
                    item.landed_price,
                    -item.price_confidence,
                    item.vendor,
                ),
            )
        if mode == "best_value":
            return sorted(
                items,
                key=lambda item: (
                    -self._value_score(item),
                    item.landed_price,
                    -item.price_confidence,
                    item.vendor,
                ),
            )

        max_reviews = max((item.review_count for item in items), default=0)
        return sorted(
            items,
            key=lambda item: (
                -self._review_score(item, max_reviews=max_reviews),
                -item.price_confidence,
                item.landed_price,
                item.vendor,
            ),
        )

    def build_summary(
        self,
        items: list[ComparisonItem],
        *,
        location: str | None = None,
        pincode: str | None = None,
    ) -> DecisionSummary | None:
        if not items:
            return None

        cheapest_offer = min(items, key=lambda item: (item.price, item.landed_price, item.vendor))
        best_landed_price = min(
            items,
            key=lambda item: (item.landed_price, item.price, item.vendor),
        )
        fastest_delivery = self._fastest_delivery(items)
        best_reviewed = self._best_reviewed(items)
        best_sentiment = self._best_sentiment(items)
        best_value = max(
            items,
            key=lambda item: self._value_score(item),
        )

        location_context_applied = bool(location or pincode)
        best_for_location = max(
            items,
            key=lambda item: self._location_score(
                item,
                location=location,
                pincode=pincode,
            ),
        )
        recommended = max(
            items,
            key=lambda item: self._recommendation_score(
                item,
                location=location,
                pincode=pincode,
            ),
        )
        recommendation_reason = self._build_reason(
            recommended,
            best_landed_price=best_landed_price,
            fastest_delivery=fastest_delivery,
            best_sentiment=best_sentiment,
            best_for_location=best_for_location,
            location_context_applied=location_context_applied,
        )

        warnings: list[str] = []
        low_confidence_count = sum(
            1 for item in items if item.price_confidence < self.LOW_CONFIDENCE_THRESHOLD
        )
        if low_confidence_count:
            noun = "offer" if low_confidence_count == 1 else "offers"
            first_verb = "has" if low_confidence_count == 1 else "have"
            second_verb = "is" if low_confidence_count == 1 else "are"
            warnings.append(
                f"{low_confidence_count} {noun} {first_verb} weak price confidence and {second_verb} deprioritized."
            )
        missing_shipping_count = sum(1 for item in items if item.shipping_cost is None)
        if missing_shipping_count:
            warnings.append(
                f"{missing_shipping_count} offers do not list shipping separately, so landed price may understate checkout cost."
            )
        missing_delivery_count = sum(
            1 for item in items if item.estimated_delivery_days is None
        )
        if missing_delivery_count:
            warnings.append(
                f"{missing_delivery_count} offers are missing delivery estimates, so speed comparisons are less certain."
            )
        missing_sentiment_count = sum(
            1 for item in items if item.sentiment_score is None
        )
        if missing_sentiment_count == len(items):
            warnings.append("Sentiment analysis is unavailable for these offers right now.")
        elif missing_sentiment_count:
            warnings.append(
                f"{missing_sentiment_count} offers are missing sentiment signals, so review-based ranking is partial."
            )
        if not location_context_applied:
            warnings.append("Add a pincode to personalize delivery and location recommendations.")

        summary = DecisionSummary(
            recommended=self._highlight(
                recommended,
                detail=recommendation_reason,
            ),
            recommendation_reason=recommendation_reason,
            cheapest_offer=self._highlight(
                cheapest_offer,
                detail="Lowest listed price before shipping.",
            ),
            best_landed_price=self._highlight(
                best_landed_price,
                detail="Lowest total cost including shipping.",
            ),
            fastest_delivery=(
                self._highlight(
                    fastest_delivery,
                    detail=self._delivery_detail(fastest_delivery),
                )
                if fastest_delivery is not None
                else None
            ),
            best_reviewed=(
                self._highlight(
                    best_reviewed,
                    detail=self._review_detail(best_reviewed),
                )
                if best_reviewed is not None
                else None
            ),
            best_sentiment=(
                self._highlight(
                    best_sentiment,
                    detail=self._sentiment_detail(best_sentiment),
                )
                if best_sentiment is not None
                else None
            ),
            best_value=self._highlight(
                best_value,
                detail="Strong balance of cost, trust, and delivery.",
            ),
            best_for_location=self._highlight(
                best_for_location,
                detail=(
                    self._location_detail(
                        best_for_location,
                        location=location,
                        pincode=pincode,
                    )
                    if location_context_applied
                    else "Apply a pincode to make this location-specific."
                ),
            ),
            location_context_applied=location_context_applied,
            location_context_label=self._location_context_label(
                location=location,
                pincode=pincode,
            ),
            warnings=warnings,
        )
        logger.info(
            "recommendation_decision vendor=%s cheapest=%s best_landed=%s best_for_location=%s location_context=%s warnings=%s",
            summary.recommended.vendor,
            summary.cheapest_offer.vendor if summary.cheapest_offer is not None else "none",
            summary.best_landed_price.vendor if summary.best_landed_price is not None else "none",
            summary.best_for_location.vendor if summary.best_for_location is not None else "none",
            summary.location_context_label or "none",
            len(summary.warnings),
        )
        return summary

    def _highlight(
        self,
        item: ComparisonItem,
        *,
        detail: str | None,
    ) -> DecisionHighlight:
        return DecisionHighlight(
            vendor=item.vendor,
            vendor_product_id=item.vendor_product_id,
            product_url=item.product_url,
            source_type=item.source_type,
            price=item.price,
            landed_price=item.landed_price,
            price_confidence=item.price_confidence,
            estimated_delivery_days=item.estimated_delivery_days,
            sentiment_score=item.sentiment_score,
            detail=detail,
        )

    def _fastest_delivery(
        self,
        items: list[ComparisonItem],
    ) -> ComparisonItem | None:
        candidates = [
            item for item in items if item.estimated_delivery_days is not None
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda item: (
                item.estimated_delivery_days or 0,
                -item.price_confidence,
                item.landed_price,
                item.vendor,
            ),
        )

    def _best_reviewed(
        self,
        items: list[ComparisonItem],
    ) -> ComparisonItem | None:
        candidates = [
            item
            for item in items
            if item.rating is not None and item.review_count > 0
        ]
        if not candidates:
            return None
        max_reviews = max(item.review_count for item in candidates)
        return max(
            candidates,
            key=lambda item: (
                self._review_score(item, max_reviews=max_reviews),
                item.price_confidence,
                -item.landed_price,
            ),
        )

    def _best_sentiment(
        self,
        items: list[ComparisonItem],
    ) -> ComparisonItem | None:
        candidates = [
            item for item in items if item.sentiment_score is not None
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda item: (
                item.sentiment_score or 0,
                item.price_confidence,
                -(item.review_count or 0),
                -item.landed_price,
            ),
        )

    def _recommendation_score(
        self,
        item: ComparisonItem,
        *,
        location: str | None,
        pincode: str | None,
    ) -> float:
        weights = self.RECOMMENDATION_WEIGHTS
        return round(
            weights["price"] * self._price_score(item)
            + weights["delivery"] * self._delivery_score(item)
            + weights["sentiment"] * self._sentiment_score(item)
            + weights["confidence"] * item.price_confidence
            + weights["market"] * self._market_score(item)
            + weights["purchase"] * self._purchase_score(item)
            + weights["location"] * self._location_score(
                item,
                location=location,
                pincode=pincode,
            ),
            4,
        )

    def _value_score(self, item: ComparisonItem) -> float:
        weights = self.VALUE_WEIGHTS
        return round(
            weights["price"] * self._price_score(item)
            + weights["delivery"] * self._delivery_score(item)
            + weights["sentiment"] * self._sentiment_score(item)
            + weights["confidence"] * item.price_confidence
            + weights["market"] * self._market_score(item)
            + weights["purchase"] * self._purchase_score(item),
            4,
        )

    def _price_score(self, item: ComparisonItem) -> float:
        return max(0.0, min(1.0, 1 / (1 + (item.landed_price / 100000))))

    def _delivery_score(self, item: ComparisonItem) -> float:
        if item.estimated_delivery_days is None:
            return 0.45
        return max(0.0, min(1.0, 1 - (item.estimated_delivery_days / 10)))

    def _sentiment_score(self, item: ComparisonItem) -> float:
        if item.sentiment_score is None:
            return 0.5
        return max(0.0, min(1.0, (item.sentiment_score + 1) / 2))

    def _market_score(self, item: ComparisonItem) -> float:
        if item.reasonability_label == "below-market":
            return 1.0
        if item.reasonability_label == "fair":
            return 0.72
        if item.reasonability_label == "above-market":
            return 0.3
        return 0.5

    def _purchase_score(self, item: ComparisonItem) -> float:
        delta = item.delta_from_last_purchase_percent
        if delta is None:
            return 0.5
        if delta <= 0:
            return min(1.0, 0.6 + min(abs(delta), 20) / 40)
        return max(0.1, 0.55 - min(delta, 40) / 80)

    def _location_score(
        self,
        item: ComparisonItem,
        *,
        location: str | None,
        pincode: str | None,
    ) -> float:
        if not location and not pincode:
            return 0.5
        if pincode and item.seller_pincode:
            return 1.0 if item.seller_pincode == pincode else 0.15
        if location and item.seller_location:
            normalized_location = location.strip().lower()
            normalized_seller_location = item.seller_location.strip().lower()
            if normalized_location in normalized_seller_location or normalized_seller_location in normalized_location:
                return 0.95
            return 0.25
        if item.source_type == "online":
            if item.estimated_delivery_days is None:
                return 0.45
            return max(0.2, min(0.8, 0.85 - (item.estimated_delivery_days * 0.1)))
        return 0.3

    def _review_score(self, item: ComparisonItem, *, max_reviews: int) -> float:
        if item.rating is None:
            return 0.0
        review_component = (
            log1p(item.review_count) / log1p(max_reviews)
            if max_reviews > 0
            else 0.0
        )
        return ((item.rating / 5) * 0.75) + (review_component * 0.25)

    def _build_reason(
        self,
        recommended: ComparisonItem,
        *,
        best_landed_price: ComparisonItem,
        fastest_delivery: ComparisonItem | None,
        best_sentiment: ComparisonItem | None,
        best_for_location: ComparisonItem,
        location_context_applied: bool,
    ) -> str:
        reasons: list[str] = []
        if recommended.price_verification_status == "verified":
            reasons.append("its store price is verified")
        elif recommended.price_confidence >= 0.9:
            reasons.append("its price confidence is strong")

        if recommended.vendor_product_id == best_landed_price.vendor_product_id:
            reasons.append("its landed price is the lowest")
        elif recommended.reasonability_label == "below-market":
            reasons.append("it is priced below the live market median")

        if fastest_delivery and recommended.vendor_product_id == fastest_delivery.vendor_product_id:
            reasons.append("it has the fastest delivery estimate")

        if location_context_applied and recommended.vendor_product_id == best_for_location.vendor_product_id:
            reasons.append("it fits the current location context best")

        if best_sentiment and recommended.vendor_product_id == best_sentiment.vendor_product_id:
            reasons.append("it has the strongest sentiment signal")

        if not reasons:
            reasons.append("it balances price, delivery, sentiment, and trust better than the alternatives")

        return "Recommended because " + ", ".join(reasons[:3]) + "."

    def _delivery_detail(self, item: ComparisonItem) -> str:
        if item.estimated_delivery_days is None:
            return "Fastest known delivery option."
        if item.estimated_delivery_days <= 1:
            return "Fastest delivery at around 1 day."
        return f"Fastest delivery at around {item.estimated_delivery_days} days."

    def _review_detail(self, item: ComparisonItem) -> str:
        if item.rating is None:
            return "Strongest review signal."
        return f"{item.rating:.1f} rating across {item.review_count} reviews."

    def _sentiment_detail(self, item: ComparisonItem) -> str:
        if item.sentiment_score is None:
            return "Strongest sentiment signal."
        return f"Sentiment score {item.sentiment_score:.2f}."

    def _location_detail(
        self,
        item: ComparisonItem,
        *,
        location: str | None,
        pincode: str | None,
    ) -> str:
        if pincode and item.seller_pincode == pincode:
            return f"Matches pincode {pincode} directly."
        if location and item.seller_location:
            return f"Closest local match for {location}."
        if item.estimated_delivery_days is not None:
            if item.estimated_delivery_days == 1:
                return "Delivery estimate is about 1 day for this context."
            return f"Delivery estimate is about {item.estimated_delivery_days} days for this context."
        return "Best available match for the current delivery context."

    def _location_context_label(
        self,
        *,
        location: str | None,
        pincode: str | None,
    ) -> str | None:
        parts = [value for value in [location, pincode] if value]
        return " · ".join(parts) if parts else None
