from decimal import Decimal
from pathlib import Path
from time import perf_counter

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.scrapers.base import PriceHistoryEntry, ScrapedListing
from app.services.dependencies import scrape_service
from app.utils.time_utils import utc_now
from conftest import StaticScraper


LOCAL_LATENCY_BUDGET_SECONDS = 0.6
HARDWARE_ALLOWED_DOMAINS_RAW = "electronicscomp.com,robu.in,moglix.com,amazon.in"


HARDWARE_VENDORS = {
    "ElectronicsComp": "https://www.electronicscomp.com",
    "Robu": "https://robu.in",
    "Moglix": "https://www.moglix.com",
    "Amazon": "https://www.amazon.in",
}


def _hardware_listing(
    *,
    vendor: str,
    canonical_name: str,
    brand: str,
    category: str,
    model_number: str,
    product_url: str,
    price: str,
    delivery_info: str,
) -> ScrapedListing:
    price_value = Decimal(price)
    return ScrapedListing(
        vendor=vendor,
        base_url=HARDWARE_VENDORS[vendor],
        scrape_strategy="test-double",
        canonical_name=canonical_name,
        brand=brand,
        category=category,
        model_number=model_number,
        image_url="https://example.com/hardware.jpg",
        vendor_product_name=canonical_name,
        product_url=product_url,
        price=price_value,
        raw_price=f"₹{int(price_value):,}",
        rating=4.5,
        review_count=120,
        delivery_info=delivery_info,
        availability_status="in_stock",
        reviews=[],
        price_history=[PriceHistoryEntry(scraped_at=utc_now(), price=price_value)],
    )


FULL_HARDWARE_LISTINGS = {
    "ElectronicsComp": [
        _hardware_listing(
            vendor="ElectronicsComp",
            canonical_name="ESP32 DevKit V1 Development Board",
            brand="ESP32",
            category="Electronics",
            model_number="esp32-devkit-v1",
            product_url="https://www.electronicscomp.com/esp32-devkit-v1-development-board",
            price="249",
            delivery_info="Delivery in 2 days",
        ),
        _hardware_listing(
            vendor="ElectronicsComp",
            canonical_name="ESP32-S3 Development Board",
            brand="ESP32-S3",
            category="Electronics",
            model_number="esp32-s3-development-board",
            product_url="https://www.electronicscomp.com/esp32-s3-development-board",
            price="389",
            delivery_info="Delivery by tomorrow",
        ),
        _hardware_listing(
            vendor="ElectronicsComp",
            canonical_name="Jumper Wires 40 Pieces Pack",
            brand="Generic",
            category="Electronics",
            model_number="jumper-wires-40pcs",
            product_url="https://www.electronicscomp.com/jumper-wires-40-pieces-pack",
            price="99",
            delivery_info="Delivery in 3 days",
        ),
    ],
    "Robu": [
        _hardware_listing(
            vendor="Robu",
            canonical_name="ESP32 DevKit V1 Development Board",
            brand="ESP32",
            category="Electronics",
            model_number="esp32-devkit-v1",
            product_url="https://robu.in/product/esp32-devkit-v1-development-board/",
            price="255",
            delivery_info="Delivery in 2 days",
        ),
        _hardware_listing(
            vendor="Robu",
            canonical_name="ESP32-S3 Development Board",
            brand="ESP32-S3",
            category="Electronics",
            model_number="esp32-s3-development-board",
            product_url="https://robu.in/product/esp32-s3-development-board/",
            price="399",
            delivery_info="Delivery by tomorrow",
        ),
        _hardware_listing(
            vendor="Robu",
            canonical_name="Jumper Wires 120 Pieces Set",
            brand="Generic",
            category="Electronics",
            model_number="jumper-wires-120pcs",
            product_url="https://robu.in/product/jumper-wires-120-pieces-set/",
            price="149",
            delivery_info="Delivery in 4 days",
        ),
    ],
    "Moglix": [
        _hardware_listing(
            vendor="Moglix",
            canonical_name="ESP32 DevKit V1 Development Board",
            brand="ESP32",
            category="Electronics",
            model_number="esp32-devkit-v1",
            product_url="https://www.moglix.com/esp32-devkit-v1-development-board/mp/msn123esp32",
            price="279",
            delivery_info="Delivery in 3 days",
        ),
    ],
    "Amazon": [
        _hardware_listing(
            vendor="Amazon",
            canonical_name="ESP32 DevKit V1 Development Board",
            brand="ESP32",
            category="Electronics",
            model_number="esp32-devkit-v1",
            product_url="https://www.amazon.in/dp/B0ESP32DEVKIT",
            price="299",
            delivery_info="Delivery by tomorrow",
        ),
        _hardware_listing(
            vendor="Amazon",
            canonical_name="ESP32-S3 Development Board",
            brand="ESP32-S3",
            category="Electronics",
            model_number="esp32-s3-development-board",
            product_url="https://www.amazon.in/dp/B0ESP32S3DEV",
            price="419",
            delivery_info="Delivery by tomorrow",
        ),
    ],
}


PARTIAL_COVERAGE_LISTINGS = {
    "ElectronicsComp": [
        _hardware_listing(
            vendor="ElectronicsComp",
            canonical_name="Digital Multimeter DT-830D",
            brand="Haoyue",
            category="Electronics",
            model_number="dt830d-digital-multimeter",
            product_url="https://www.electronicscomp.com/digital-multimeter-dt830d",
            price="189",
            delivery_info="Delivery in 2 days",
        ),
    ],
    "Robu": [
        _hardware_listing(
            vendor="Robu",
            canonical_name="Digital Multimeter DT-830D",
            brand="Haoyue",
            category="Electronics",
            model_number="dt830d-digital-multimeter",
            product_url="https://robu.in/product/digital-multimeter-dt830d/",
            price="199",
            delivery_info="Delivery in 3 days",
        ),
    ],
    "Moglix": [],
    "Amazon": [],
}


@pytest.fixture
def hardware_client(tmp_path: Path, fake_pincode_lookup):
    yield from _hardware_client_fixture(
        tmp_path=tmp_path,
        listings_by_vendor=FULL_HARDWARE_LISTINGS,
    )


@pytest.fixture
def hardware_gap_client(tmp_path: Path, fake_pincode_lookup):
    yield from _hardware_client_fixture(
        tmp_path=tmp_path,
        listings_by_vendor=PARTIAL_COVERAGE_LISTINGS,
    )


def test_hardware_search_comparison_and_detail_pipeline(hardware_client: TestClient):
    search_response = hardware_client.get(
        "/api/v1/products/search",
        params={"q": "esp32 devkit v1 development board"},
    )

    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert search_payload["search_diagnostics"] is None
    assert search_payload["results"][0]["canonical_name"] == "ESP32 DevKit V1 Development Board"
    assert search_payload["results"][0]["vendor_count"] == 4
    product_id = search_payload["results"][0]["id"]

    comparison_response = hardware_client.get(
        "/api/v1/comparisons",
        params={"q": "esp32 devkit v1 development board", "pincode": "560001"},
    )

    assert comparison_response.status_code == 200
    comparison_payload = comparison_response.json()
    assert comparison_payload["product_id"] == product_id
    assert comparison_payload["product_name"] == "ESP32 DevKit V1 Development Board"
    assert comparison_payload["best_option"]["vendor"] == "ElectronicsComp"
    assert comparison_payload["best_option"]["price"] == 249.0
    assert [item["vendor"] for item in comparison_payload["results"]] == [
        "ElectronicsComp",
        "Robu",
        "Moglix",
        "Amazon",
    ]
    assert comparison_payload["location"] == "Bengaluru, Karnataka, India"
    assert comparison_payload["pincode"] == "560001"
    assert comparison_payload["benchmark"]["offer_count"] == 4
    assert comparison_payload["search_diagnostics"]["coverage_status"] == "complete"
    assert set(comparison_payload["search_diagnostics"]["source_groups_checked"]) == {
        "hardware stores",
        "mainstream stores",
    }
    assert all(item["vendor_is_trusted"] is True for item in comparison_payload["results"])
    assert all(item["price_verification_status"] == "fresh_unverified" for item in comparison_payload["results"])
    assert comparison_payload["results"][0]["estimated_delivery_days"] == 2
    assert {
        item["vendor"]
        for item in comparison_payload["related_store_results"]
    } == {"Robu", "Moglix", "Amazon"}

    detail_response = hardware_client.get(
        f"/api/v1/products/{product_id}",
        params={"ranking_mode": "recommended"},
    )

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["id"] == product_id
    assert detail_payload["vendor_count"] == 4
    assert [item["vendor"] for item in detail_payload["vendors"]] == [
        "ElectronicsComp",
        "Robu",
        "Moglix",
        "Amazon",
    ]
    assert detail_payload["comparison"]["best_option"]["vendor"] == "ElectronicsComp"


def test_hardware_suggestions_rank_live_matches_and_sources(hardware_client: TestClient):
    response = hardware_client.get("/api/v1/products/suggestions", params={"q": "esp32"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"] == ["ElectronicsComp", "Moglix"]
    assert payload["results"][0]["canonical_name"] == "ESP32 DevKit V1 Development Board"
    assert payload["results"][0]["live_store_count"] == 2
    assert {store["vendor"] for store in payload["results"][0]["source_stores"]} == {
        "ElectronicsComp",
        "Moglix",
    }


def test_hardware_precision_query_excludes_non_matching_variants(hardware_client: TestClient):
    search_response = hardware_client.get(
        "/api/v1/products/search",
        params={"q": "esp32 s3 development board"},
    )

    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert search_payload["results"][0]["canonical_name"] == "ESP32-S3 Development Board"

    comparison_response = hardware_client.get(
        "/api/v1/comparisons",
        params={"q": "esp32 s3 development board"},
    )

    assert comparison_response.status_code == 200
    comparison_payload = comparison_response.json()
    assert comparison_payload["best_option"]["vendor"] == "ElectronicsComp"
    assert all("S3" in item["product_name"] for item in comparison_payload["results"])
    assert {item["vendor"] for item in comparison_payload["results"]} == {
        "ElectronicsComp",
        "Robu",
        "Amazon",
    }


def test_hardware_comparison_surfaces_coverage_gaps_without_failing_request(
    hardware_gap_client: TestClient,
):
    response = hardware_gap_client.get(
        "/api/v1/comparisons",
        params={"q": "digital multimeter"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["best_option"]["vendor"] == "ElectronicsComp"
    assert {item["vendor"] for item in payload["results"]} == {"ElectronicsComp", "Robu"}
    assert payload["search_diagnostics"]["coverage_status"] == "complete"
    assert any(
        filter_item["key"] == "candidate_relation_validation"
        for filter_item in payload["search_diagnostics"]["filters"]
    )


def test_hardware_api_meets_local_latency_budget(hardware_client: TestClient):
    search_elapsed, search_payload = _timed_json_get(
        hardware_client,
        "/api/v1/products/search",
        {"q": "esp32 devkit v1 development board"},
    )
    suggestions_elapsed, suggestions_payload = _timed_json_get(
        hardware_client,
        "/api/v1/products/suggestions",
        {"q": "esp32"},
    )
    comparison_elapsed, comparison_payload = _timed_json_get(
        hardware_client,
        "/api/v1/comparisons",
        {"q": "esp32 devkit v1 development board"},
    )
    detail_elapsed, detail_payload = _timed_json_get(
        hardware_client,
        f"/api/v1/products/{search_payload['results'][0]['id']}",
        {},
    )

    assert search_payload["results"]
    assert suggestions_payload["results"]
    assert comparison_payload["results"]
    assert detail_payload["vendors"]
    assert max(
        search_elapsed,
        suggestions_elapsed,
        comparison_elapsed,
        detail_elapsed,
    ) < LOCAL_LATENCY_BUDGET_SECONDS


def _hardware_client_fixture(
    *,
    tmp_path: Path,
    listings_by_vendor: dict[str, list[ScrapedListing]],
):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'hardware-readiness.db'}",
        auto_create_schema=True,
        bootstrap_vendors_on_startup=True,
        offer_verification_enabled=False,
        trusted_vendor_domains_raw=HARDWARE_ALLOWED_DOMAINS_RAW,
        secret_key="hardware-suite-secret",
        environment="test",
    )
    app = create_app(settings)
    original_scrapers = scrape_service.scrapers
    scrape_service.clear_cache()
    scrape_service.scrapers = [
        StaticScraper(vendor_name, HARDWARE_VENDORS[vendor_name], listings)
        for vendor_name, listings in listings_by_vendor.items()
    ]
    with TestClient(app) as test_client:
        yield test_client
    scrape_service.clear_cache()
    scrape_service.scrapers = original_scrapers


def _timed_json_get(
    client: TestClient,
    path: str,
    params: dict[str, str],
) -> tuple[float, dict]:
    started_at = perf_counter()
    response = client.get(path, params=params)
    elapsed_seconds = perf_counter() - started_at
    assert response.status_code == 200
    return elapsed_seconds, response.json()
