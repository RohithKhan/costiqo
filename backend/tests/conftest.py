import inspect
from pathlib import Path
from datetime import date
from decimal import Decimal

import pytest
import httpx

if "app" not in inspect.signature(httpx.Client.__init__).parameters:
    _original_httpx_client_init = httpx.Client.__init__

    def _compat_httpx_client_init(self, *args, app=None, **kwargs):
        return _original_httpx_client_init(self, *args, **kwargs)

    httpx.Client.__init__ = _compat_httpx_client_init

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.scrapers.base import BaseScraper, PriceHistoryEntry, ScrapedListing, ScrapedReview, SearchContext
from app.scrapers.normalizers import listing_matches_query
from app.services.dependencies import scrape_service
from app.utils.india_pincode import PincodeDetails
from app.utils.time_utils import utc_now


def build_review(title: str, body: str, rating: float) -> ScrapedReview:
    return ScrapedReview(
        title=title,
        body=body,
        rating=rating,
        review_date=date(2026, 4, 1),
    )


def build_listing(
    *,
    vendor: str,
    base_url: str,
    canonical_name: str,
    brand: str,
    category: str,
    model_number: str,
    image_url: str,
    vendor_product_name: str,
    product_url: str,
    price: str,
    rating: float,
    review_count: int,
    delivery_info: str,
    reviews: list[ScrapedReview],
) -> ScrapedListing:
    price_value = Decimal(price)
    return ScrapedListing(
        vendor=vendor,
        base_url=base_url,
        scrape_strategy="test-double",
        canonical_name=canonical_name,
        brand=brand,
        category=category,
        model_number=model_number,
        image_url=image_url,
        vendor_product_name=vendor_product_name,
        product_url=product_url,
        price=price_value,
        raw_price=f"₹{int(price_value):,}",
        rating=rating,
        review_count=review_count,
        delivery_info=delivery_info,
        reviews=reviews,
        price_history=[PriceHistoryEntry(scraped_at=utc_now(), price=price_value)],
    )


TEST_LISTINGS = {
    "Amazon": [
        build_listing(
            vendor="Amazon",
            base_url="https://www.amazon.in",
            canonical_name="Apple iPhone 15 128 GB",
            brand="Apple",
            category="Smartphones",
            model_number="apple-iphone-15-128gb",
            image_url="https://example.com/iphone15-black.jpg",
            vendor_product_name="Apple iPhone 15 (128 GB) - Black",
            product_url="https://www.amazon.in/dp/B0CHX1W1XY",
            price="69900",
            rating=4.6,
            review_count=1850,
            delivery_info="Delivery by tomorrow",
            reviews=[
                build_review("Solid camera", "Battery life is dependable and performance is smooth.", 4.5),
            ],
        ),
        build_listing(
            vendor="Amazon",
            base_url="https://www.amazon.in",
            canonical_name="Redmi Note 13 Pro 5G 256 GB",
            brand="Xiaomi",
            category="Smartphones",
            model_number="redmi-note-13-pro-5g-256gb",
            image_url="https://example.com/redmi-note-13-pro.jpg",
            vendor_product_name="Redmi Note 13 Pro 5G (Coral Purple, 8GB RAM, 256GB Storage)",
            product_url="https://www.amazon.in/dp/B0CNJ1REDM",
            price="24999",
            rating=4.3,
            review_count=920,
            delivery_info="Delivery in 2 days",
            reviews=[
                build_review("Good display", "Display is sharp and charging is fast.", 4.0),
            ],
        ),
        build_listing(
            vendor="Amazon",
            base_url="https://www.amazon.in",
            canonical_name="Dell Inspiron 15 3530",
            brand="Dell",
            category="Laptops",
            model_number="dell-inspiron-15-3530-i5",
            image_url="https://example.com/dell-inspiron.jpg",
            vendor_product_name="Dell Inspiron 15 3530, Intel Core i5 13th Gen, 16GB RAM",
            product_url="https://www.amazon.in/dp/B0DELL3530",
            price="57990",
            rating=4.1,
            review_count=410,
            delivery_info="Delivery by Friday",
            reviews=[
                build_review("Practical laptop", "Good keyboard and enough performance for office work.", 4.0),
            ],
        ),
    ],
    "Flipkart": [
        build_listing(
            vendor="Flipkart",
            base_url="https://www.flipkart.com",
            canonical_name="Apple iPhone 15 128 GB",
            brand="Apple",
            category="Smartphones",
            model_number="apple-iphone-15-128gb",
            image_url="https://example.com/iphone15-black.jpg",
            vendor_product_name="Apple iPhone 15 (Black, 128 GB)",
            product_url="https://www.flipkart.com/apple-iphone-15-black-128-gb/p/itm1234567890",
            price="68999",
            rating=4.7,
            review_count=2400,
            delivery_info="Free delivery tomorrow",
            reviews=[
                build_review("Best price", "Packaging was good and delivery was on time.", 4.7),
            ],
        ),
        build_listing(
            vendor="Flipkart",
            base_url="https://www.flipkart.com",
            canonical_name="Redmi Note 13 Pro 5G 256 GB",
            brand="Xiaomi",
            category="Smartphones",
            model_number="redmi-note-13-pro-5g-256gb",
            image_url="https://example.com/redmi-note-13-pro.jpg",
            vendor_product_name="REDMI Note 13 Pro 5G (Midnight Black, 256 GB)",
            product_url="https://www.flipkart.com/redmi-note-13-pro-5g/p/itmredmi123",
            price="23999",
            rating=4.4,
            review_count=1100,
            delivery_info="Free delivery in 2 days",
            reviews=[
                build_review("Fast phone", "Performance is reliable and the camera is decent for the price.", 4.2),
            ],
        ),
        build_listing(
            vendor="Flipkart",
            base_url="https://www.flipkart.com",
            canonical_name="Dell Inspiron 15 3530",
            brand="Dell",
            category="Laptops",
            model_number="dell-inspiron-15-3530-i5",
            image_url="https://example.com/dell-inspiron.jpg",
            vendor_product_name="Dell Inspiron 15 3530 Intel Core i5 13th Gen",
            product_url="https://www.flipkart.com/dell-inspiron-15-3530/p/itmdell3530",
            price="56990",
            rating=4.2,
            review_count=530,
            delivery_info="Delivery by Saturday",
            reviews=[
                build_review("Office-ready", "Thermals are stable and battery life is acceptable.", 4.1),
            ],
        ),
    ],
    "Croma": [
        build_listing(
            vendor="Croma",
            base_url="https://www.croma.com",
            canonical_name="Apple iPhone 15 128 GB",
            brand="Apple",
            category="Smartphones",
            model_number="apple-iphone-15-128gb",
            image_url="https://example.com/iphone15-black.jpg",
            vendor_product_name="Apple iPhone 15 128 GB Croma Offer",
            product_url="https://www.croma.com/apple-iphone-15-128-gb/p/croma123iphone",
            price="70999",
            rating=4.0,
            review_count=260,
            delivery_info="Estimated delivery in 4 days",
            reviews=[
                build_review("Works fine", "Seller communication was okay and the phone arrived sealed.", 3.9),
            ],
        ),
        build_listing(
            vendor="Croma",
            base_url="https://www.croma.com",
            canonical_name="Redmi Note 13 Pro 5G 256 GB",
            brand="Xiaomi",
            category="Smartphones",
            model_number="redmi-note-13-pro-5g-256gb",
            image_url="https://example.com/redmi-note-13-pro.jpg",
            vendor_product_name="Redmi Note 13 Pro 5G Croma Offer",
            product_url="https://www.croma.com/redmi-note-13-pro-5g/p/croma123redmi",
            price="24550",
            rating=3.9,
            review_count=180,
            delivery_info="Estimated delivery in 5 days",
            reviews=[
                build_review("Decent value", "Not the fastest delivery but the device was genuine.", 3.8),
            ],
        ),
    ],
}


class StaticScraper(BaseScraper):
    def __init__(self, vendor_name: str, base_url: str, listings: list[ScrapedListing]) -> None:
        self.vendor_name = vendor_name
        self.base_url = base_url
        self.scrape_strategy = "test-double"
        self._listings = listings

    async def search(
        self,
        query: str,
        context: SearchContext | None = None,
    ) -> list[ScrapedListing]:
        return [
            listing
            for listing in self._listings
            if listing_matches_query(
                query,
                listing.canonical_name,
                listing.vendor_product_name,
                listing.brand,
                listing.category,
                listing.model_number,
            )
        ]

    async def fetch_reviews(self, product_url: str) -> list[ScrapedReview]:
        for listing in self._listings:
            if listing.product_url == product_url:
                return listing.reviews
        return []


@pytest.fixture
def fake_pincode_lookup(monkeypatch):
    async def _fake_resolve(pincode: str) -> PincodeDetails:
        if pincode == "560001":
            return PincodeDetails(
                pincode="560001",
                district="Bengaluru",
                state="Karnataka",
                office_name="Bangalore G.P.O.",
            )
        if pincode == "110001":
            return PincodeDetails(
                pincode="110001",
                district="Central Delhi",
                state="Delhi",
                office_name="Connaught Place",
            )
        raise ValueError("Pincode was not recognized as a valid Indian delivery area.")

    monkeypatch.setattr(
        "app.services.search_context_service.resolve_indian_pincode",
        _fake_resolve,
    )


@pytest.fixture
def client(tmp_path: Path, fake_pincode_lookup):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        auto_create_schema=True,
        bootstrap_vendors_on_startup=True,
        offer_verification_enabled=False,
        secret_key="test-secret-key",
        environment="test",
    )
    app = create_app(settings)
    original_scrapers = scrape_service.scrapers
    scrape_service.clear_cache()
    scrape_service.scrapers = [
        StaticScraper("Amazon", "https://www.amazon.in", TEST_LISTINGS["Amazon"]),
        StaticScraper("Flipkart", "https://www.flipkart.com", TEST_LISTINGS["Flipkart"]),
        StaticScraper("Croma", "https://www.croma.com", TEST_LISTINGS["Croma"]),
    ]
    with TestClient(app) as test_client:
        yield test_client
    scrape_service.clear_cache()
    scrape_service.scrapers = original_scrapers
