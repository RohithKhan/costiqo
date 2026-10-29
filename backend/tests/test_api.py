from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.models.search_audit_log import SearchAuditLog
from app.db.models.product import Product
from app.db.models.user import User
from app.db.models.vendor import Vendor
from app.db.models.vendor_product import VendorProduct
from app.db.session import get_session_factory
from app.main import create_app
from app.scrapers.base import BaseScraper, SearchContext
from app.services.dependencies import offer_verification_service, scrape_service
from app.services.offer_verification_service import OfferVerificationResult
from app.services.search_diagnostics import SearchDiagnostics, SearchFilterDiagnostic
from conftest import StaticScraper, build_listing, build_review


@pytest.fixture
def admin_headers(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Admin User",
            "email": "admin@example.com",
            "password": "supersecure",
        },
    )
    assert response.status_code == 201
    token = response.json()["access_token"]

    with get_session_factory()() as db:
        user = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert user is not None
        user.role = "admin"
        db.commit()

    return {"Authorization": f"Bearer {token}"}


def test_healthcheck(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_auth_flow(client):
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Test User",
            "email": "test@example.com",
            "password": "supersecure",
        },
    )

    assert register_response.status_code == 201
    token = register_response.json()["access_token"]

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert me_response.status_code == 200
    assert me_response.json()["email"] == "test@example.com"


def test_search_and_comparison_flow(client):
    search_response = client.get("/api/v1/products/search", params={"q": "iphone 15"})

    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert search_payload["results"]
    assert search_payload["results"][0]["canonical_name"] == "Apple iPhone 15 128 GB"

    comparison_response = client.get("/api/v1/comparisons", params={"q": "iphone 15"})

    assert comparison_response.status_code == 200
    comparison_payload = comparison_response.json()
    assert comparison_payload["best_option"]["vendor"] == "Flipkart"
    assert comparison_payload["decision_summary"]["recommended"]["vendor"] == "Flipkart"
    assert len(comparison_payload["results"]) == 3
    assert comparison_payload["results"][0]["vendor"] == comparison_payload["best_option"]["vendor"]
    assert comparison_payload["results"][0]["vendor_is_trusted"] is True
    assert comparison_payload["results"][0]["vendor_domain"] == "flipkart.com"
    assert comparison_payload["results"][0]["displayed_price"] == comparison_payload["results"][0]["price"]
    assert comparison_payload["results"][0]["shipping_cost"] == 0
    assert comparison_payload["results"][0]["estimated_delivery_days"] == 1
    assert comparison_payload["results"][0]["landed_price"] == comparison_payload["results"][0]["price"]
    assert comparison_payload["results"][0]["price_verification_status"] == "fresh_unverified"
    assert comparison_payload["results"][0]["price_confidence"] == 0.7
    assert len(comparison_payload["related_store_results"]) == 2
    assert comparison_payload["related_store_results"][0]["vendor"] == "Amazon"
    assert len(comparison_payload["related_store_results"]) + len(
        comparison_payload["related_store_links"]
    ) >= 3
    assert all(
        link["vendor"] != comparison_payload["best_option"]["vendor"]
        for link in comparison_payload["related_store_links"]
    )
    assert any(
        result["vendor"] != comparison_payload["best_option"]["vendor"]
        for result in comparison_payload["results"]
    )


def test_authenticated_comparison_writes_search_audit_log(client):
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Search User",
            "email": "search-user@example.com",
            "password": "supersecure",
        },
    )
    assert register_response.status_code == 201
    token = register_response.json()["access_token"]

    response = client.get(
        "/api/v1/comparisons",
        params={"q": "iphone 15", "pincode": "560001", "ranking_mode": "recommended"},
        headers={"Authorization": f"Bearer {token}", "User-Agent": "pytest-client"},
    )

    assert response.status_code == 200
    payload = response.json()

    with get_session_factory()() as db:
        audit_log = db.scalar(
            select(SearchAuditLog).where(SearchAuditLog.user_email == "search-user@example.com")
        )

    assert audit_log is not None
    assert audit_log.query == "iphone 15"
    assert audit_log.pincode == payload["pincode"]
    assert audit_log.ranking_mode == "recommended"
    assert audit_log.result_count == len(payload["results"])
    assert audit_log.user_agent == "pytest-client"


def test_comparison_progress_tracks_final_offer_count(client):
    progress_id = "pytest-progress-iphone-15"

    response = client.get(
        "/api/v1/comparisons",
        params={"q": "iphone 15", "progress_id": progress_id},
    )
    assert response.status_code == 200
    payload = response.json()

    progress_response = client.get(f"/api/v1/comparisons/progress/{progress_id}")

    assert progress_response.status_code == 200
    progress_payload = progress_response.json()
    assert progress_payload["status"] == "complete"
    assert progress_payload["offer_count"] == len(payload["results"])


def test_rate_limit_returns_soft_error(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'rate-limit.db'}",
        neon_database_url="",
        auto_create_schema=True,
        bootstrap_vendors_on_startup=False,
        offer_verification_enabled=False,
        secret_key="a_secure_production_secret_key_at_least_32_characters_long",
        environment="production",
        rate_limit_enabled=True,
        rate_limit_requests=1,
        rate_limit_window_seconds=60,
    )
    app = create_app(settings)

    with TestClient(app) as rate_limited_client:
        first_response = rate_limited_client.post(
            "/api/v1/auth/register",
            json={
                "name": "Rate User",
                "email": "rate-1@example.com",
                "password": "supersecure",
            },
        )
        second_response = rate_limited_client.post(
            "/api/v1/auth/register",
            json={
                "name": "Rate User Two",
                "email": "rate-2@example.com",
                "password": "supersecure",
            },
        )

    assert first_response.status_code == 201
    assert second_response.status_code == 429
    assert second_response.json()["detail"] == "Too many requests. Please try again shortly."


def test_unclear_product_search_returns_before_scraping(client):
    class TrackingScraper(BaseScraper):
        vendor_name = "Tracking"
        base_url = "https://tracking.example"
        scrape_strategy = "test-double"

        def __init__(self) -> None:
            self.called = False

        async def search(
            self,
            query: str,
            context: SearchContext | None = None,
        ):
            self.called = True
            return []

        async def fetch_reviews(self, product_url: str):
            return []

    scraper = TrackingScraper()
    original_scrapers = scrape_service.scrapers
    scrape_service.clear_cache()
    scrape_service.scrapers = [scraper]

    try:
        response = client.get("/api/v1/products/search", params={"q": "under 500"})
    finally:
        scrape_service.clear_cache()
        scrape_service.scrapers = original_scrapers

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"] == []
    assert scraper.called is False
    assert payload["search_diagnostics"]["coverage_status"] == "query_needs_clarification"
    assert any(
        filter_item["key"] == "query_clarity"
        for filter_item in payload["search_diagnostics"]["filters"]
    )


def test_unclear_comparison_returns_before_scraping(client):
    class TrackingScraper(BaseScraper):
        vendor_name = "Tracking"
        base_url = "https://tracking.example"
        scrape_strategy = "test-double"

        def __init__(self) -> None:
            self.called = False

        async def search(
            self,
            query: str,
            context: SearchContext | None = None,
        ):
            self.called = True
            return []

        async def fetch_reviews(self, product_url: str):
            return []

    scraper = TrackingScraper()
    original_scrapers = scrape_service.scrapers
    scrape_service.clear_cache()
    scrape_service.scrapers = [scraper]

    try:
        response = client.get("/api/v1/comparisons", params={"q": "under 500"})
    finally:
        scrape_service.clear_cache()
        scrape_service.scrapers = original_scrapers

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"] == []
    assert scraper.called is False
    assert payload["search_diagnostics"]["source_profile"] == "preflight"
    assert payload["search_diagnostics"]["observed_offer_count"] == 0
    assert payload["search_diagnostics"]["coverage_status"] == "query_needs_clarification"
    assert any(
        filter_item["key"] == "query_clarity"
        for filter_item in payload["search_diagnostics"]["filters"]
    )


def test_search_and_comparison_prefer_products_with_query_matching_listings(client):
    with get_session_factory()() as db:
        amazon = db.scalar(select(Vendor).where(Vendor.name == "Amazon"))
        flipkart = db.scalar(select(Vendor).where(Vendor.name == "Flipkart"))
        croma = db.scalar(select(Vendor).where(Vendor.name == "Croma"))
        assert amazon is not None
        assert flipkart is not None
        assert croma is not None

        corrupted_product = Product(
            canonical_name="Apple iPhone 17 (Black, 512 GB)",
            brand="Apple",
            category="Smartphones",
            model_number="iphone-16-512-gb",
            image_url="https://example.com/iphone17-corrupted.jpg",
        )
        clean_product = Product(
            canonical_name="Apple iPhone 17 256 GB",
            brand="Apple",
            category="Smartphones",
            model_number="iphone-17-256-gb",
            image_url="https://example.com/iphone17-clean.jpg",
        )
        db.add_all([corrupted_product, clean_product])
        db.flush()

        db.add_all(
            [
                VendorProduct(
                    product_id=corrupted_product.id,
                    vendor_id=flipkart.id,
                    vendor_product_name="Apple iPhone 16 (Black, 512 GB)",
                    vendor_product_url="https://www.flipkart.com/apple-iphone-16-black-512-gb/p/corrupt-1",
                    current_price=Decimal("99900"),
                    raw_price="₹99,900",
                    rating=4.6,
                    review_count=1200,
                    delivery_info="Free delivery tomorrow",
                ),
                VendorProduct(
                    product_id=corrupted_product.id,
                    vendor_id=croma.id,
                    vendor_product_name="Apple iPhone 16 128 GB, Black",
                    vendor_product_url="https://www.croma.com/apple-iphone-16-128-gb-black/p/corrupt-2",
                    current_price=Decimal("68990"),
                    raw_price="₹68,990",
                    rating=5.0,
                    review_count=149,
                    delivery_info="Delivery by tomorrow",
                ),
                VendorProduct(
                    product_id=corrupted_product.id,
                    vendor_id=amazon.id,
                    vendor_product_name="Apple iPhone 17 (Black, 512 GB)",
                    vendor_product_url="https://www.amazon.in/dp/CORRUPT17BLACK512",
                    current_price=Decimal("102900"),
                    raw_price="₹102,900",
                    rating=4.7,
                    review_count=320,
                    delivery_info="Delivery in 2 days",
                ),
                VendorProduct(
                    product_id=clean_product.id,
                    vendor_id=flipkart.id,
                    vendor_product_name="Apple iPhone 17 (Lavender, 256 GB)",
                    vendor_product_url="https://www.flipkart.com/apple-iphone-17-lavender-256-gb/p/clean-1",
                    current_price=Decimal("82900"),
                    raw_price="₹82,900",
                    rating=4.7,
                    review_count=980,
                    delivery_info="Free delivery tomorrow",
                ),
                VendorProduct(
                    product_id=clean_product.id,
                    vendor_id=croma.id,
                    vendor_product_name="Apple iPhone 17 256 GB, White",
                    vendor_product_url="https://www.croma.com/apple-iphone-17-256-gb-white/p/clean-2",
                    current_price=Decimal("80990"),
                    raw_price="₹80,990",
                    rating=4.8,
                    review_count=210,
                    delivery_info="Delivery by tomorrow",
                ),
            ]
        )
        db.commit()
        clean_product_id = clean_product.id

    search_response = client.get("/api/v1/products/search", params={"q": "iphone 17"})

    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert search_payload["results"][0]["id"] == clean_product_id
    assert search_payload["results"][0]["best_vendor"] == "Croma"

    comparison_response = client.get("/api/v1/comparisons", params={"q": "iphone 17"})

    assert comparison_response.status_code == 200
    comparison_payload = comparison_response.json()
    assert comparison_payload["product_id"] == clean_product_id
    assert comparison_payload["best_option"]["vendor"] == "Croma"
    assert {item["vendor"] for item in comparison_payload["results"]} == {
        "Flipkart",
        "Croma",
    }


def test_ensure_product_does_not_merge_incompatible_model_keys(client):
    with get_session_factory()() as db:
        existing = Product(
            canonical_name="Apple iPhone 16 (Black, 512 GB)",
            brand="Apple",
            category="Smartphones",
            model_number="iphone-16-512-gb",
            image_url="https://example.com/iphone16-black.jpg",
        )
        db.add(existing)
        db.flush()

        listing = build_listing(
            vendor="Flipkart",
            base_url="https://www.flipkart.com",
            canonical_name="Apple iPhone 17 (Black, 512 GB)",
            brand="Apple",
            category="Smartphones",
            model_number="iphone-17-512-gb",
            image_url="https://example.com/iphone17-black.jpg",
            vendor_product_name="Apple iPhone 17 (Black, 512 GB)",
            product_url="https://www.flipkart.com/apple-iphone-17-black-512-gb/p/test-17",
            price="102900",
            rating=4.7,
            review_count=320,
            delivery_info="Free delivery tomorrow",
            reviews=[],
        )

        ensured = scrape_service._ensure_product(db, listing)

        assert ensured.id != existing.id
        assert ensured.model_number == "iphone-17-512-gb"


def test_low_confidence_offer_does_not_win_best_option(client, monkeypatch):
    async def fake_verify(listings):
        results = {}
        for listing in listings:
            if listing.vendor == "Flipkart":
                results[listing.id] = OfferVerificationResult(
                    status="mismatch_detected",
                    confidence=0.0,
                    verified_price=73999.0,
                    checked_at=listing.last_seen_at,
                )
            if listing.vendor == "Amazon":
                results[listing.id] = OfferVerificationResult(
                    status="verified",
                    confidence=1.0,
                    verified_price=listing.current_price,
                    checked_at=listing.last_seen_at,
                )
        return results

    monkeypatch.setattr(
        offer_verification_service,
        "verify_vendor_summaries",
        fake_verify,
    )

    response = client.get("/api/v1/comparisons", params={"q": "iphone 15"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["best_option"]["vendor"] == "Amazon"
    assert payload["results"][0]["price_verification_status"] == "verified"
    assert payload["decision_summary"]["cheapest_offer"]["vendor"] == "Amazon"
    assert payload["decision_summary"]["recommended"]["vendor"] == "Amazon"
    assert any(
        result["vendor"] == "Flipkart"
        and result["price_verification_status"] == "mismatch_detected"
        and result["price"] == 73999.0
        for result in payload["results"]
    )


def test_ranking_mode_can_sort_results_without_changing_best_option(client, monkeypatch):
    async def fake_verify(listings):
        results = {}
        for listing in listings:
            if listing.vendor == "Flipkart":
                results[listing.id] = OfferVerificationResult(
                    status="mismatch_detected",
                    confidence=0.0,
                    verified_price=73999.0,
                    checked_at=listing.last_seen_at,
                )
            if listing.vendor == "Amazon":
                results[listing.id] = OfferVerificationResult(
                    status="verified",
                    confidence=1.0,
                    verified_price=listing.current_price,
                    checked_at=listing.last_seen_at,
                )
        return results

    monkeypatch.setattr(
        offer_verification_service,
        "verify_vendor_summaries",
        fake_verify,
    )

    response = client.get(
        "/api/v1/comparisons",
        params={"q": "iphone 15", "ranking_mode": "cheapest"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ranking_mode"] == "cheapest"
    assert payload["best_option"]["vendor"] == "Amazon"
    assert payload["results"][0]["vendor"] == "Amazon"
    assert payload["decision_summary"]["recommended"]["vendor"] == "Amazon"


def test_product_analytics_endpoints(client):
    search_response = client.get("/api/v1/products/search", params={"q": "redmi"})
    product_id = search_response.json()["results"][0]["id"]

    detail_response = client.get(f"/api/v1/products/{product_id}")
    history_response = client.get(f"/api/v1/products/{product_id}/history")
    reviews_response = client.get(f"/api/v1/products/{product_id}/reviews")
    sentiment_response = client.get(f"/api/v1/products/{product_id}/sentiment")

    assert detail_response.status_code == 200
    assert detail_response.json()["vendor_count"] == 3
    detail_payload = detail_response.json()
    assert detail_payload["comparison"]["product_id"] == product_id
    assert detail_payload["comparison"]["benchmark"]["offer_count"] == 3
    assert detail_payload["comparison"]["decision_summary"]["recommended"]["vendor"] in {
        "Amazon",
        "Flipkart",
    }
    assert detail_payload["comparison"]["decision_summary"]["recommendation_reason"]
    assert len(detail_payload["comparison"]["results"]) == 3
    assert detail_payload["comparison"]["results"][0]["displayed_price"] == detail_payload["comparison"]["results"][0]["price"]
    assert detail_payload["comparison"]["results"][0]["price_verification_status"] == "fresh_unverified"
    assert detail_payload["comparison"]["results"][0]["price_confidence"] == 0.7
    assert detail_payload["comparison"]["results"][0]["reasonability_label"] in {
        "below-market",
        "fair",
        "above-market",
    }
    assert len(detail_payload["comparison"]["related_store_results"]) == 2
    assert len(detail_payload["comparison"]["related_store_results"]) + len(
        detail_payload["comparison"]["related_store_links"]
    ) >= 3
    assert detail_payload["offline_quotes"] == []

    assert history_response.status_code == 200
    assert len(history_response.json()["history"]) == 3

    assert reviews_response.status_code == 200
    assert len(reviews_response.json()["reviews"]) >= 2

    assert sentiment_response.status_code == 200
    sentiment_payload = sentiment_response.json()
    assert sentiment_payload["positive_count"] >= 1
    assert len(sentiment_payload["vendor_breakdown"]) == 3


def test_product_detail_can_respect_ranking_mode(client):
    search_response = client.get("/api/v1/products/search", params={"q": "iphone 15"})
    product_id = search_response.json()["results"][0]["id"]

    detail_response = client.get(
        f"/api/v1/products/{product_id}",
        params={"ranking_mode": "best_reviewed"},
    )

    assert detail_response.status_code == 200
    payload = detail_response.json()
    assert payload["comparison"]["ranking_mode"] == "best_reviewed"
    assert payload["comparison"]["results"][0]["vendor"] == "Flipkart"


def test_product_suggestions_endpoint(client):
    response = client.get("/api/v1/products/suggestions", params={"q": "iphone"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"] == ["Croma"]
    assert payload["results"]
    assert payload["results"][0]["canonical_name"] == "Apple iPhone 15 128 GB"
    assert payload["results"][0]["live_store_count"] == 1
    assert {store["vendor"] for store in payload["results"][0]["source_stores"]} == {
        "Croma",
    }


def test_pincode_verification_endpoint(client):
    response = client.get("/api/v1/locations/pincode", params={"pincode": "560001"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["pincode"] == "560001"
    assert payload["district"] == "Bengaluru"
    assert payload["state"] == "Karnataka"
    assert payload["location"] == "Bengaluru, Karnataka, India"


def test_invalid_comparison_pincode_is_ignored(client):
    response = client.get(
        "/api/v1/comparisons",
        params={"q": "iphone 15", "pincode": "000000"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pincode"] is None
    assert payload["results"]


def test_partial_comparison_pincode_is_ignored(client):
    response = client.get(
        "/api/v1/comparisons",
        params={"q": "iphone 15", "pincode": "60019"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pincode"] is None
    assert payload["results"]


def test_search_continues_when_pincode_lookup_is_temporarily_unavailable(client, monkeypatch):
    async def unavailable_lookup(pincode: str):
        raise ValueError("Unable to verify the Indian pincode right now.")

    monkeypatch.setattr(
        "app.services.search_context_service.resolve_indian_pincode",
        unavailable_lookup,
    )

    response = client.get(
        "/api/v1/comparisons",
        params={
            "q": "iphone 15",
            "location": "Kanchipuram, Tamil Nadu, India",
            "pincode": "600091",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["location"] == "Kanchipuram, Tamil Nadu, India"
    assert payload["pincode"] == "600091"
    assert payload["results"]


def test_admin_scrape_and_vendor_status(client, admin_headers):
    scrape_response = client.post(
        "/api/v1/admin/scrape",
        json={"query": "dell"},
        headers=admin_headers,
    )

    assert scrape_response.status_code == 202
    job = scrape_response.json()
    assert job["status"] == "completed"
    assert job["result_count"] >= 1

    job_response = client.get(f"/api/v1/admin/jobs/{job['id']}", headers=admin_headers)
    vendors_response = client.get("/api/v1/admin/vendors", headers=admin_headers)

    assert job_response.status_code == 200
    assert job_response.json()["id"] == job["id"]

    assert vendors_response.status_code == 200
    vendors = vendors_response.json()
    assert len(vendors) == 3
    assert any(vendor["last_status"] in {"ok", "no-match"} for vendor in vendors)


def test_procurement_quotes_and_reasonability(client, admin_headers):
    search_response = client.get("/api/v1/products/search", params={"q": "iphone 15"})
    assert search_response.status_code == 200
    product_id = search_response.json()["results"][0]["id"]

    purchase_response = client.post(
        "/api/v1/admin/purchases",
        headers=admin_headers,
        json={
            "product_id": product_id,
            "supplier_name": "Department Purchase",
            "unit_price": 72000,
            "quantity": 2,
            "shipping_cost": 1200,
            "buyer_location": "Bengaluru",
            "pincode": "560001",
            "delivery_days": 5,
            "reference_number": "PO-2026-001",
        },
    )
    assert purchase_response.status_code == 201

    quote_response = client.post(
        "/api/v1/admin/offline-quotes",
        headers=admin_headers,
        json={
            "product_id": product_id,
            "supplier_name": "Local Mobile Hub",
            "quoted_price": 65000,
            "shipping_cost": 500,
            "seller_location": "Bengaluru",
            "pincode": "560001",
            "estimated_delivery_days": 1,
            "contact_name": "Rahul",
            "contact_phone": "9999999999",
        },
    )
    assert quote_response.status_code == 201

    quotes_response = client.get(f"/api/v1/products/{product_id}/offline-quotes")
    purchases_response = client.get(f"/api/v1/products/{product_id}/purchases")
    comparison_response = client.get(
        "/api/v1/comparisons",
        params={
            "q": "iphone 15",
            "location": "Bengaluru",
            "pincode": "560001",
        },
    )

    assert quotes_response.status_code == 200
    assert purchases_response.status_code == 200
    assert comparison_response.status_code == 200

    comparison_payload = comparison_response.json()
    detail_response = client.get(f"/api/v1/products/{product_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert comparison_payload["location"] == "Bengaluru"
    assert comparison_payload["pincode"] == "560001"
    assert comparison_payload["latest_purchase"]["supplier_name"] == "Department Purchase"
    assert comparison_payload["benchmark"]["offer_count"] == 4
    assert comparison_payload["best_option"]["vendor"] == "Offline · Local Mobile Hub"
    assert comparison_payload["results"][0]["source_type"] == "offline"
    assert comparison_payload["results"][0]["landed_price"] == 65500
    assert comparison_payload["results"][0]["reasonability_label"] in {
        "below-market",
        "fair",
    }
    assert comparison_payload["results"][0]["delta_from_median_percent"] < 0
    assert comparison_payload["results"][0]["delta_from_last_purchase_percent"] < 0
    assert comparison_payload["results"][0]["displayed_price"] == comparison_payload["results"][0]["price"]
    assert comparison_payload["results"][0]["price_verification_status"] == "supplier-quoted"
    assert comparison_payload["results"][0]["price_confidence"] == 0.9
    assert detail_payload["comparison"]["latest_purchase"]["supplier_name"] == "Department Purchase"
    assert detail_payload["comparison"]["benchmark"]["offer_count"] == 4
    assert detail_payload["comparison"]["best_option"]["vendor"] == "Offline · Local Mobile Hub"
    assert len(detail_payload["offline_quotes"]) == 1


def test_procurement_quote_lifecycle_and_summary(client, admin_headers):
    search_response = client.get("/api/v1/products/search", params={"q": "iphone 15"})
    assert search_response.status_code == 200
    product_id = search_response.json()["results"][0]["id"]

    near_expiry = (
        client.post(
            "/api/v1/admin/offline-quotes",
            headers=admin_headers,
            json={
                "product_id": product_id,
                "supplier_name": "Near Expiry Supplier",
                "quoted_price": 64500,
                "shipping_cost": 500,
                "estimated_delivery_days": 2,
                "status": "submitted",
                "valid_until": (date.today() + timedelta(days=2)).isoformat(),
                "quote_reference": "Q-NEAR-1",
            },
        )
    )
    approved_quote = client.post(
        "/api/v1/admin/offline-quotes",
        headers=admin_headers,
        json={
            "product_id": product_id,
            "supplier_name": "Approved Supplier",
            "quoted_price": 64000,
            "shipping_cost": 500,
            "estimated_delivery_days": 1,
            "status": "approved",
            "quote_reference": "Q-APP-1",
            "supplier_score": 4.6,
        },
    )

    assert near_expiry.status_code == 201
    assert approved_quote.status_code == 201
    near_expiry_payload = near_expiry.json()
    approved_quote_payload = approved_quote.json()
    assert near_expiry_payload["is_expiring_soon"] is True
    assert approved_quote_payload["status"] == "approved"

    purchase_response = client.post(
        "/api/v1/admin/purchases",
        headers=admin_headers,
        json={
            "product_id": product_id,
            "supplier_name": "Approved Supplier",
            "unit_price": 63950,
            "quantity": 1,
            "shipping_cost": 500,
            "related_quote_ids": [approved_quote_payload["id"]],
            "reference_number": "PO-LIFE-1",
        },
    )
    assert purchase_response.status_code == 201
    purchase_payload = purchase_response.json()
    assert purchase_payload["related_quote_ids"] == [approved_quote_payload["id"]]
    assert purchase_payload["market_best_price"] is not None

    purchases_resp = client.get(f"/api/v1/products/{product_id}/purchases")
    assert purchases_resp.status_code == 200
    assert purchases_resp.json()[0]["related_quote_ids"] == [approved_quote_payload["id"]]

    update_response = client.patch(
        f"/api/v1/admin/offline-quotes/{near_expiry_payload['id']}",
        headers=admin_headers,
        json={"status": "approved"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "approved"

    quotes_response = client.get(f"/api/v1/products/{product_id}/offline-quotes")
    summary_response = client.get(
        "/api/v1/admin/procurement/summary",
        headers=admin_headers,
        params={"product_id": product_id},
    )

    assert quotes_response.status_code == 200
    assert summary_response.status_code == 200
    quotes_payload = quotes_response.json()
    summary_payload = summary_response.json()
    assert any(
        quote["id"] == approved_quote_payload["id"] and quote["status"] == "purchased" and quote["is_active"] is False
        for quote in quotes_payload
    )
    assert summary_payload["active_quote_count"] >= 1
    assert summary_payload["expiring_quote_count"] >= 1
    assert summary_payload["approved_quote_count"] >= 1
    assert summary_payload["latest_purchase_benchmark"] is not None
    assert summary_payload["latest_purchase_benchmark"]["supplier_name"] == "Approved Supplier"
    assert any(
        supplier["supplier_name"] == "Approved Supplier"
        and supplier["competitiveness_label"] in {"beats-online", "competitive", "above-online"}
        for supplier in summary_payload["supplier_competitiveness"]
    )


def test_invalid_quote_transition_is_rejected(client, admin_headers):
    search_response = client.get("/api/v1/products/search", params={"q": "iphone 15"})
    product_id = search_response.json()["results"][0]["id"]

    quote_response = client.post(
        "/api/v1/admin/offline-quotes",
        headers=admin_headers,
        json={
            "product_id": product_id,
            "supplier_name": "Lifecycle Guard",
            "quoted_price": 66000,
            "shipping_cost": 500,
            "status": "submitted",
        },
    )
    assert quote_response.status_code == 201
    quote_id = quote_response.json()["id"]

    invalid_response = client.patch(
        f"/api/v1/admin/offline-quotes/{quote_id}",
        headers=admin_headers,
        json={"status": "draft"},
    )

    assert invalid_response.status_code == 400
    assert "cannot move" in invalid_response.json()["detail"]


def test_pincode_can_change_recommendation(client, admin_headers):
    search_response = client.get("/api/v1/products/search", params={"q": "iphone 15"})
    assert search_response.status_code == 200
    product_id = search_response.json()["results"][0]["id"]

    first_quote = client.post(
        "/api/v1/admin/offline-quotes",
        headers=admin_headers,
        json={
            "product_id": product_id,
            "supplier_name": "Bengaluru Hub",
            "quoted_price": 65000,
            "shipping_cost": 500,
            "seller_location": "Bengaluru",
            "pincode": "560001",
            "estimated_delivery_days": 1,
        },
    )
    second_quote = client.post(
        "/api/v1/admin/offline-quotes",
        headers=admin_headers,
        json={
            "product_id": product_id,
            "supplier_name": "Delhi Hub",
            "quoted_price": 65100,
            "shipping_cost": 500,
            "seller_location": "Delhi",
            "pincode": "110001",
            "estimated_delivery_days": 1,
        },
    )

    assert first_quote.status_code == 201
    assert second_quote.status_code == 201

    bengaluru_response = client.get(
        "/api/v1/comparisons",
        params={
            "q": "iphone 15",
            "location": "Bengaluru",
            "pincode": "560001",
        },
    )
    delhi_response = client.get(
        "/api/v1/comparisons",
        params={
            "q": "iphone 15",
            "location": "Delhi",
            "pincode": "110001",
        },
    )

    assert bengaluru_response.status_code == 200
    assert delhi_response.status_code == 200

    bengaluru_payload = bengaluru_response.json()
    delhi_payload = delhi_response.json()
    assert bengaluru_payload["decision_summary"]["recommended"]["vendor"] == "Offline · Bengaluru Hub"
    assert delhi_payload["decision_summary"]["recommended"]["vendor"] == "Offline · Delhi Hub"
    assert bengaluru_payload["decision_summary"]["best_for_location"]["vendor"] == "Offline · Bengaluru Hub"
    assert delhi_payload["decision_summary"]["best_for_location"]["vendor"] == "Offline · Delhi Hub"


def test_listing_vendor_identity_can_differ_from_scraper_source(client):
    original_scrapers = scrape_service.scrapers
    scrape_service.clear_cache()
    scrape_service.scrapers = [
        StaticScraper(
            "Flipkart",
            "https://www.flipkart.com",
            [
                build_listing(
                    vendor="Croma",
                    base_url="https://www.croma.com",
                    canonical_name="Samsung Galaxy S24 256 GB",
                    brand="Samsung",
                    category="Smartphones",
                    model_number="samsung-galaxy-s24-256gb",
                    image_url="https://example.com/galaxy-s24.jpg",
                    vendor_product_name="Samsung Galaxy S24 256 GB",
                    product_url="https://www.croma.com/samsung-galaxy-s24-256-gb/p/123456",
                    price="71999",
                    rating=4.5,
                    review_count=320,
                    delivery_info="Delivery in 2 days",
                    reviews=[
                        build_review(
                            "Good in-store support",
                            "Price matched with quick delivery.",
                            4.4,
                        ),
                    ],
                )
            ],
        )
    ]
    try:
        response = client.get("/api/v1/products/search", params={"q": "galaxy s24"})
    finally:
        scrape_service.clear_cache()
        scrape_service.scrapers = original_scrapers

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"]
    assert payload["results"][0]["best_vendor"] == "Croma"


def test_live_comparison_can_match_variant_only_results_for_broad_query(client):
    original_scrapers = scrape_service.scrapers
    scrape_service.clear_cache()
    scrape_service.scrapers = [
        StaticScraper(
            "Flipkart",
            "https://www.flipkart.com",
            [
                build_listing(
                    vendor="Flipkart",
                    base_url="https://www.flipkart.com",
                    canonical_name="Apple iPhone 17 Pro 256 GB",
                    brand="Apple",
                    category="Smartphones",
                    model_number="iphone-17-pro-256-gb",
                    image_url="https://example.com/iphone17pro.jpg",
                    vendor_product_name="Apple iPhone 17 Pro (Black, 256 GB)",
                    product_url="https://www.flipkart.com/apple-iphone-17-pro/p/itm17pro",
                    price="99999",
                    rating=4.7,
                    review_count=480,
                    delivery_info="Free delivery tomorrow",
                    reviews=[],
                ),
            ],
        ),
        StaticScraper(
            "Amazon",
            "https://www.amazon.in",
            [
                build_listing(
                    vendor="Amazon",
                    base_url="https://www.amazon.in",
                    canonical_name="Apple iPhone 17 Pro 256 GB",
                    brand="Apple",
                    category="Smartphones",
                    model_number="iphone-17-pro-256-gb",
                    image_url="https://example.com/iphone17pro.jpg",
                    vendor_product_name="Apple iPhone 17 Pro 256 GB",
                    product_url="https://www.amazon.in/dp/IPHONE17PRO256",
                    price="100999",
                    rating=4.6,
                    review_count=330,
                    delivery_info="Delivery in 2 days",
                    reviews=[],
                ),
            ],
        ),
    ]
    try:
        response = client.get("/api/v1/comparisons", params={"q": "iphone 17"})
    finally:
        scrape_service.clear_cache()
        scrape_service.scrapers = original_scrapers

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"]
    assert payload["product_name"] == "Apple iPhone 17 Pro 256 GB"
    assert payload["best_option"]["vendor"] == "Flipkart"


def test_live_comparison_can_match_short_alias_queries(client):
    original_scrapers = scrape_service.scrapers
    scrape_service.clear_cache()
    scrape_service.scrapers = [
        StaticScraper(
            "Amazon",
            "https://www.amazon.in",
            [
                build_listing(
                    vendor="Amazon",
                    base_url="https://www.amazon.in",
                    canonical_name="Sony PlayStation 5 Slim Disc Edition",
                    brand="Sony",
                    category="Electronics",
                    model_number="sony-playstation-5-slim-disc-edition",
                    image_url="https://example.com/ps5-slim.jpg",
                    vendor_product_name="Sony PlayStation 5 Slim Disc Edition Console",
                    product_url="https://www.amazon.in/dp/PS5SLIMDISC",
                    price="54990",
                    rating=4.8,
                    review_count=920,
                    delivery_info="Delivery by tomorrow",
                    reviews=[],
                ),
            ],
        ),
    ]
    try:
        response = client.get("/api/v1/comparisons", params={"q": "ps5"})
    finally:
        scrape_service.clear_cache()
        scrape_service.scrapers = original_scrapers

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"]
    assert payload["product_name"] == "Sony PlayStation 5 Slim Disc Edition"
    assert payload["best_option"]["vendor"] == "Amazon"


def test_empty_comparison_includes_search_diagnostics(client):
    class DiagnosticsOnlyScraper(BaseScraper):
        def __init__(self) -> None:
            self.vendor_name = "Diagnostics Store"
            self.base_url = "https://diagnostics.example"
            self.scrape_strategy = "test-double"

        async def search(
            self,
            query: str,
            context: SearchContext | None = None,
        ):
            self.last_search_diagnostics = SearchDiagnostics(
                query=query,
                source_profile="primary",
                location=context.effective_location if context is not None else None,
                pincode=context.pincode if context is not None else None,
                sources_checked=[self.vendor_name],
                observed_offer_count=2,
                matched_offer_count=0,
                filters=[
                    SearchFilterDiagnostic(
                        key="domain_allowlist",
                        label="Domain allowlist",
                        detail=(
                            "Domain allowlist disabled. Offers from any merchant domain are allowed, "
                            "but domains in the configured merchant list are still marked as trusted in the UI."
                        ),
                        source=self.vendor_name,
                        active=False,
                        removed_count=0,
                    ),
                    SearchFilterDiagnostic(
                        key="direct_title_match",
                        label="Direct title match",
                        detail="Rejects direct scraper titles that do not match the search.",
                        source=self.vendor_name,
                        active=True,
                        removed_count=2,
                    ),
                ],
            )
            return []

        async def fetch_reviews(self, product_url: str):
            return []

    original_scrapers = scrape_service.scrapers
    original_scrape_query = scrape_service.scrape_query
    scrape_service.clear_cache()
    scrape_service.scrapers = [DiagnosticsOnlyScraper()]

    async def fail_scrape_query(*args, **kwargs):
        raise AssertionError("compare() should not issue a duplicate synchronous scrape after an empty live fetch")

    scrape_service.scrape_query = fail_scrape_query
    try:
        response = client.get(
            "/api/v1/comparisons",
            params={
                "q": "charger",
                "location": "Bengaluru, Karnataka, India",
                "pincode": "560001",
            },
        )
    finally:
        scrape_service.clear_cache()
        scrape_service.scrapers = original_scrapers
        scrape_service.scrape_query = original_scrape_query

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"] == []
    assert payload["search_diagnostics"]["observed_offer_count"] == 2
    assert payload["search_diagnostics"]["matched_offer_count"] == 0
    assert payload["search_diagnostics"]["location"] == "Bengaluru, Karnataka, India"
    assert payload["search_diagnostics"]["pincode"] == "560001"
    assert any(
        filter_item["key"] == "domain_allowlist"
        and filter_item["active"] is False
        for filter_item in payload["search_diagnostics"]["filters"]
    )
    assert any(
        filter_item["key"] == "direct_title_match"
        and filter_item["removed_count"] == 2
        for filter_item in payload["search_diagnostics"]["filters"]
    )


def test_live_comparison_marks_only_configured_domains_as_trusted(client):
    original_scrapers = scrape_service.scrapers
    scrape_service.clear_cache()
    scrape_service.scrapers = [
        StaticScraper(
            "Flipkart",
            "https://www.flipkart.com",
            [
                build_listing(
                    vendor="Flipkart",
                    base_url="https://www.flipkart.com",
                    canonical_name="Apple iPhone 15 128 GB",
                    brand="Apple",
                    category="Smartphones",
                    model_number="apple-iphone-15-128gb",
                    image_url="https://example.com/iphone15.jpg",
                    vendor_product_name="Apple iPhone 15 128 GB",
                    product_url="https://www.flipkart.com/apple-iphone-15-128-gb/p/itmtrusted",
                    price="68999",
                    rating=4.4,
                    review_count=120,
                    delivery_info="Delivery by tomorrow",
                    reviews=[],
                ),
                build_listing(
                    vendor="Unknown Shop",
                    base_url="https://unknown-shop.example",
                    canonical_name="Apple iPhone 15 128 GB",
                    brand="Apple",
                    category="Smartphones",
                    model_number="apple-iphone-15-128gb",
                    image_url="https://example.com/iphone15.jpg",
                    vendor_product_name="Apple iPhone 15 128 GB",
                    product_url="https://unknown-shop.example/apple-iphone-15-128-gb",
                    price="69999",
                    rating=4.1,
                    review_count=40,
                    delivery_info="Delivery in 3 days",
                    reviews=[],
                ),
            ],
        )
    ]
    try:
        response = client.get("/api/v1/comparisons", params={"q": "iphone 15"})
    finally:
        scrape_service.clear_cache()
        scrape_service.scrapers = original_scrapers

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["results"]) == 2
    trust_by_vendor = {
        item["vendor"]: {
            "trusted": item["vendor_is_trusted"],
            "domain": item["vendor_domain"],
        }
        for item in payload["results"]
    }
    assert trust_by_vendor["Flipkart"] == {
        "trusted": True,
        "domain": "flipkart.com",
    }
    assert trust_by_vendor["Unknown Shop"] == {
        "trusted": False,
        "domain": "unknown-shop.example",
    }
