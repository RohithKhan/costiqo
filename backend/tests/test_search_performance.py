from decimal import Decimal
from pathlib import Path
from time import perf_counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.core.config import Settings
from app.db.models.product import Product
from app.db.models.vendor_product import VendorProduct
from app.db.session import get_engine, get_session_factory
from app.main import create_app
from app.scrapers.base import PriceHistoryEntry, ScrapedListing
from app.services.dependencies import product_service, scrape_service
from app.services.query_cache_store import QueryCacheStore
from app.utils.time_utils import utc_now
from conftest import StaticScraper


HARDWARE_VENDORS = {
    "ElectronicsComp": "https://www.electronicscomp.com",
    "Robu": "https://robu.in",
    "Moglix": "https://www.moglix.com",
    "Amazon": "https://www.amazon.in",
}


def _sample_listing(
    vendor: str,
    canonical_name: str,
    brand: str,
    category: str,
    model_number: str,
    price: str,
) -> ScrapedListing:
    price_val = Decimal(price)
    return ScrapedListing(
        vendor=vendor,
        base_url=HARDWARE_VENDORS[vendor],
        scrape_strategy="test-double",
        canonical_name=canonical_name,
        brand=brand,
        category=category,
        model_number=model_number,
        image_url="https://example.com/item.jpg",
        vendor_product_name=canonical_name,
        product_url=f"{HARDWARE_VENDORS[vendor]}/{model_number}",
        price=price_val,
        raw_price=f"₹{int(price_val):,}",
        rating=4.5,
        review_count=50,
        delivery_info="2 days delivery",
        availability_status="in_stock",
        reviews=[],
        price_history=[PriceHistoryEntry(scraped_at=utc_now(), price=price_val)],
    )


def test_sql_filter_generation_for_queries():
    """Verify that _build_product_search_filter handles empty, partial, and special character queries."""
    # Empty / whitespace
    assert product_service._build_product_search_filter("") is None
    assert product_service._build_product_search_filter("   ") is None

    # Single-character tokens
    assert product_service._build_product_search_filter("a") is None

    # Normal query
    expr = product_service._build_product_search_filter("esp32 devkit")
    assert expr is not None

    # Special characters and punctuation
    expr_punct = product_service._build_product_search_filter("ESP32-S3 / v1.0 & board")
    assert expr_punct is not None

    # Ensure scrape_service filter matches logic
    scrape_expr = scrape_service._build_product_search_filter("esp32 devkit")
    assert scrape_expr is not None


def test_sql_filtering_avoids_materializing_unrelated_products(tmp_path: Path):
    """Verify that _load_products and _load_existing_results do not load unrelated products."""
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'filter-test.db'}",
        auto_create_schema=True,
        environment="test",
        secret_key="perf-test-secret",
    )
    create_app(settings)
    session_factory = get_session_factory()

    with session_factory() as db:
        # Seed 1 matching product and 10 completely unrelated products
        target = Product(
            canonical_name="UniqueMicrocontrollerXYZ DevKit V1",
            brand="Espressif",
            category="Microcontrollers",
            model_number="unique-devkit-v1",
        )
        db.add(target)
        for i in range(10):
            db.add(
                Product(
                    canonical_name=f"Cotton Casual T-Shirt Style {i}",
                    brand="ApparelBrand",
                    category="Clothing",
                    model_number=f"tshirt-{i}",
                )
            )
        db.commit()

        # Query with specific term "UniqueMicrocontrollerXYZ"
        loaded = product_service._load_products(db, query="UniqueMicrocontrollerXYZ")
        # Should only load the 1 matching product, NOT the 10 clothing items
        assert len(loaded) == 1
        assert loaded[0].canonical_name == "UniqueMicrocontrollerXYZ DevKit V1"

        # Query with unrelated term "tshirt"
        loaded_tshirts = product_service._load_products(db, query="tshirt", limit=5)
        assert len(loaded_tshirts) == 5

        # Query with non-matching term
        loaded_none = product_service._load_products(db, query="quantum-superconductor")
        assert len(loaded_none) == 0


def test_query_cache_store_timeout_and_circuit_breaker():
    """Verify that QueryCacheStore fails gracefully without multi-second stalls when Redis is unreachable."""
    # Point to an unreachable port
    store = QueryCacheStore(redis_url="redis://127.0.0.1:59999/0")

    t0 = perf_counter()
    fresh = store.is_fresh("test-key")
    elapsed = perf_counter() - t0

    # First attempt should timeout quickly (<= 0.5s instead of OS 4+ second stall)
    assert elapsed < 0.5
    assert fresh is False
    assert not store._is_redis_available()

    # Second attempt should immediately short-circuit via the circuit breaker (< 5ms)
    t1 = perf_counter()
    fresh_again = store.is_fresh("test-key")
    elapsed_short = perf_counter() - t1
    assert elapsed_short < 0.05
    assert fresh_again is False

    # In-memory operations continue functioning seamlessly
    store.mark_fresh("test-key", ttl_seconds=60)
    assert store.is_fresh("test-key") is True


def test_search_and_suggestions_correctness_and_contract(tmp_path: Path):
    """Verify search, suggestions, comparisons, and product details adhere to response schemas and maintain ranking."""
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'e2e-perf.db'}",
        auto_create_schema=True,
        bootstrap_vendors_on_startup=True,
        offer_verification_enabled=False,
        trusted_vendor_domains_raw="electronicscomp.com,robu.in,moglix.com,amazon.in",
        secret_key="perf-test-secret",
        environment="test",
    )
    app = create_app(settings)
    original_scrapers = scrape_service.scrapers
    scrape_service.clear_cache()

    listings = {
        "ElectronicsComp": [
            _sample_listing(
                "ElectronicsComp",
                "ESP32 DevKit V1 Development Board",
                "ESP32",
                "Electronics",
                "esp32-devkit-v1",
                "249",
            ),
        ],
        "Robu": [
            _sample_listing(
                "Robu",
                "ESP32 DevKit V1 Development Board",
                "ESP32",
                "Electronics",
                "esp32-devkit-v1",
                "259",
            ),
        ],
    }
    scrape_service.scrapers = [
        StaticScraper(vendor, HARDWARE_VENDORS[vendor], items)
        for vendor, items in listings.items()
    ]

    try:
        with TestClient(app) as client:
            # 1. Search endpoint
            s_resp = client.get("/api/v1/products/search", params={"q": "esp32 devkit v1 development board"})
            assert s_resp.status_code == 200
            s_data = s_resp.json()
            assert "results" in s_data
            assert len(s_data["results"]) >= 1
            first_product = s_data["results"][0]
            assert "canonical_name" in first_product
            assert "best_price" in first_product
            assert first_product["best_price"] == 249.0

            # 2. Suggestions endpoint
            sugg_resp = client.get("/api/v1/products/suggestions", params={"q": "esp32", "limit": 6})
            assert sugg_resp.status_code == 200
            sugg_data = sugg_resp.json()
            assert "results" in sugg_data
            assert "sources" in sugg_data
            assert len(sugg_data["results"]) >= 1
            assert "ESP32 DevKit V1" in sugg_data["results"][0]["canonical_name"]
            assert sugg_data["results"][0]["best_price"] == 249.0

            # 3. Comparisons endpoint
            comp_resp = client.get("/api/v1/comparisons", params={"q": "esp32 devkit v1 development board"})
            assert comp_resp.status_code == 200
            comp_data = comp_resp.json()
            assert "results" in comp_data
            assert len(comp_data["results"]) >= 1

            # 4. Product detail endpoint
            pid = first_product["id"]
            detail_resp = client.get(f"/api/v1/products/{pid}")
            assert detail_resp.status_code == 200
            detail_data = detail_resp.json()
            assert detail_data["id"] == pid
            assert "vendors" in detail_data
            assert len(detail_data["vendors"]) >= 1
            assert "comparison" in detail_data
    finally:
        scrape_service.clear_cache()
        scrape_service.scrapers = original_scrapers
