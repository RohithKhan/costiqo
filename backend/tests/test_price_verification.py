from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.schemas.comparison import ComparisonItem
from app.services.comparison_service import ComparisonService


def build_service(now: datetime) -> ComparisonService:
    service = ComparisonService(
        None,
        None,
        None,
        None,
        None,
        SimpleNamespace(),
        SimpleNamespace(),
    )
    service._now = lambda: now
    return service


def build_listing(**overrides):
    base = {
        "product_url": "https://example.com/product",
        "last_seen_at": datetime(2026, 4, 28, 10, 0, 0),
        "raw_price": "₹58,190",
        "current_price": 58190.0,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_price_verification_status_accepts_recent_naive_datetimes():
    service = build_service(datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc))

    status = service._price_verification_status(build_listing())

    assert status == "fresh_unverified"


def test_price_verification_status_marks_stale_offers():
    now = datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc)
    service = build_service(now)
    stale_seen_at = now - timedelta(hours=12)

    status = service._price_verification_status(
        build_listing(last_seen_at=stale_seen_at)
    )

    assert status == "stale"


def test_price_verification_status_marks_mismatched_raw_prices():
    service = build_service(datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc))

    status = service._price_verification_status(
        build_listing(raw_price="₹61,999", current_price=58190.0)
    )

    assert status == "mismatch_detected"


def test_price_confidence_scales_by_status():
    service = build_service(datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc))

    assert service._price_confidence("supplier-quoted") > service._price_confidence("stale")
    assert service._price_confidence("mismatch_detected") == 0.0


def test_low_confidence_offers_sort_after_trusted_offers():
    service = build_service(datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc))
    trusted = ComparisonItem(
        vendor_product_id=1,
        vendor="Trusted Store",
        product_name="Trusted Listing",
        price=60000,
        displayed_price=60000,
        review_count=0,
        availability_status="in_stock",
        product_url="https://example.com/trusted",
        landed_price=60000,
        source_type="online",
        price_verification_status="verified",
        price_confidence=1.0,
        reasonability_label="fair",
    )
    risky = ComparisonItem(
        vendor_product_id=2,
        vendor="Risky Store",
        product_name="Risky Listing",
        price=58000,
        displayed_price=58000,
        review_count=0,
        availability_status="in_stock",
        product_url="https://example.com/risky",
        landed_price=58000,
        source_type="online",
        price_verification_status="mismatch_detected",
        price_confidence=0.0,
        reasonability_label="fair",
    )

    ordered = sorted([risky, trusted], key=service._comparison_sort_key)

    assert ordered[0].vendor == "Trusted Store"
