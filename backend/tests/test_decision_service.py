from app.schemas.comparison import ComparisonItem
from app.services.decision_service import DecisionService


def build_item(
    *,
    vendor_product_id: int,
    vendor: str,
    price: float,
    landed_price: float,
    price_confidence: float,
    price_verification_status: str,
    estimated_delivery_days: int | None = None,
    sentiment_score: float | None = None,
    rating: float | None = None,
    review_count: int = 0,
    seller_location: str | None = None,
    seller_pincode: str | None = None,
    source_type: str = "online",
) -> ComparisonItem:
    return ComparisonItem(
        vendor_product_id=vendor_product_id,
        vendor=vendor,
        product_name=f"{vendor} offer",
        price=price,
        displayed_price=price,
        rating=rating,
        review_count=review_count,
        availability_status="in_stock",
        product_url=f"https://example.com/{vendor_product_id}",
        estimated_delivery_days=estimated_delivery_days,
        sentiment_score=sentiment_score,
        seller_location=seller_location,
        seller_pincode=seller_pincode,
        landed_price=landed_price,
        source_type=source_type,
        price_verification_status=price_verification_status,
        price_confidence=price_confidence,
        reasonability_label="fair",
    )


def test_cheapest_offer_can_differ_from_recommended_vendor():
    service = DecisionService()
    risky_cheapest = build_item(
        vendor_product_id=1,
        vendor="Risky Mart",
        price=58000,
        landed_price=58000,
        price_confidence=0.0,
        price_verification_status="mismatch_detected",
        estimated_delivery_days=1,
    )
    trusted = build_item(
        vendor_product_id=2,
        vendor="Trusted Store",
        price=59000,
        landed_price=59000,
        price_confidence=1.0,
        price_verification_status="verified",
        estimated_delivery_days=1,
        sentiment_score=0.4,
        rating=4.6,
        review_count=1500,
    )

    summary = service.build_summary([risky_cheapest, trusted])

    assert summary is not None
    assert summary.cheapest_offer is not None
    assert summary.cheapest_offer.vendor == "Risky Mart"
    assert summary.recommended.vendor == "Trusted Store"


def test_location_context_can_change_best_for_location():
    service = DecisionService()
    bengaluru_quote = build_item(
        vendor_product_id=1,
        vendor="Offline · Bengaluru Hub",
        price=65500,
        landed_price=66000,
        price_confidence=0.9,
        price_verification_status="supplier-quoted",
        estimated_delivery_days=1,
        seller_location="Bengaluru",
        seller_pincode="560001",
        source_type="offline",
    )
    delhi_quote = build_item(
        vendor_product_id=2,
        vendor="Offline · Delhi Hub",
        price=65400,
        landed_price=65900,
        price_confidence=0.9,
        price_verification_status="supplier-quoted",
        estimated_delivery_days=1,
        seller_location="Delhi",
        seller_pincode="110001",
        source_type="offline",
    )

    bengaluru_summary = service.build_summary(
        [bengaluru_quote, delhi_quote],
        location="Bengaluru",
        pincode="560001",
    )
    delhi_summary = service.build_summary(
        [bengaluru_quote, delhi_quote],
        location="Delhi",
        pincode="110001",
    )

    assert bengaluru_summary is not None
    assert delhi_summary is not None
    assert bengaluru_summary.best_for_location is not None
    assert delhi_summary.best_for_location is not None
    assert bengaluru_summary.best_for_location.vendor == "Offline · Bengaluru Hub"
    assert delhi_summary.best_for_location.vendor == "Offline · Delhi Hub"


def test_sort_items_can_prioritize_review_signal():
    service = DecisionService()
    low_review_offer = build_item(
        vendor_product_id=1,
        vendor="Budget Store",
        price=58000,
        landed_price=58000,
        price_confidence=0.9,
        price_verification_status="verified",
        rating=4.0,
        review_count=30,
    )
    high_review_offer = build_item(
        vendor_product_id=2,
        vendor="Popular Store",
        price=59000,
        landed_price=59000,
        price_confidence=0.7,
        price_verification_status="fresh_unverified",
        rating=4.7,
        review_count=2400,
    )

    ordered = service.sort_items(
        [low_review_offer, high_review_offer],
        "best_reviewed",
    )

    assert ordered[0].vendor == "Popular Store"


def test_sort_items_can_prioritize_cheapest_even_when_not_recommended():
    service = DecisionService()
    risky_cheapest = build_item(
        vendor_product_id=1,
        vendor="Risky Mart",
        price=58000,
        landed_price=58000,
        price_confidence=0.0,
        price_verification_status="mismatch_detected",
        estimated_delivery_days=1,
    )
    trusted = build_item(
        vendor_product_id=2,
        vendor="Trusted Store",
        price=59000,
        landed_price=59000,
        price_confidence=1.0,
        price_verification_status="verified",
        estimated_delivery_days=1,
        sentiment_score=0.4,
        rating=4.6,
        review_count=1500,
    )

    ordered = service.sort_items([risky_cheapest, trusted], "cheapest")
    recommended = service.sort_items([risky_cheapest, trusted], "recommended")

    assert ordered[0].vendor == "Risky Mart"
    assert recommended[0].vendor == "Trusted Store"


def test_summary_warns_when_delivery_shipping_and_sentiment_signals_are_missing():
    service = DecisionService()
    incomplete_offer = build_item(
        vendor_product_id=1,
        vendor="Sparse Store",
        price=61200,
        landed_price=61200,
        price_confidence=0.7,
        price_verification_status="fresh_unverified",
    )

    summary = service.build_summary([incomplete_offer])

    assert summary is not None
    assert summary.recommended.vendor == "Sparse Store"
    assert any("shipping" in warning for warning in summary.warnings)
    assert any("delivery estimates" in warning for warning in summary.warnings)
    assert any("Sentiment analysis is unavailable" in warning for warning in summary.warnings)
